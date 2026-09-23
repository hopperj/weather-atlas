\set ON_ERROR_STOP on

BEGIN;

SET ROLE weather_owner;

-- Weather model and analysis cycles are an append-only historical archive.
-- Age-based maintenance remains available for products that explicitly opt
-- into it, but it must never select this installation's ECCC payloads.
UPDATE catalogue.product
SET retention_config = retention_config
        || jsonb_build_object('retain_forever', true),
    updated_at = clock_timestamp()
WHERE provider_id = (
    SELECT id
    FROM catalogue.provider
    WHERE code = 'eccc'
);

UPDATE catalogue.product_field AS product_field
SET metadata = (product_field.metadata - 'retention_policy')
        || jsonb_build_object('retention_policy', 'historical_archive'),
    updated_at = clock_timestamp()
FROM catalogue.product AS product
WHERE product.id = product_field.product_id
  AND product.provider_id = (
      SELECT id
      FROM catalogue.provider
      WHERE code = 'eccc'
  );

RESET ROLE;

INSERT INTO app.schema_migration (migration_name, checksum)
VALUES (:'migration_name', :'migration_checksum');

COMMIT;
