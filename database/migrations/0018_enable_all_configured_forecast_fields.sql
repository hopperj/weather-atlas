\set ON_ERROR_STOP on

BEGIN;

SET ROLE weather_owner;

-- Every configured HRDPS, RDPS, and GDPS mapping has now been verified against
-- the live 2026-07-22 archive at forecast hours 000 and 001. Activate the full
-- reviewed catalogue for download, COG processing, and display.
UPDATE catalogue.product_field AS product_field
SET download_enabled = true,
    processing_enabled = true,
    displayable = true,
    metadata = product_field.metadata || jsonb_build_object(
        'all_fields_activated_at', '2026-07-22T12:30:00Z',
        'processing_pipeline', 'validated_grib2_to_cog'
    ),
    updated_at = clock_timestamp()
FROM catalogue.product AS product
WHERE product.id = product_field.product_id
  AND product.code IN ('gdps', 'hrdps', 'rdps');

DO $$
BEGIN
    IF (
        SELECT count(*)
        FROM catalogue.product_field AS product_field
        JOIN catalogue.product AS product ON product.id = product_field.product_id
        WHERE product.code IN ('gdps', 'hrdps', 'rdps')
          AND product_field.download_enabled
          AND product_field.processing_enabled
          AND product_field.displayable
    ) <> 30 THEN
        RAISE EXCEPTION 'expected all 30 deterministic forecast fields to be enabled';
    END IF;
END
$$;

RESET ROLE;

INSERT INTO app.schema_migration (migration_name, checksum)
VALUES (:'migration_name', :'migration_checksum');

COMMIT;
