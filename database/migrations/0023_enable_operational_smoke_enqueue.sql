\set ON_ERROR_STOP on

BEGIN;

SET ROLE weather_owner;

CREATE UNIQUE INDEX simulation_system_scenario_identity_uq
    ON simulation.scenario (name)
    WHERE owner_label = 'system' AND archived_at IS NULL;

GRANT INSERT ON simulation.scenario, simulation.scenario_revision TO weather_ingest;

RESET ROLE;

INSERT INTO app.schema_migration (migration_name, checksum)
VALUES (:'migration_name', :'migration_checksum');

COMMIT;
