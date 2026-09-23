\set ON_ERROR_STOP on

BEGIN;

SET ROLE weather_owner;

UPDATE catalogue.product
SET retention_config = retention_config || jsonb_build_object(
        'interactive_days', 30,
        'operational_days', 14,
        'retain_scientific_artifacts', true
    ),
    updated_at = clock_timestamp()
WHERE code = 'flexpart_smoke';

RESET ROLE;

INSERT INTO app.schema_migration (migration_name, checksum)
VALUES (:'migration_name', :'migration_checksum');

COMMIT;
