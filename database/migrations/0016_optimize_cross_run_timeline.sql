\set ON_ERROR_STOP on

BEGIN;

SET ROLE weather_owner;

CREATE INDEX IF NOT EXISTS product_time_valid_run_idx
    ON catalogue.product_time (valid_time, product_run_id);

CREATE INDEX IF NOT EXISTS asset_available_time_field_idx
    ON catalogue.asset (product_time_id, product_field_id)
    WHERE status = 'available'
      AND asset_role IN ('processed_cog', 'derived_cog');

RESET ROLE;

INSERT INTO app.schema_migration (migration_name, checksum)
VALUES (:'migration_name', :'migration_checksum');

COMMIT;
