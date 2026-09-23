#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "Usage: $0 <fire_event_reconcile|flexpart_smoke_operational>" >&2
  exit 2
fi
dag_id=$1
case "$dag_id" in
  fire_event_reconcile|flexpart_smoke_operational) ;;
  *) echo "Unsupported smoke DAG: $dag_id" >&2; exit 2 ;;
esac
if ! command -v docker >/dev/null 2>&1; then
  echo "docker is required" >&2
  exit 1
fi
project_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$project_root"
run_id="manual__${dag_id}__$(date -u +%Y%m%dT%H%M%SZ)__$$"
timeout=${SMOKE_DAG_WAIT_TIMEOUT_SECONDS:-14400}
poll=${SMOKE_DAG_POLL_INTERVAL_SECONDS:-5}
if [[ ! "$timeout" =~ ^[1-9][0-9]*$ ]] || [[ ! "$poll" =~ ^[1-9][0-9]*$ ]]; then
  echo "Smoke DAG timeout and poll interval must be positive integers." >&2
  exit 2
fi
docker compose exec -T airflow-scheduler \
  airflow dags trigger "$dag_id" --run-id "$run_id" --output json >/dev/null
started_at=$SECONDS
while true; do
  state=$(docker compose exec -T airflow-scheduler \
    airflow dags state "$dag_id" "$run_id" 2>/dev/null \
    | tail -n 1 | cut -d ',' -f 1 | tr '[:upper:]' '[:lower:]' | tr -d '[:space:]"')
  case "$state" in
    success) echo "$dag_id completed successfully."; exit 0 ;;
    failed)
      docker compose exec -T airflow-scheduler \
        airflow tasks states-for-dag-run "$dag_id" "$run_id" --output table >&2
      exit 1
      ;;
  esac
  if (( SECONDS - started_at >= timeout )); then
    echo "Timed out waiting for $dag_id ($run_id)." >&2
    exit 1
  fi
  sleep "$poll"
done
