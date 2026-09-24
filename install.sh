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

# Refuse an absent/wrong NAS mount before creating directories or secrets.
weather_mount=$(env_value WEATHER_DATA_MOUNTPOINT)
if [[ -n "$weather_mount" ]]; then
  require_command findmnt
  if ! findmnt --mountpoint "$weather_mount" >/dev/null; then
    echo "Required weather-data mount is not mounted: $weather_mount" >&2
    exit 1
  fi
  expected_source=$(env_value WEATHER_DATA_MOUNT_SOURCE)
  actual_source=$(findmnt --noheadings --output SOURCE --mountpoint "$weather_mount")
  if [[ -n "$expected_source" && "$actual_source" != "$expected_source" ]]; then
    echo "Weather-data mount has an unexpected source: $actual_source" >&2
    exit 1
  fi
fi

weatherapp_data_root=$(env_value WEATHERAPP_DATA_DIR)
weatherapp_data_root=${weatherapp_data_root:-./weatherapp_data}
if [[ "$weatherapp_data_root" != /* ]]; then
  weatherapp_data_root="$script_dir/$weatherapp_data_root"
fi
postgres_data_root=$(env_value POSTGRES_DATA_DIR)
postgres_data_root=${postgres_data_root:-$weatherapp_data_root/postgres}
if [[ "$postgres_data_root" != /* ]]; then
  postgres_data_root="$script_dir/$postgres_data_root"
fi
postgres_storage_exists=false
if [[ -d "$postgres_data_root" ]]; then
  postgres_storage_exists=true
fi
# Check before creating the service root: temporary service state may be nested
# under POSTGRES_DATA_DIR, which must not make a fresh install look established.
manage_service_permissions=$(env_value WEATHER_MANAGE_SERVICE_PERMISSIONS)
manage_service_permissions=${manage_service_permissions:-true}
case "$manage_service_permissions" in
  true) mkdir -p "$weatherapp_data_root" ;;
  false)
    if [[ -z "$(env_value WEATHER_MONITORING_DIR)" ]]; then
      echo "Set WEATHER_MONITORING_DIR to local storage before using externally managed service directories." >&2
      exit 1
    fi
    for directory in . redis airflow/logs sarracenia/cache caddy/data caddy/config tile-cache backups/postgres; do
      if [[ ! -d "$weatherapp_data_root/$directory" ]]; then
        echo "Externally managed service directory must already exist: $weatherapp_data_root/$directory" >&2
        exit 1
      fi
    done
    ;;
  *) echo "WEATHER_MANAGE_SERVICE_PERMISSIONS must be true or false." >&2; exit 1 ;;
esac
weatherapp_data_root=$(cd "$weatherapp_data_root" && pwd -P)

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
manage_data_permissions=${WEATHER_MANAGE_DATA_PERMISSIONS:-true}
case "$manage_data_permissions" in
  true) mkdir -p "$data_root" ;;
  false)
    if [[ ! -d "$data_root" ]]; then
      echo "Externally managed WEATHER_DATA_DIR must already exist: $data_root" >&2
      exit 1
    fi
    ;;
  *) echo "WEATHER_MANAGE_DATA_PERMISSIONS must be true or false." >&2; exit 1 ;;
esac
mkdir -p "$weatherapp_data_root"
weatherapp_data_root=$(cd "$weatherapp_data_root" && pwd -P)
data_root=$(cd "$data_root" && pwd -P)
if [[ -n "$weather_mount" ]]; then
  resolved_mount=$(cd "$weather_mount" && pwd -P)
  case "$data_root" in
    "$resolved_mount"|"$resolved_mount"/*) ;;
    *) echo "WEATHER_DATA_DIR is outside the required mount." >&2; exit 1 ;;
  esac
fi

for directory in raw staging processed derived quarantine cache temporary amqp/inbox; do
  if [[ "$manage_data_permissions" == true ]]; then
    mkdir -p "$data_root/$directory"
  elif [[ ! -d "$data_root/$directory" ]]; then
    echo "Required weather-data directory has not been transferred: $data_root/$directory" >&2
    exit 1
  fi
done

# PostgreSQL may live independently of other service state. Its entrypoint
# manages cluster ownership; never descend into an existing private cluster.
mkdir -p "$postgres_data_root"
if [[ "$manage_service_permissions" == true ]]; then
  for directory in redis airflow/logs sarracenia/cache caddy/data caddy/config \
      tile-cache backups/postgres; do
    service_root="$weatherapp_data_root/${directory%%/*}"
    mkdir -p "$service_root"
    # Private service state may belong to a container UID. Do not enter/chown it
    # as the host user; storage-init creates its children.
    if [[ -w "$service_root" && -x "$service_root" ]]; then
      mkdir -p "$weatherapp_data_root/$directory"
    fi
  done
fi
monitoring_root=${WEATHER_MONITORING_DIR:-$weatherapp_data_root}
if [[ "$monitoring_root" != /* ]]; then
  monitoring_root="$script_dir/$monitoring_root"
fi
mkdir -p "$monitoring_root/prometheus" "$monitoring_root/grafana"
mkdir -p "$script_dir/airflow/plugins"

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
  if [[ -n "${WEATHER_STARTUP_HOLD:-}" && "${WEATHER_STARTUP_HOLD}" != false ]]; then
    echo "Images are ready. Startup remains on hold: $WEATHER_STARTUP_HOLD"
    echo "Do not start containers until the migration cutover is complete."
  else
    echo "Installation completed. Start the entire platform with:"
    echo "  ./run.sh"
  fi
else
  echo "Installation prerequisites and configuration are ready."
fi
