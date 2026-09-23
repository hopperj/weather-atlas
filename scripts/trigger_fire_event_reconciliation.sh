#!/usr/bin/env bash
set -euo pipefail
script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
exec "$script_dir/trigger_smoke_dag.sh" fire_event_reconcile
