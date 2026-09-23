#!/usr/bin/env bash
set -euo pipefail

script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
repo_root=$(cd "$script_dir/.." && pwd)

usage() {
  cat <<'EOF'
Usage: backup_postgres.sh [OPTIONS]

Create verified PostgreSQL custom-format dumps without overwriting prior files.

Options:
  --database all|app|airflow   Database selection (default: all)
  --output-dir PATH            Destination (default: WEATHER_BACKUP_DIR or
                                WEATHERAPP_DATA_DIR/backups/postgres)
  --help                       Show this help

Required credentials:
  app:      WEATHER_BACKUP_PASSWORD (user defaults to weather_backup)
  airflow:  AIRFLOW_BACKUP_PASSWORD or AIRFLOW_DB_PASSWORD

This command creates backups but never prunes or overwrites existing backups.
EOF
}

sha256_file() {
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$1" | awk '{print $1}'
  elif command -v shasum >/dev/null 2>&1; then
    shasum -a 256 "$1" | awk '{print $1}'
  else
    echo "Neither sha256sum nor shasum is available." >&2
    return 1
  fi
}

if [[ -f "$repo_root/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$repo_root/.env"
  set +a
fi

database_selection=all
output_dir=${WEATHER_BACKUP_DIR:-${WEATHERAPP_DATA_DIR:-./weatherapp_data}/backups/postgres}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --database)
      [[ $# -ge 2 ]] || { usage >&2; exit 2; }
      database_selection=$2
      shift 2
      ;;
    --output-dir)
      [[ $# -ge 2 ]] || { usage >&2; exit 2; }
      output_dir=$2
      shift 2
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

case "$database_selection" in
  all)
    database_kinds=(app airflow)
    ;;
  app|airflow)
    database_kinds=("$database_selection")
    ;;
  *)
    echo "--database must be one of: all, app, airflow" >&2
    exit 2
    ;;
esac

if [[ "$output_dir" != /* ]]; then
  output_dir="$repo_root/$output_dir"
fi
umask 077
mkdir -p "$output_dir"
if [[ ! -d "$output_dir" || ! -w "$output_dir" ]]; then
  echo "Backup destination is not a writable directory: $output_dir" >&2
  exit 1
fi

timestamp=$(date -u +%Y%m%dT%H%M%SZ)
if [[ ! "$timestamp" =~ ^[0-9]{8}T[0-9]{6}Z$ ]]; then
  echo "Unable to generate a safe UTC backup timestamp." >&2
  exit 1
fi

database_names=()
database_users=()
database_passwords=()
for database_kind in "${database_kinds[@]}"; do
  if [[ "$database_kind" == "app" ]]; then
    database_names+=("${WEATHER_APP_DATABASE:-weather_app}")
    database_users+=("${WEATHER_BACKUP_USER:-weather_backup}")
    database_passwords+=("${WEATHER_BACKUP_PASSWORD:-}")
  else
    database_names+=("${AIRFLOW_DATABASE:-weather_airflow}")
    database_users+=("${AIRFLOW_BACKUP_USER:-weather_airflow}")
    database_passwords+=("${AIRFLOW_BACKUP_PASSWORD:-${AIRFLOW_DB_PASSWORD:-}}")
  fi
done

for index in "${!database_names[@]}"; do
  database_name=${database_names[$index]}
  database_user=${database_users[$index]}
  database_password=${database_passwords[$index]}
  if [[ ! "$database_name" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]]; then
    echo "Unsafe database name: $database_name" >&2
    exit 2
  fi
  if [[ ! "$database_user" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]]; then
    echo "Unsafe database user: $database_user" >&2
    exit 2
  fi
  if [[ -z "$database_password" ]]; then
    echo "No backup password configured for $database_name ($database_user)." >&2
    exit 2
  fi
  final_path="$output_dir/${database_name}_${timestamp}.dump"
  if [[ -e "$final_path" || -e "$final_path.sha256" ]]; then
    echo "Refusing to overwrite existing backup: $final_path" >&2
    exit 1
  fi
done

staging_dir=$(mktemp -d "$output_dir/.postgres-backup.XXXXXX")
cleanup() {
  if [[ -n "${staging_dir:-}" && -d "$staging_dir" \
      && "$staging_dir" == "$output_dir"/.postgres-backup.* ]]; then
    rm -rf -- "$staging_dir"
  fi
}
trap cleanup EXIT

for index in "${!database_names[@]}"; do
  database_name=${database_names[$index]}
  database_user=${database_users[$index]}
  database_password=${database_passwords[$index]}
  dump_name="${database_name}_${timestamp}.dump"
  staged_dump="$staging_dir/$dump_name"

  echo "Creating $database_name backup as $database_user ..."
  docker compose --project-directory "$repo_root" --file "$repo_root/compose.yaml" exec -T \
    -e "PGPASSWORD=$database_password" postgres pg_dump \
    --host 127.0.0.1 \
    --username "$database_user" \
    --dbname "$database_name" \
    --format custom >"$staged_dump"

  if [[ ! -s "$staged_dump" ]]; then
    echo "Backup is empty: $database_name" >&2
    exit 1
  fi
  if ! docker compose --project-directory "$repo_root" --file "$repo_root/compose.yaml" \
    exec -T postgres pg_restore --list <"$staged_dump" >/dev/null; then
    echo "pg_restore could not read the $database_name backup." >&2
    exit 1
  fi

  checksum=$(sha256_file "$staged_dump")
  printf '%s  %s\n' "$checksum" "$dump_name" >"$staged_dump.sha256"
done

for index in "${!database_names[@]}"; do
  database_name=${database_names[$index]}
  dump_name="${database_name}_${timestamp}.dump"
  mv "$staging_dir/$dump_name" "$output_dir/$dump_name"
  mv "$staging_dir/$dump_name.sha256" "$output_dir/$dump_name.sha256"
  echo "Verified backup: $output_dir/$dump_name"
done

echo "PostgreSQL backup completed. Copy this backup set to physically separate storage."
