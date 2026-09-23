#!/usr/bin/env bash
set -euo pipefail

script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
repo_root=$(cd "$script_dir/.." && pwd)

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

expected_database=${WEATHER_APP_DATABASE:-weather_app}
migrator_user=${WEATHER_MIGRATOR_USER:-weather_migrator}

psql_command=(
  docker compose --project-directory "$repo_root" --file "$repo_root/compose.yaml" exec -T
  -e "PGPASSWORD=${WEATHER_MIGRATOR_PASSWORD:?WEATHER_MIGRATOR_PASSWORD must be set in .env}"
  postgres psql --host 127.0.0.1 --username "$migrator_user" --dbname "$expected_database"
  --set ON_ERROR_STOP=1 --tuples-only --no-align
)

connection_identity=$("${psql_command[@]}" --command \
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

extensions=$("${psql_command[@]}" --command \
  "SELECT extname FROM pg_extension WHERE extname IN ('postgis', 'pgcrypto') ORDER BY extname;")
if [[ "$extensions" != $'pgcrypto\npostgis' ]]; then
  echo "Required extensions are missing. Found: ${extensions:-none}" >&2
  exit 1
fi
echo "verified extensions: pgcrypto, postgis"

tracking_exists=$("${psql_command[@]}" --command \
  "SELECT to_regclass('app.schema_migration') IS NOT NULL;")
if [[ "$tracking_exists" != "t" ]]; then
  echo "Migration tracking table app.schema_migration does not exist." >&2
  exit 1
fi

recorded_migrations=$("${psql_command[@]}" --field-separator='|' --command \
  "SELECT migration_name, checksum FROM app.schema_migration ORDER BY migration_name;")
if [[ -z "$recorded_migrations" ]]; then
  echo "No application migrations are recorded." >&2
  exit 1
fi

while IFS='|' read -r migration_name recorded_checksum; do
  migration_path="$repo_root/database/migrations/$migration_name"
  if [[ ! -f "$migration_path" ]]; then
    echo "Recorded migration file is missing: $migration_name" >&2
    exit 1
  fi
  actual_checksum=$(sha256_file "$migration_path")
  if [[ "$actual_checksum" != "$recorded_checksum" ]]; then
    echo "Checksum mismatch: $migration_name" >&2
    exit 1
  fi
  echo "verified $migration_name"
done <<<"$recorded_migrations"

shopt -s nullglob
migration_files=("$repo_root"/database/migrations/*.sql)
if [[ ${#migration_files[@]} -eq 0 ]]; then
  echo "No migration files exist in database/migrations." >&2
  exit 1
fi

for migration_path in "${migration_files[@]}"; do
  migration_name=$(basename "$migration_path")
  if ! grep -Fq "$migration_name|" <<<"$recorded_migrations"; then
    echo "Migration file has not been applied: $migration_name" >&2
    exit 1
  fi
done

echo "Database verification passed."
