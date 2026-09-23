\set ON_ERROR_STOP on

BEGIN;

SET ROLE weather_owner;

ALTER TABLE catalogue.product_run
    ADD COLUMN simulation_run_id uuid REFERENCES simulation.run (id) ON DELETE RESTRICT;

CREATE UNIQUE INDEX product_run_simulation_uk
    ON catalogue.product_run (simulation_run_id)
    WHERE simulation_run_id IS NOT NULL;

GRANT SELECT ON simulation.model_build, simulation.scenario,
    simulation.scenario_revision, simulation.run, simulation.run_input,
    simulation.run_artifact TO weather_tiles;
GRANT USAGE ON SCHEMA simulation TO weather_tiles;

RESET ROLE;

INSERT INTO app.schema_migration (migration_name, checksum)
VALUES (:'migration_name', :'migration_checksum');

COMMIT;
