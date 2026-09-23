\set ON_ERROR_STOP on

-- This file must be run by a PostgreSQL administrator. Application migrations
-- deliberately run as weather_migrator, which never receives CREATEROLE.

\if :{?migrator_password}
\else
\set migrator_password ''
\endif
\if :{?api_password}
\else
\set api_password ''
\endif
\if :{?tiles_password}
\else
\set tiles_password ''
\endif
\if :{?ingest_password}
\else
\set ingest_password ''
\endif
\if :{?readonly_password}
\else
\set readonly_password ''
\endif
\if :{?backup_password}
\else
\set backup_password ''
\endif

SELECT 'CREATE ROLE weather_owner NOLOGIN'
WHERE NOT EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'weather_owner')
\gexec
SELECT 'CREATE ROLE weather_migrator LOGIN'
WHERE NOT EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'weather_migrator')
\gexec
SELECT 'CREATE ROLE weather_api LOGIN'
WHERE NOT EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'weather_api')
\gexec
SELECT 'CREATE ROLE weather_tiles LOGIN'
WHERE NOT EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'weather_tiles')
\gexec
SELECT 'CREATE ROLE weather_ingest LOGIN'
WHERE NOT EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'weather_ingest')
\gexec
SELECT 'CREATE ROLE weather_readonly LOGIN'
WHERE NOT EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'weather_readonly')
\gexec
SELECT 'CREATE ROLE weather_backup LOGIN'
WHERE NOT EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'weather_backup')
\gexec

ALTER ROLE weather_owner NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
ALTER ROLE weather_migrator LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
ALTER ROLE weather_api LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
ALTER ROLE weather_tiles LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
ALTER ROLE weather_ingest LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
ALTER ROLE weather_readonly LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
ALTER ROLE weather_backup LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;

SELECT format('ALTER ROLE weather_migrator PASSWORD %L', :'migrator_password')
WHERE btrim(:'migrator_password') <> ''
\gexec
SELECT format('ALTER ROLE weather_api PASSWORD %L', :'api_password')
WHERE btrim(:'api_password') <> ''
\gexec
SELECT format('ALTER ROLE weather_tiles PASSWORD %L', :'tiles_password')
WHERE btrim(:'tiles_password') <> ''
\gexec
SELECT format('ALTER ROLE weather_ingest PASSWORD %L', :'ingest_password')
WHERE btrim(:'ingest_password') <> ''
\gexec
SELECT format('ALTER ROLE weather_readonly PASSWORD %L', :'readonly_password')
WHERE btrim(:'readonly_password') <> ''
\gexec
SELECT format('ALTER ROLE weather_backup PASSWORD %L', :'backup_password')
WHERE btrim(:'backup_password') <> ''
\gexec

GRANT weather_owner TO weather_migrator;

ALTER ROLE weather_migrator IN DATABASE weather_app SET search_path = pg_catalog, public;
ALTER ROLE weather_api IN DATABASE weather_app SET search_path = pg_catalog, public;
ALTER ROLE weather_tiles IN DATABASE weather_app SET search_path = pg_catalog, public;
ALTER ROLE weather_ingest IN DATABASE weather_app SET search_path = pg_catalog, public;
ALTER ROLE weather_readonly IN DATABASE weather_app SET search_path = pg_catalog, public;
ALTER ROLE weather_backup IN DATABASE weather_app SET search_path = pg_catalog, public;
