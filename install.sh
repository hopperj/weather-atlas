#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 0 ]]; then
  echo "Usage: ./install.sh" >&2
  exit 2
fi

script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
cd "$script_dir"

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Required command is not installed: $1" >&2
    exit 1
  fi
}

for command_name in docker openssl awk; do
  require_command "$command_name"
done

if ! docker compose version >/dev/null 2>&1; then
  echo "Docker Compose v2 is required (the 'docker compose' command)." >&2
  exit 1
fi
if ! docker info >/dev/null 2>&1; then
  echo "Docker is installed, but its daemon is not available." >&2
  exit 1
fi

env_file="$script_dir/.env"
created_env=false
if [[ ! -f "$env_file" ]]; then
  cp "$script_dir/.env.example" "$env_file"
  created_env=true
  echo "Created .env from .env.example."
fi

env_value() {
  awk -F= -v key="$1" '$1 == key { sub(/^[^=]*=/, ""); value = $0 } END { print value }' \
    "$env_file"
}

set_env_value() {
  local key=$1
  local value=$2
  local temporary
  temporary=$(mktemp "${env_file}.tmp.XXXXXX")
  awk -v key="$key" -v value="$value" '
    BEGIN { replaced = 0 }
    index($0, key "=") == 1 {
      if (!replaced) {
        print key "=" value
        replaced = 1
      }
      next
    }
    { print }
    END {
      if (!replaced) print key "=" value
    }
  ' "$env_file" > "$temporary"
  chmod 600 "$temporary"
  mv "$temporary" "$env_file"
}

random_hex() {
  openssl rand -hex 32
}

fernet_key() {
  openssl rand -base64 32 | tr '+/' '-_' | tr -d '\r\n'
}

compose=(docker compose --project-directory "$script_dir" --file "$script_dir/compose.yaml")

weatherapp_data_root=$(env_value WEATHERAPP_DATA_DIR)
weatherapp_data_root=${weatherapp_data_root:-./weatherapp_data}
if [[ "$weatherapp_data_root" != /* ]]; then
  weatherapp_data_root="$script_dir/$weatherapp_data_root"
fi
mkdir -p "$weatherapp_data_root"
weatherapp_data_root=$(cd "$weatherapp_data_root" && pwd -P)

postgres_storage_exists=false
if [[ -d "$weatherapp_data_root/postgres" ]]; then
  postgres_storage_exists=true
fi

# Secret rotation must be coordinated with PostgreSQL and Airflow. Generate
# strong values only for a fresh installation; preserve an existing deployment.
if [[ "$created_env" == true || "$postgres_storage_exists" == false ]]; then
  secret_keys=(
    POSTGRES_ADMIN_PASSWORD
    AIRFLOW_DB_PASSWORD
    WEATHER_MIGRATOR_PASSWORD
    WEATHER_API_PASSWORD
    WEATHER_TILES_PASSWORD
    WEATHER_INGEST_PASSWORD
    WEATHER_READONLY_PASSWORD
    WEATHER_BACKUP_PASSWORD
    WEATHER_LAYER_TOKEN_SECRET
    AIRFLOW_ADMIN_PASSWORD
    AIRFLOW_JWT_SECRET
    GRAFANA_ADMIN_PASSWORD
  )
  for key in "${secret_keys[@]}"; do
    current=$(env_value "$key")
    if [[ -z "$current" || "$current" == change-me-* ]]; then
      set_env_value "$key" "$(random_hex)"
    fi
  done
  current_fernet=$(env_value AIRFLOW_FERNET_KEY)
  if [[ -z "$current_fernet" ]]; then
    set_env_value AIRFLOW_FERNET_KEY "$(fernet_key)"
  fi
  current_airflow_uid=$(env_value AIRFLOW_UID)
  if [[ -z "$current_airflow_uid" || "$current_airflow_uid" == "50000" ]]; then
    set_env_value AIRFLOW_UID "$(id -u)"
  fi
  echo "Generated installation secrets without printing them."
else
  if grep -Eq '^[A-Z0-9_]+=(change-me-|$)' "$env_file"; then
    echo "WARNING: .env still contains placeholder or empty secrets." >&2
    echo "Existing database storage was detected, so credentials were not rotated." >&2
  fi
fi
chmod 600 "$env_file"

set -a
# shellcheck disable=SC1091
source "$env_file"
set +a

required_settings=(
  POSTGRES_ADMIN_PASSWORD
  AIRFLOW_DB_PASSWORD
  WEATHER_MIGRATOR_PASSWORD
  WEATHER_API_PASSWORD
  WEATHER_TILES_PASSWORD
  WEATHER_INGEST_PASSWORD
  WEATHER_READONLY_PASSWORD
  WEATHER_BACKUP_PASSWORD
  WEATHER_LAYER_TOKEN_SECRET
  AIRFLOW_ADMIN_PASSWORD
  AIRFLOW_JWT_SECRET
  GRAFANA_ADMIN_PASSWORD
)
for key in "${required_settings[@]}"; do
  if [[ -z "${!key:-}" ]]; then
    echo "Required setting is empty in .env: $key" >&2
    exit 1
  fi
done

weatherapp_data_root=${WEATHERAPP_DATA_DIR:-./weatherapp_data}
if [[ "$weatherapp_data_root" != /* ]]; then
  weatherapp_data_root="$script_dir/$weatherapp_data_root"
fi

data_root=${WEATHER_DATA_DIR:-./weatherapp_data/weather}
if [[ "$data_root" != /* ]]; then
  data_root="$script_dir/$data_root"
fi
mkdir -p "$weatherapp_data_root" "$data_root"
weatherapp_data_root=$(cd "$weatherapp_data_root" && pwd -P)
data_root=$(cd "$data_root" && pwd -P)
case "$data_root" in
  "$weatherapp_data_root" | "$weatherapp_data_root"/*) ;;
  *)
    echo "WEATHER_DATA_DIR must be inside WEATHERAPP_DATA_DIR." >&2
    echo "Resolved WEATHERAPP_DATA_DIR: $weatherapp_data_root" >&2
    echo "Resolved WEATHER_DATA_DIR: $data_root" >&2
    exit 1
    ;;
esac

mkdir -p \
  "$weatherapp_data_root/postgres" \
  "$weatherapp_data_root/redis" \
  "$data_root/raw" \
  "$data_root/staging" \
  "$data_root/processed" \
  "$data_root/derived" \
  "$data_root/quarantine" \
  "$data_root/cache" \
  "$data_root/temporary" \
  "$data_root/amqp/inbox" \
  "$weatherapp_data_root/airflow/logs" \
  "$weatherapp_data_root/sarracenia/cache" \
  "$weatherapp_data_root/caddy/data" \
  "$weatherapp_data_root/caddy/config" \
  "$weatherapp_data_root/tile-cache" \
  "$weatherapp_data_root/prometheus" \
  "$weatherapp_data_root/grafana" \
  "$weatherapp_data_root/backups/postgres" \
  "$script_dir/airflow/plugins"

if ! "$script_dir/scripts/check_disk_capacity.sh"; then
  echo "WARNING: weather-data capacity is below the configured ingestion floor." >&2
  echo "The platform can run, but model downloads should remain disabled." >&2
fi

"${compose[@]}" --profile observability config --quiet

skip_build=${WEATHER_INSTALL_SKIP_BUILD:-0}
if [[ "$skip_build" != "0" && "$skip_build" != "1" ]]; then
  echo "WEATHER_INSTALL_SKIP_BUILD must be 0 or 1." >&2
  exit 1
fi

if [[ "$skip_build" == "0" ]]; then
  echo "Pulling runtime images..."
  "${compose[@]}" --profile observability pull --ignore-buildable

  echo "Building application, frontend, tile, and Airflow images..."
  "${compose[@]}" --profile observability build --pull

  echo
  echo "Installation completed. Start the entire platform with:"
  echo "  ./run.sh"
else
  echo "Installation prerequisites and configuration are ready."
fi
