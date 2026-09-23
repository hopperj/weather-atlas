\set ON_ERROR_STOP on

BEGIN;

SET ROLE weather_owner;

UPDATE catalogue.product_field AS product_field
SET download_enabled = (
        product_field.metadata ->> 'field_code' = 'precipitation_6h_final'
    ),
    processing_enabled = (
        product_field.metadata ->> 'field_code' = 'precipitation_6h_final'
    ),
    displayable = (
        product_field.metadata ->> 'field_code' = 'precipitation_6h_final'
    ),
    metadata = product_field.metadata || jsonb_build_object(
        'retention_policy', 'latest_displayable_run'
    ),
    updated_at = clock_timestamp()
FROM catalogue.product AS product
WHERE product.id = product_field.product_id
  AND product.code IN ('hrdpa', 'rdpa');

-- The operational configuration now expects one displayable final 6-hour
-- analysis per valid time. Deleted source rows are excluded by finalization,
-- so existing partially published runs can converge cleanly after this change.
UPDATE catalogue.product_run AS product_run
SET expected_asset_count = 1,
    updated_at = clock_timestamp()
FROM catalogue.product AS product
WHERE product.id = product_run.product_id
  AND product.code IN ('hrdpa', 'rdpa')
  AND product_run.processing_status <> 'expired';

RESET ROLE;

INSERT INTO app.schema_migration (migration_name, checksum)
VALUES (:'migration_name', :'migration_checksum');

COMMIT;
