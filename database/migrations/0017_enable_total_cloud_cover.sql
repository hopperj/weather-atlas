\set ON_ERROR_STOP on

BEGIN;

SET ROLE weather_owner;

-- The source mappings, percent units, COG conversion, transparent-clear-sky
-- palette, and display styles were registered in migration 0008. Activate the
-- reviewed total-cloud-cover field for every deterministic forecast product.
UPDATE catalogue.product_field AS product_field
SET download_enabled = true,
    processing_enabled = true,
    displayable = true,
    metadata = product_field.metadata || jsonb_build_object(
        'processing_activated_at', '2026-07-22T12:00:00Z',
        'processing_pipeline', 'validated_grib2_to_cog'
    ),
    updated_at = clock_timestamp()
FROM catalogue.product AS product
WHERE product.id = product_field.product_id
  AND product.code IN ('gdps', 'hrdps', 'rdps')
  AND product_field.metadata ->> 'field_code' = 'total_cloud_cover';

DO $$
BEGIN
    IF (
        SELECT count(*)
        FROM catalogue.product_field AS product_field
        JOIN catalogue.product AS product ON product.id = product_field.product_id
        WHERE product.code IN ('gdps', 'hrdps', 'rdps')
          AND product_field.metadata ->> 'field_code' = 'total_cloud_cover'
          AND product_field.download_enabled
          AND product_field.processing_enabled
          AND product_field.displayable
    ) <> 3 THEN
        RAISE EXCEPTION 'expected three enabled total-cloud-cover fields';
    END IF;
END
$$;

RESET ROLE;

INSERT INTO app.schema_migration (migration_name, checksum)
VALUES (:'migration_name', :'migration_checksum');

COMMIT;
