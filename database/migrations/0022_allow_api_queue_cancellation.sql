\set ON_ERROR_STOP on

BEGIN;

SET ROLE weather_owner;

GRANT UPDATE (status, cancellation_requested_at, completed_at)
    ON simulation.run TO weather_api;

RESET ROLE;

INSERT INTO app.schema_migration (migration_name, checksum)
VALUES (:'migration_name', :'migration_checksum');

COMMIT;
