#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 0 ]]; then
  echo "Usage: ./run.sh" >&2
  exit 2
fi

script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
cd "$script_dir"

# Always run the lightweight installation pass so run.sh is sufficient on its
# own. Image assembly happens once below through Compose's --build option.
echo "Validating installation prerequisites and configuration..."
WEATHER_INSTALL_SKIP_BUILD=1 "$script_dir/install.sh"

set -a
# shellcheck disable=SC1091
source "$script_dir/.env"
set +a

wait_timeout=${COMPOSE_WAIT_TIMEOUT:-600}
if [[ ! "$wait_timeout" =~ ^[1-9][0-9]*$ ]]; then
  echo "COMPOSE_WAIT_TIMEOUT must be a positive integer." >&2
  exit 1
fi

compose=(docker compose --project-directory "$script_dir" --file "$script_dir/compose.yaml")

report_failure() {
  local status=$?
  trap - ERR
  echo >&2
  echo "Platform startup failed. Current container state:" >&2
  "${compose[@]}" ps --all >&2 || true
  echo >&2
  echo "Inspect logs with: docker compose logs --tail=200" >&2
  exit "$status"
}
trap report_failure ERR

"${compose[@]}" --profile observability config --quiet

echo "Starting PostgreSQL and Redis..."
"${compose[@]}" up --build -d --wait --wait-timeout "$wait_timeout" postgres redis

echo "Applying reviewed application SQL migrations..."
"$script_dir/scripts/apply_migrations.sh" --yes
"$script_dir/scripts/verify_database.sh"

echo "Starting all application, Airflow, proxy, cache, and observability containers..."
"${compose[@]}" --profile observability up \
  --build \
  -d \
  --wait \
  --wait-timeout "$wait_timeout"

echo "Checking application readiness..."
"${compose[@]}" exec -T weather-api python -c \
  "import urllib.request; urllib.request.urlopen('http://localhost:8000/health/ready', timeout=10).read()"
"${compose[@]}" exec -T tile-api python -c \
  "import urllib.request; urllib.request.urlopen('http://localhost:8000/health/ready', timeout=10).read()"

trap - ERR

app_port=${APP_PORT:-8080}
https_port=${HTTPS_PORT:-8443}
app_url="https://${CADDY_SITE_ADDRESS}"
airflow_port=${AIRFLOW_PORT:-8081}
prometheus_port=${PROMETHEUS_PORT:-9090}
grafana_port=${GRAFANA_PORT:-3000}

echo
echo "Weather platform is running."
echo "  Map:        ${app_url}/"
echo "  Forecast:   ${app_url}/forecast"
echo "  HTTPS bind: ${APP_BIND_ADDRESS:-0.0.0.0}:${https_port}"
echo "  Redirect:   ${APP_BIND_ADDRESS:-0.0.0.0}:${app_port} (HTTP redirects only)"
echo "  API docs:   ${app_url}/docs"
echo "  Airflow:    http://localhost:${airflow_port}/"
echo "  Prometheus: http://localhost:${prometheus_port}/"
echo "  Grafana:    http://localhost:${grafana_port}/"
echo
"${compose[@]}" ps --all
