\set ON_ERROR_STOP on

BEGIN;

SET ROLE weather_owner;

-- Analysis products legitimately publish several revisions and accumulation
-- windows for the same canonical variable and level. Their configured field
-- code is the public display identity.
DROP INDEX catalogue.product_field_display_identity_uk;

CREATE UNIQUE INDEX product_field_display_identity_uk
    ON catalogue.product_field (
        product_id,
        COALESCE(
            metadata ->> 'field_code',
            variable_id::text || ':' || vertical_level_id::text
        )
    )
    WHERE displayable;

-- Retain every configured deterministic analysis variant. "6h" and "24h"
-- are accumulation windows, not forecast limits, and every valid time remains
-- part of the historical archive.
UPDATE catalogue.product_field AS product_field
SET download_enabled = true,
    processing_enabled = true,
    displayable = true,
    metadata = (product_field.metadata - 'retention_policy')
        || jsonb_build_object(
            'retention_policy', 'historical_archive'
        ),
    updated_at = clock_timestamp()
FROM catalogue.product AS product
WHERE product.id = product_field.product_id
  AND product.code IN ('hrdpa', 'rdpa');

UPDATE catalogue.product_run AS product_run
SET expected_asset_count = CASE
        WHEN EXTRACT(hour FROM product_run.run_time AT TIME ZONE 'UTC') IN (6, 12)
            THEN 4
        ELSE 2
    END,
    updated_at = clock_timestamp()
FROM catalogue.product AS product
WHERE product.id = product_run.product_id
  AND product.code IN ('hrdpa', 'rdpa')
  AND product_run.processing_status <> 'expired';

RESET ROLE;

INSERT INTO app.schema_migration (migration_name, checksum)
VALUES (:'migration_name', :'migration_checksum');

COMMIT;
