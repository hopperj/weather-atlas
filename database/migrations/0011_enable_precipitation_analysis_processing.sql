\set ON_ERROR_STOP on

BEGIN;

SET ROLE weather_owner;

UPDATE catalogue.product_field AS product_field
SET processing_enabled = true,
    displayable = (
        product_field.metadata ->> 'field_code' = 'precipitation_6h_final'
    ),
    metadata = (product_field.metadata - 'processing_activation_gate')
        || jsonb_build_object(
            'processing_activated_at', '2026-07-17T19:00:00Z',
            'processing_pipeline', 'validated_grib2_to_cog'
        ),
    updated_at = clock_timestamp()
FROM catalogue.product AS product
WHERE product.id = product_field.product_id
  AND product.code IN ('hrdpa', 'rdpa')
  AND product_field.download_enabled;

UPDATE display.variable_style AS style
SET metadata = (style.metadata - 'activation_state')
        || jsonb_build_object('activation_state', 'active'),
    updated_at = clock_timestamp()
FROM catalogue.product_field AS product_field
JOIN catalogue.product ON product.id = product_field.product_id
WHERE style.product_field_id = product_field.id
  AND product.code IN ('hrdpa', 'rdpa');

RESET ROLE;

INSERT INTO app.schema_migration (migration_name, checksum)
VALUES (:'migration_name', :'migration_checksum');

COMMIT;
