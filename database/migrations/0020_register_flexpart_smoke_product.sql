\set ON_ERROR_STOP on

BEGIN;

SET ROLE weather_owner;

INSERT INTO catalogue.provider (code, name, base_url, documentation_url, enabled)
VALUES (
    'local_research', 'Local research models', 'https://localhost.invalid/models',
    'https://www.flexpart.eu/', true
)
ON CONFLICT (code) DO NOTHING;

INSERT INTO catalogue.product (
    provider_id, code, name, description, product_kind, enabled, priority,
    schedule_config, retention_config
)
SELECT provider.id, 'flexpart_smoke', 'FLEXPART wildfire smoke',
    'Research estimate of primary wildfire emissions transported by FLEXPART; not an official forecast.',
    'forecast', true, 40,
    '{"schedule":"disabled_pending_validation","cycles_per_day":4}'::jsonb,
    '{"retain_runs":16,"retain_scientific_artifacts":true}'::jsonb
FROM catalogue.provider WHERE code = 'local_research'
ON CONFLICT (code) DO NOTHING;

INSERT INTO catalogue.domain (
    product_id, code, name, native_crs, source_grid_metadata, enabled
)
SELECT product.id, 'scenario_domain', 'Scenario-defined smoke domain', 'EPSG:4326',
    '{"variable_extent":true,"allowed_spacing_degrees":[0.25,0.5,1.0]}'::jsonb, true
FROM catalogue.product WHERE code = 'flexpart_smoke'
ON CONFLICT (product_id, code) DO NOTHING;

INSERT INTO catalogue.vertical_level (code, name, level_type, level_value, unit, display_order)
VALUES
    ('smoke_surface', 'Lowest FLEXPART output layer', 'model_layer', 1, '1', 15),
    ('atmospheric_column', 'Atmospheric column', 'column', NULL, NULL, 200),
    ('plume_injection', 'Emission-weighted plume injection', 'diagnostic', NULL, NULL, 210)
ON CONFLICT (code) DO NOTHING;

INSERT INTO catalogue.variable (
    code, name, description, variable_class, canonical_unit, value_kind, metadata
)
VALUES
    ('wildfire_pm25', 'Primary wildfire PM2.5', 'Primary PM2.5 attributable to configured wildfire emissions.', 'air_quality', 'ug m-3', 'continuous', '{"primary_emissions_only":true}'::jsonb),
    ('wildfire_co', 'Wildfire carbon monoxide', 'CO attributable to configured wildfire emissions.', 'air_quality', 'ug m-3', 'continuous', '{"primary_emissions_only":true}'::jsonb),
    ('wildfire_bc', 'Wildfire black carbon', 'Black carbon attributable to configured wildfire emissions.', 'air_quality', 'ug m-3', 'continuous', '{"primary_emissions_only":true}'::jsonb),
    ('wildfire_pm25_column', 'Wildfire PM2.5 column burden', 'Vertically integrated primary wildfire PM2.5.', 'air_quality', 'mg m-2', 'continuous', '{"primary_emissions_only":true}'::jsonb),
    ('wildfire_pm25_wet_deposition', 'Wildfire PM2.5 wet deposition', 'Accumulated FLEXPART wet deposition.', 'air_quality', 'mg m-2', 'continuous', '{"primary_emissions_only":true}'::jsonb),
    ('wildfire_pm25_dry_deposition', 'Wildfire PM2.5 dry deposition', 'Accumulated FLEXPART dry deposition.', 'air_quality', 'mg m-2', 'continuous', '{"primary_emissions_only":true}'::jsonb),
    ('wildfire_injection_height', 'Wildfire injection height', 'Emission-weighted plume injection height.', 'air_quality', 'm', 'continuous', '{"datum":"AGL"}'::jsonb)
ON CONFLICT (code) DO NOTHING;

WITH fields(variable_code, level_code, field_code) AS (
    VALUES
        ('wildfire_pm25', 'smoke_surface', 'wildfire_pm25_surface'),
        ('wildfire_co', 'smoke_surface', 'wildfire_co_surface'),
        ('wildfire_bc', 'smoke_surface', 'wildfire_bc_surface'),
        ('wildfire_pm25_column', 'atmospheric_column', 'wildfire_pm25_column'),
        ('wildfire_pm25_wet_deposition', 'smoke_surface', 'wildfire_pm25_wet_deposition'),
        ('wildfire_pm25_dry_deposition', 'smoke_surface', 'wildfire_pm25_dry_deposition'),
        ('wildfire_injection_height', 'plume_injection', 'wildfire_injection_height')
)
INSERT INTO catalogue.product_field (
    product_id, variable_id, vertical_level_id, source_parameter,
    source_producer, source_level_type, source_level_value, source_unit, conversion_key,
    displayable, download_enabled, processing_enabled, metadata
)
SELECT product.id, variable.id, vertical_level.id, fields.field_code,
    'FLEXPART', 'derived', NULL, variable.canonical_unit, 'identity', true, true, true,
    jsonb_build_object(
        'field_code', fields.field_code,
        'model', 'FLEXPART 11.1',
        'emissions_model', 'CFFEPS 4.1',
        'primary_emissions_only', true
    )
FROM fields
JOIN catalogue.product AS product ON product.code = 'flexpart_smoke'
JOIN catalogue.variable AS variable ON variable.code = fields.variable_code
JOIN catalogue.vertical_level ON vertical_level.code = fields.level_code
ON CONFLICT DO NOTHING;

INSERT INTO display.palette (code, name, description, revision, definition)
VALUES
    ('smoke_concentration', 'Wildfire smoke concentration', 'Log-oriented primary-smoke concentration ramp.', 1,
     '{"interpolation":"linear","stops":[{"value":0,"color":"#ffffff00"},{"value":1,"color":"#ffffcc"},{"value":5,"color":"#fd8d3c"},{"value":25,"color":"#e31a1c"},{"value":100,"color":"#800026"}]}'::jsonb),
    ('smoke_burden', 'Wildfire smoke burden', 'Column burden and deposition ramp.', 1,
     '{"interpolation":"linear","stops":[{"value":0,"color":"#ffffff00"},{"value":0.01,"color":"#c7e9c0"},{"value":0.1,"color":"#41ab5d"},{"value":1,"color":"#006d2c"}]}'::jsonb),
    ('plume_height', 'Plume injection height', 'Height above ground in metres.', 1,
     '{"interpolation":"linear","stops":[{"value":0,"color":"#f7fbff"},{"value":1000,"color":"#9ecae1"},{"value":3000,"color":"#4292c6"},{"value":8000,"color":"#084594"}]}'::jsonb)
ON CONFLICT (code, revision) DO NOTHING;

WITH styles(variable_code, palette_code, maximum_value, precision) AS (
    VALUES
        ('wildfire_pm25', 'smoke_concentration', 100.0, 2),
        ('wildfire_co', 'smoke_concentration', 500.0, 2),
        ('wildfire_bc', 'smoke_concentration', 10.0, 3),
        ('wildfire_pm25_column', 'smoke_burden', 1.0, 3),
        ('wildfire_pm25_wet_deposition', 'smoke_burden', 1.0, 3),
        ('wildfire_pm25_dry_deposition', 'smoke_burden', 1.0, 3),
        ('wildfire_injection_height', 'plume_height', 8000.0, 0)
)
INSERT INTO display.variable_style (
    variable_id, product_field_id, palette_id, code, name, revision,
    default_min, default_max, scale_type, clamp_values, opacity,
    resampling_method, legend_precision, nodata_transparent, metadata
)
SELECT variable.id, product_field.id, palette.id, 'default',
    'Default ' || variable.name, 1, 0.0, styles.maximum_value, 'linear', true,
    0.82, 'bilinear', styles.precision, true,
    '{"research_product":true,"primary_emissions_only":true}'::jsonb
FROM styles
JOIN catalogue.variable AS variable ON variable.code = styles.variable_code
JOIN catalogue.product AS product ON product.code = 'flexpart_smoke'
JOIN catalogue.product_field ON product_field.product_id = product.id
    AND product_field.variable_id = variable.id
JOIN display.palette ON palette.code = styles.palette_code AND palette.revision = 1
ON CONFLICT DO NOTHING;

RESET ROLE;

INSERT INTO app.schema_migration (migration_name, checksum)
VALUES (:'migration_name', :'migration_checksum');

COMMIT;
