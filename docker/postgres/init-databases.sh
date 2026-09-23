#!/usr/bin/env bash
set -euo pipefail

weather_api_password=${WEATHER_API_PASSWORD:-}
weather_tiles_password=${WEATHER_TILES_PASSWORD:-}
weather_ingest_password=${WEATHER_INGEST_PASSWORD:-}
weather_readonly_password=${WEATHER_READONLY_PASSWORD:-}
weather_backup_password=${WEATHER_BACKUP_PASSWORD:-}

psql --set ON_ERROR_STOP=1 \
  --username "$POSTGRES_USER" \
  --dbname "$POSTGRES_DB" \
  --variable airflow_password="$AIRFLOW_DB_PASSWORD" \
  --variable migrator_password="$WEATHER_MIGRATOR_PASSWORD" <<'SQL'
SELECT format('CREATE ROLE weather_airflow LOGIN PASSWORD %L', :'airflow_password')
WHERE NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'weather_airflow')
\gexec

SELECT 'CREATE DATABASE weather_airflow OWNER weather_airflow'
WHERE NOT EXISTS (SELECT FROM pg_catalog.pg_database WHERE datname = 'weather_airflow')
\gexec

SELECT format('CREATE ROLE weather_migrator LOGIN PASSWORD %L', :'migrator_password')
WHERE NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'weather_migrator')
\gexec

SELECT 'CREATE DATABASE weather_app OWNER weather_migrator'
WHERE NOT EXISTS (SELECT FROM pg_catalog.pg_database WHERE datname = 'weather_app')
\gexec
SQL

# Role creation is a privileged cluster bootstrap operation. Runtime migrations
# connect as weather_migrator and intentionally cannot create or alter roles.
psql --set ON_ERROR_STOP=1 \
  --username "$POSTGRES_USER" \
  --dbname weather_app \
  --variable migrator_password="$WEATHER_MIGRATOR_PASSWORD" \
  --variable api_password="$weather_api_password" \
  --variable tiles_password="$weather_tiles_password" \
  --variable ingest_password="$weather_ingest_password" \
  --variable readonly_password="$weather_readonly_password" \
  --variable backup_password="$weather_backup_password" <<'SQL'
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

SELECT 'CREATE ROLE weather_owner NOLOGIN'
WHERE NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'weather_owner')
\gexec

SELECT format('CREATE ROLE weather_api LOGIN PASSWORD %L', :'api_password')
WHERE NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'weather_api')
\gexec

SELECT format('CREATE ROLE weather_tiles LOGIN PASSWORD %L', :'tiles_password')
WHERE NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'weather_tiles')
\gexec

SELECT format('CREATE ROLE weather_ingest LOGIN PASSWORD %L', :'ingest_password')
WHERE NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'weather_ingest')
\gexec

SELECT format('CREATE ROLE weather_readonly LOGIN PASSWORD %L', :'readonly_password')
WHERE NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'weather_readonly')
\gexec

SELECT format('CREATE ROLE weather_backup LOGIN PASSWORD %L', :'backup_password')
WHERE NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'weather_backup')
\gexec

ALTER ROLE weather_migrator NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
ALTER ROLE weather_api NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
ALTER ROLE weather_tiles NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
ALTER ROLE weather_ingest NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
ALTER ROLE weather_readonly NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
ALTER ROLE weather_backup NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;

GRANT weather_owner TO weather_migrator;

ALTER ROLE weather_migrator IN DATABASE weather_app SET search_path = pg_catalog, public;
ALTER ROLE weather_api IN DATABASE weather_app SET search_path = pg_catalog, public;
ALTER ROLE weather_tiles IN DATABASE weather_app SET search_path = pg_catalog, public;
ALTER ROLE weather_ingest IN DATABASE weather_app SET search_path = pg_catalog, public;
ALTER ROLE weather_readonly IN DATABASE weather_app SET search_path = pg_catalog, public;
ALTER ROLE weather_backup IN DATABASE weather_app SET search_path = pg_catalog, public;
SQL
