#!/usr/bin/env bash
set -euo pipefail

usage() {
  echo "Usage: $0" >&2
}

if [[ $# -ne 0 ]]; then
  usage
  exit 2
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "docker is required" >&2
  exit 1
fi

project_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$project_root"

wait_timeout=${INGESTION_WAIT_TIMEOUT_SECONDS:-7200}
poll_interval=${INGESTION_POLL_INTERVAL_SECONDS:-5}
if [[ ! "$wait_timeout" =~ ^[1-9][0-9]*$ ]] \
  || [[ ! "$poll_interval" =~ ^[1-9][0-9]*$ ]]; then
  echo "Ingestion wait and poll intervals must be positive integers." >&2
  exit 2
fi

dag_ids=()
while IFS= read -r dag_id; do
  if [[ -n "$dag_id" ]]; then
    dag_ids[${#dag_ids[@]}]=$dag_id
  fi
done < <(
  docker compose exec -T airflow-scheduler python - <<'PY'
import os
from pathlib import Path

from weather_ingest.orchestration import load_ingestion_dag_definitions

config_root = Path(os.environ.get("WEATHER_CONFIG_ROOT", "/opt/weather/config"))
for definition in load_ingestion_dag_definitions(config_root):
    print(definition.dag_id)
PY
)
dag_ids[${#dag_ids[@]}]=noaa_gfs_ingest
dag_ids[${#dag_ids[@]}]=nrcan_cwfis_hotspots_ingest
dag_ids[${#dag_ids[@]}]=nrcan_cwfis_cffdrs_ingest
dag_ids[${#dag_ids[@]}]=eccc_city_forecasts_ingest
dag_ids[${#dag_ids[@]}]=eccc_imagery_ingest

if [[ ${#dag_ids[@]} -eq 0 ]]; then
  echo "No enabled data-collection DAGs were discovered." >&2
  exit 1
fi

run_id="run_all_collections__$(date -u +%Y%m%dT%H%M%SZ)__$$"
echo "Triggering ${#dag_ids[@]} data-collection DAG(s) with run ID $run_id:"

for dag_id in "${dag_ids[@]}"; do
  echo "  - $dag_id"
  docker compose exec -T airflow-scheduler \
    airflow dags trigger "$dag_id" \
      --run-id "$run_id" \
      --output json \
    >/dev/null
done

echo
echo "All DAGs submitted. Waiting for terminal results..."
failure_count=0

for dag_id in "${dag_ids[@]}"; do
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
        echo "SUCCESS  $dag_id"
        break
        ;;
      failed)
        echo "FAILED   $dag_id" >&2
        docker compose exec -T airflow-scheduler \
          airflow tasks states-for-dag-run "$dag_id" "$run_id" --output table >&2
        failure_count=$((failure_count + 1))
        break
        ;;
      queued|running)
        ;;
      *)
        echo "Waiting for $dag_id (current state: ${state:-not visible yet})..."
        ;;
    esac
    if (( SECONDS - started_at >= wait_timeout )); then
      echo "TIMEOUT  $dag_id after ${wait_timeout}s (state: ${state:-unknown})" >&2
      failure_count=$((failure_count + 1))
      break
    fi
    sleep "$poll_interval"
  done
done

echo
if (( failure_count > 0 )); then
  echo "$failure_count of ${#dag_ids[@]} data-collection DAG(s) failed or timed out." >&2
  exit 1
fi

echo "All ${#dag_ids[@]} data-collection DAG(s) completed successfully."

# Events depend on the newly collected hotspots and fire-weather state. Never
# reconcile before those inputs finish, or after an upstream collection fails.
echo "Reconciling fire events from the completed input collections..."
docker compose exec -T airflow-scheduler \
  airflow dags trigger fire_event_reconcile --run-id "$run_id" --output json >/dev/null
started_at=$SECONDS
while true; do
  state=$(
    docker compose exec -T airflow-scheduler \
      airflow dags state fire_event_reconcile "$run_id" 2>/dev/null \
      | tail -n 1 | cut -d ',' -f 1 | tr '[:upper:]' '[:lower:]' | tr -d '[:space:]"'
  )
  case "$state" in
    success) echo "SUCCESS  fire_event_reconcile"; break ;;
    failed) echo "FAILED   fire_event_reconcile" >&2; exit 1 ;;
  esac
  if (( SECONDS - started_at >= wait_timeout )); then
    echo "TIMEOUT  fire_event_reconcile after ${wait_timeout}s" >&2
    exit 1
  fi
  sleep "$poll_interval"
done
