#!/usr/bin/env bash
set -euo pipefail

script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
repo_root=$(cd "$script_dir/.." && pwd)

usage() {
  echo "Usage: $0 [--yes] PATH_TO_MIGRATION.sql"
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

assume_yes=false
if [[ "${1:-}" == "--yes" ]]; then
  assume_yes=true
  shift
fi

if [[ $# -ne 1 ]]; then
  usage
  exit 2
fi

migration_file=$1
if [[ ! -f "$migration_file" || "$migration_file" != *.sql ]]; then
  echo "Migration must be an existing .sql file: $migration_file" >&2
  exit 2
fi
migration_file=$(cd "$(dirname "$migration_file")" && pwd)/$(basename "$migration_file")

if [[ -f "$repo_root/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$repo_root/.env"
  set +a
fi

migration_name=$(basename "$migration_file")
if [[ ! "$migration_name" =~ ^[A-Za-z0-9._-]+$ ]]; then
  echo "Migration filename contains unsupported characters: $migration_name" >&2
  exit 2
fi
migration_checksum=$(sha256_file "$migration_file")
expected_database=${WEATHER_APP_DATABASE:-weather_app}
migrator_user=${WEATHER_MIGRATOR_USER:-weather_migrator}

psql_command=(
  docker compose --project-directory "$repo_root" --file "$repo_root/compose.yaml" exec -T
  -e "PGPASSWORD=${WEATHER_MIGRATOR_PASSWORD:?WEATHER_MIGRATOR_PASSWORD must be set in .env}"
  postgres psql
  --host 127.0.0.1
  --username "$migrator_user"
  --dbname "$expected_database"
  --set ON_ERROR_STOP=1
)

connection_identity=$("${psql_command[@]}" --tuples-only --no-align --command \
  "SELECT current_database() || '|' || current_user || '|' || inet_server_addr()::text || '|' || inet_server_port()::text;")

IFS='|' read -r actual_database actual_user actual_host actual_port <<<"$connection_identity"
if [[ "$actual_database" != "$expected_database" ]]; then
  echo "Refusing unidentified database. Expected '$expected_database', got '$actual_database'." >&2
  exit 1
fi
if [[ "$actual_user" != "$migrator_user" ]]; then
  echo "Refusing unexpected database user. Expected '$migrator_user', got '$actual_user'." >&2
  exit 1
fi

echo "Target database: $actual_database"
echo "Server:          $actual_host:$actual_port"
echo "Database user:   $actual_user"
echo "Migration:       $migration_name"
echo "SHA-256:         $migration_checksum"

tracking_exists=$("${psql_command[@]}" --tuples-only --no-align --command \
  "SELECT to_regclass('app.schema_migration') IS NOT NULL;")

if [[ "$tracking_exists" == "t" ]]; then
  applied_checksum=$("${psql_command[@]}" \
    --variable migration_name="$migration_name" \
    --tuples-only --no-align \
    --command "SELECT checksum FROM app.schema_migration WHERE migration_name = '$migration_name';")

  if [[ -n "$applied_checksum" ]]; then
    if [[ "$applied_checksum" != "$migration_checksum" ]]; then
      echo "Refusing changed migration: recorded checksum is $applied_checksum" >&2
      exit 1
    fi
    echo "Migration is already applied; no changes made." >&2
    # The directory runner distinguishes this safe no-op from a newly applied
    # migration while still treating it as success for the overall batch.
    # Keep this distinct from psql's fatal-error exit status (3).
    exit 10
  fi
fi

if [[ "$assume_yes" != true ]]; then
  read -r -p "Apply this migration? Type 'yes' to continue: " confirmation
  if [[ "$confirmation" != "yes" ]]; then
    echo "Migration cancelled."
    exit 1
  fi
fi

"${psql_command[@]}" \
  --variable migration_name="$migration_name" \
  --variable migration_checksum="$migration_checksum" \
  < "$migration_file"

recorded_checksum=$("${psql_command[@]}" \
  --variable migration_name="$migration_name" \
  --tuples-only --no-align \
  --command "SELECT checksum FROM app.schema_migration WHERE migration_name = '$migration_name';")

if [[ "$recorded_checksum" != "$migration_checksum" ]]; then
  echo "Post-migration verification failed." >&2
  exit 1
fi

echo "Migration applied and verified."
