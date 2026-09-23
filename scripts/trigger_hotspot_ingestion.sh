#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 0 ]]; then
  echo "Usage: $0" >&2
  exit 2
fi
if ! command -v docker >/dev/null 2>&1; then
  echo "docker is required" >&2
  exit 1
fi

project_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$project_root"

dag_id=nrcan_cwfis_hotspots_ingest
run_id="nrcan_cwfis_hotspots__$(date -u +%Y%m%dT%H%M%SZ)__$$"
wait_timeout=${CWFIS_WAIT_TIMEOUT_SECONDS:-3600}
poll_interval=${CWFIS_POLL_INTERVAL_SECONDS:-5}
if [[ ! "$wait_timeout" =~ ^[1-9][0-9]*$ ]] \
  || [[ ! "$poll_interval" =~ ^[1-9][0-9]*$ ]]; then
  echo "CWFIS wait and poll intervals must be positive integers." >&2
  exit 2
fi

echo "Triggering $dag_id (run ID $run_id)."
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
      exit 0
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
