\set ON_ERROR_STOP on

BEGIN;

SET ROLE weather_owner;

GRANT UPDATE (description, updated_at) ON simulation.scenario TO weather_ingest;

RESET ROLE;

INSERT INTO app.schema_migration (migration_name, checksum)
VALUES (:'migration_name', :'migration_checksum');

COMMIT;
