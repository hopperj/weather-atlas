\set ON_ERROR_STOP on

BEGIN;

CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE SCHEMA IF NOT EXISTS app AUTHORIZATION weather_migrator;

CREATE TABLE app.schema_migration (
    migration_name text PRIMARY KEY,
    checksum text NOT NULL CHECK (checksum ~ '^[0-9a-f]{64}$'),
    applied_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    applied_by text NOT NULL DEFAULT current_user
);

ALTER TABLE app.schema_migration OWNER TO weather_migrator;

INSERT INTO app.schema_migration (migration_name, checksum)
VALUES (:'migration_name', :'migration_checksum');

COMMIT;

