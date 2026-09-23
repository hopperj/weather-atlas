#!/usr/bin/env bash
set -euo pipefail

usage() {
  echo "Usage: $0 PRODUCT" >&2
  echo "Example: $0 hrdps" >&2
}

if [[ $# -ne 1 ]]; then
  usage
  exit 2
fi

product=$1
if [[ ! "$product" =~ ^[a-z][a-z0-9_]*$ ]]; then
  echo "PRODUCT must be a lowercase product code." >&2
  exit 2
fi
if ! command -v docker >/dev/null 2>&1; then
  echo "docker is required" >&2
  exit 1
fi

project_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$project_root"

dag_id=$(
  docker compose exec -T airflow-scheduler python - "$product" <<'PY'
import os
import sys
from pathlib import Path

from weather_ingest.orchestration import load_ingestion_dag_definitions

product = sys.argv[1]
config_root = Path(os.environ.get("WEATHER_CONFIG_ROOT", "/opt/weather/config"))
matches = [
    definition.dag_id
    for definition in load_ingestion_dag_definitions(config_root)
    if definition.product_code == product
]
if len(matches) != 1:
    raise SystemExit(f"No parameterless data-collection DAG is configured for {product!r}.")
print(matches[0])
PY
)

wait_timeout=${INGESTION_WAIT_TIMEOUT_SECONDS:-7200}
poll_interval=${INGESTION_POLL_INTERVAL_SECONDS:-5}
if [[ ! "$wait_timeout" =~ ^[1-9][0-9]*$ ]] \
  || [[ ! "$poll_interval" =~ ^[1-9][0-9]*$ ]]; then
  echo "Ingestion wait and poll intervals must be positive integers." >&2
  exit 2
fi

run_id="weather_ingest__$(date -u +%Y%m%dT%H%M%SZ)__$$"
echo "Triggering $dag_id with automatic discovery (run ID $run_id)."
docker compose exec -T airflow-scheduler \
  airflow dags trigger "$dag_id" --run-id "$run_id" --output json \
  >/dev/null

started_at=$SECONDS
while true; do
  state=$(
    docker compose exec -T airflow-scheduler \
      airflow dags state "$dag_id" "$run_id" 2>/dev/null \
      | tail -n 1 \
      | cut -d ',' -f 1 \
      | tr '[:upper:]' '[:lower:]' \
      | tr -d '[:space:]"'
  )
  case "$state" in
    success)
      echo "$dag_id completed successfully."
      break
      ;;
    failed)
      echo "$dag_id failed. Task states:" >&2
      docker compose exec -T airflow-scheduler \
        airflow tasks states-for-dag-run "$dag_id" "$run_id" --output table >&2
      exit 1
      ;;
    queued|running)
      ;;
    *)
      echo "Waiting for $run_id (current state: ${state:-not visible yet})..."
      ;;
  esac
  if (( SECONDS - started_at >= wait_timeout )); then
    echo "Timed out after ${wait_timeout}s waiting for $run_id (state: ${state:-unknown})." >&2
    exit 1
  fi
  sleep "$poll_interval"
done
