\set ON_ERROR_STOP on

BEGIN;

SET ROLE weather_owner;

INSERT INTO catalogue.domain (
    product_id,
    code,
    name,
    native_crs,
    grid_resolution_x_m,
    grid_resolution_y_m,
    grid_width,
    grid_height,
    source_grid_metadata,
    enabled
)
SELECT
    product.id,
    'continental',
    'Pan-Canadian continental grid',
    'RLatLon0.0225',
    2500,
    2500,
    2540,
    1290,
    jsonb_build_object(
        'grid', 'RLatLon0.0225',
        'first_grid_point', jsonb_build_array(-134.0, 39.0),
        'documentation_url',
        'https://eccc-msc.github.io/open-data/msc-data/nwp_hrdps/readme_hrdps-datamart_en/'
    ),
    true
FROM catalogue.product
WHERE product.code = 'hrdps';

INSERT INTO catalogue.product_field (
    product_id,
    variable_id,
    vertical_level_id,
    source_parameter,
    source_level_type,
    source_level_value,
    source_unit,
    conversion_key,
    displayable,
    download_enabled,
    processing_enabled,
    metadata
)
SELECT
    product.id,
    variable.id,
    vertical_level.id,
    'TMP',
    'AGL',
    2,
    'K',
    'kelvin_to_celsius',
    true,
    true,
    true,
    jsonb_build_object(
        'field_code', 'air_temperature_2m',
        'source_level', 'AGL-2m',
        'inventory_verified_at', '2026-07-16T00:00:00Z',
        'inventory_frames', 49
    )
FROM catalogue.product
JOIN catalogue.variable ON variable.code = 'air_temperature'
JOIN catalogue.vertical_level ON vertical_level.code = '2m_agl'
WHERE product.code = 'hrdps';

RESET ROLE;

INSERT INTO app.schema_migration (migration_name, checksum)
VALUES (:'migration_name', :'migration_checksum');

COMMIT;
