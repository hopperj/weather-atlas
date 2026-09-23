\set ON_ERROR_STOP on

BEGIN;

SET ROLE weather_owner;

INSERT INTO catalogue.provider (
    code,
    name,
    base_url,
    documentation_url,
    enabled
)
VALUES (
    'eccc',
    'Environment and Climate Change Canada',
    'https://dd.weather.gc.ca/',
    'https://eccc-msc.github.io/open-data/msc-datamart/readme_en/',
    true
);

INSERT INTO catalogue.product (
    provider_id,
    code,
    name,
    description,
    product_kind,
    enabled,
    priority,
    schedule_config,
    retention_config
)
SELECT
    provider.id,
    seed.code,
    seed.name,
    seed.description,
    seed.product_kind,
    true,
    seed.priority,
    '{"ingestion_enabled": false, "live_inventory_required": true}'::jsonb,
    jsonb_build_object(
        'raw_days', 30,
        'processed_days', seed.processed_days,
        'capacity_review_required', true
    )
FROM catalogue.provider AS provider
CROSS JOIN (
    VALUES
        ('hrdps', 'High Resolution Deterministic Prediction System',
            'Pan-Canadian high-resolution deterministic atmospheric forecast.',
            'forecast', 1, 180),
        ('raqdps', 'Regional Air Quality Deterministic Prediction System',
            'Regional deterministic air-quality forecast.',
            'forecast', 2, 180),
        ('rdps', 'Regional Deterministic Prediction System',
            'Regional deterministic atmospheric forecast.',
            'forecast', 3, 365),
        ('gdps', 'Global Deterministic Prediction System',
            'Global deterministic atmospheric forecast.',
            'forecast', 4, 365),
        ('hrdpa', 'High Resolution Deterministic Precipitation Analysis',
            'High-resolution precipitation analysis.',
            'analysis', 5, 180),
        ('rdpa', 'Regional Deterministic Precipitation Analysis',
            'Regional precipitation analysis.',
            'analysis', 6, 180),
        ('hrepa', 'High Resolution Ensemble Precipitation Analysis',
            'High-resolution ensemble precipitation analysis.',
            'ensemble_analysis', 7, 180)
) AS seed(code, name, description, product_kind, priority, processed_days)
WHERE provider.code = 'eccc';

INSERT INTO catalogue.vertical_level (
    code,
    name,
    level_type,
    level_value,
    unit,
    display_order
)
VALUES
    ('surface', 'Surface', 'surface', NULL, NULL, 10),
    ('2m_agl', '2 metres above ground', 'height_above_ground', 2, 'm', 20),
    ('10m_agl', '10 metres above ground', 'height_above_ground', 10, 'm', 30),
    ('850_hpa', '850 hPa', 'isobaric', 850, 'hPa', 100),
    ('700_hpa', '700 hPa', 'isobaric', 700, 'hPa', 110),
    ('500_hpa', '500 hPa', 'isobaric', 500, 'hPa', 120);

INSERT INTO catalogue.variable (
    code,
    name,
    description,
    variable_class,
    canonical_unit,
    value_kind,
    is_vector_component,
    vector_group,
    metadata
)
VALUES
    ('air_temperature', 'Air temperature', '', 'atmosphere', 'Cel',
        'continuous', false, NULL, '{}'::jsonb),
    ('relative_humidity', 'Relative humidity', '', 'atmosphere', '%',
        'continuous', false, NULL, '{}'::jsonb),
    ('total_cloud_cover', 'Total cloud cover', '', 'atmosphere', '%',
        'continuous', false, NULL, '{}'::jsonb),
    ('surface_pressure', 'Surface pressure', '', 'atmosphere', 'hPa',
        'continuous', false, NULL, '{}'::jsonb),
    ('mean_sea_level_pressure', 'Mean sea-level pressure', '', 'atmosphere', 'hPa',
        'continuous', false, NULL, '{}'::jsonb),
    ('wind_u', 'Eastward wind component', '', 'atmosphere', 'm s-1',
        'vector_component', true, 'wind', '{}'::jsonb),
    ('wind_v', 'Northward wind component', '', 'atmosphere', 'm s-1',
        'vector_component', true, 'wind', '{}'::jsonb),
    ('wind_speed', 'Wind speed', 'Derived from matched U and V components.',
        'atmosphere', 'm s-1', 'continuous', false, NULL, '{"derived": true}'::jsonb),
    ('wind_direction', 'Wind direction', 'Meteorological direction from true north.',
        'atmosphere', 'degree', 'continuous', false, NULL, '{"derived": true}'::jsonb),
    ('wind_gust', 'Wind gust', '', 'atmosphere', 'm s-1',
        'continuous', false, NULL, '{}'::jsonb),
    ('visibility', 'Visibility', '', 'atmosphere', 'km',
        'continuous', false, NULL, '{}'::jsonb),
    ('total_precipitation', 'Total precipitation',
        'Accumulation interval is retained on each product time.',
        'precipitation', 'mm', 'continuous', false, NULL, '{}'::jsonb),
    ('snowfall', 'Snowfall',
        'Source semantics and conversion must be verified before a product field is enabled.',
        'precipitation', 'mm', 'continuous', false, NULL,
        '{"requires_source_semantics_review": true}'::jsonb),
    ('precipitation_type', 'Precipitation type', '', 'precipitation', 'category',
        'categorical', false, NULL, '{}'::jsonb),
    ('pm25', 'Fine particulate matter (PM2.5)', '', 'air_quality', 'ug m-3',
        'continuous', false, NULL, '{}'::jsonb),
    ('pm10', 'Particulate matter (PM10)', '', 'air_quality', 'ug m-3',
        'continuous', false, NULL, '{}'::jsonb),
    ('ozone', 'Ozone',
        'Canonical concentration unit must be confirmed by each source mapping.',
        'air_quality', 'ppbv', 'continuous', false, NULL,
        '{"requires_source_unit_review": true}'::jsonb),
    ('nitrogen_dioxide', 'Nitrogen dioxide',
        'Canonical concentration unit must be confirmed by each source mapping.',
        'air_quality', 'ppbv', 'continuous', false, NULL,
        '{"requires_source_unit_review": true}'::jsonb),
    ('sulfur_dioxide', 'Sulfur dioxide',
        'Canonical concentration unit must be confirmed by each source mapping.',
        'air_quality', 'ppbv', 'continuous', false, NULL,
        '{"requires_source_unit_review": true}'::jsonb),
    ('carbon_monoxide', 'Carbon monoxide',
        'Canonical concentration unit must be confirmed by each source mapping.',
        'air_quality', 'ppbv', 'continuous', false, NULL,
        '{"requires_source_unit_review": true}'::jsonb),
    ('aqhi', 'Air Quality Health Index', '', 'air_quality', '1',
        'index', false, NULL, '{}'::jsonb);

INSERT INTO display.palette (code, name, description, revision, definition)
VALUES
    ('temperature', 'Temperature', 'Continuous temperature display ramp.', 1,
        '{"interpolation":"linear","stops":[{"value":-40,"color":"#582a9f"},{"value":-20,"color":"#2d79c7"},{"value":0,"color":"#73d7e8"},{"value":15,"color":"#8bd646"},{"value":25,"color":"#ffd447"},{"value":40,"color":"#b40426"}]}'::jsonb),
    ('percent', 'Percentage', 'Continuous zero-to-one-hundred ramp.', 1,
        '{"interpolation":"linear","stops":[{"value":0,"color":"#ffffff00"},{"value":25,"color":"#d9e8f5"},{"value":50,"color":"#90b9d6"},{"value":75,"color":"#4d7ea8"},{"value":100,"color":"#1f365c"}]}'::jsonb),
    ('pressure', 'Pressure', 'Mean sea-level and surface pressure ramp.', 1,
        '{"interpolation":"linear","stops":[{"value":940,"color":"#54278f"},{"value":980,"color":"#2b8cbe"},{"value":1010,"color":"#7bccc4"},{"value":1030,"color":"#fdae61"},{"value":1060,"color":"#d73027"}]}'::jsonb),
    ('wind_speed', 'Wind speed', 'Continuous wind-speed ramp.', 1,
        '{"interpolation":"linear","stops":[{"value":0,"color":"#f7fcf0"},{"value":5,"color":"#ccebc5"},{"value":10,"color":"#7bccc4"},{"value":20,"color":"#2b8cbe"},{"value":40,"color":"#7a0177"}]}'::jsonb),
    ('precipitation', 'Precipitation', 'Threshold-oriented accumulated precipitation ramp.', 1,
        '{"interpolation":"step","stops":[{"value":0,"color":"#ffffff00"},{"value":0.2,"color":"#d9f0ff"},{"value":2,"color":"#74a9cf"},{"value":10,"color":"#238b45"},{"value":25,"color":"#fec44f"},{"value":50,"color":"#d7301f"}]}'::jsonb),
    ('visibility', 'Visibility', 'Continuous visibility ramp.', 1,
        '{"interpolation":"linear","stops":[{"value":0,"color":"#4d004b"},{"value":2,"color":"#88419d"},{"value":10,"color":"#8c96c6"},{"value":25,"color":"#b3cde3"},{"value":50,"color":"#f7fcfd"}]}'::jsonb),
    ('concentration', 'Concentration',
        'Generic concentration ramp; it does not encode regulatory or health thresholds.', 1,
        '{"interpolation":"linear","stops":[{"value":0,"color":"#f7fcf5"},{"value":10,"color":"#c7e9c0"},{"value":25,"color":"#74c476"},{"value":50,"color":"#238b45"},{"value":100,"color":"#54278f"}]}'::jsonb);

INSERT INTO display.variable_style (
    variable_id,
    product_field_id,
    palette_id,
    code,
    name,
    revision,
    default_min,
    default_max,
    scale_type,
    clamp_values,
    opacity,
    resampling_method,
    legend_precision,
    nodata_transparent,
    metadata
)
SELECT
    variable.id,
    NULL,
    palette.id,
    'default',
    style.name,
    1,
    style.default_min,
    style.default_max,
    style.scale_type,
    true,
    0.8,
    style.resampling_method,
    style.legend_precision,
    true,
    '{}'::jsonb
FROM (
    VALUES
        ('air_temperature', 'temperature', 'Default temperature', -40.0, 40.0, 'linear', 'bilinear', 1),
        ('relative_humidity', 'percent', 'Default relative humidity', 0.0, 100.0, 'linear', 'bilinear', 0),
        ('total_cloud_cover', 'percent', 'Default cloud cover', 0.0, 100.0, 'linear', 'average', 0),
        ('surface_pressure', 'pressure', 'Default surface pressure', 940.0, 1060.0, 'linear', 'bilinear', 0),
        ('mean_sea_level_pressure', 'pressure', 'Default mean sea-level pressure', 940.0, 1060.0, 'linear', 'bilinear', 0),
        ('wind_speed', 'wind_speed', 'Default wind speed', 0.0, 40.0, 'linear', 'bilinear', 1),
        ('wind_gust', 'wind_speed', 'Default wind gust', 0.0, 50.0, 'linear', 'bilinear', 1),
        ('visibility', 'visibility', 'Default visibility', 0.0, 50.0, 'linear', 'bilinear', 1),
        ('total_precipitation', 'precipitation', 'Default total precipitation', 0.0, 50.0, 'threshold', 'nearest', 1),
        ('snowfall', 'precipitation', 'Default snowfall', 0.0, 50.0, 'threshold', 'nearest', 1),
        ('pm25', 'concentration', 'Default PM2.5 concentration', 0.0, 100.0, 'linear', 'bilinear', 1),
        ('pm10', 'concentration', 'Default PM10 concentration', 0.0, 150.0, 'linear', 'bilinear', 1),
        ('ozone', 'concentration', 'Default ozone concentration', 0.0, 100.0, 'linear', 'bilinear', 1),
        ('nitrogen_dioxide', 'concentration', 'Default nitrogen dioxide concentration', 0.0, 100.0, 'linear', 'bilinear', 1),
        ('sulfur_dioxide', 'concentration', 'Default sulfur dioxide concentration', 0.0, 100.0, 'linear', 'bilinear', 1),
        ('carbon_monoxide', 'concentration', 'Default carbon monoxide concentration', 0.0, 100.0, 'linear', 'bilinear', 1)
) AS style(
    variable_code,
    palette_code,
    name,
    default_min,
    default_max,
    scale_type,
    resampling_method,
    legend_precision
)
JOIN catalogue.variable AS variable ON variable.code = style.variable_code
JOIN display.palette AS palette ON palette.code = style.palette_code AND palette.revision = 1;

RESET ROLE;

INSERT INTO app.schema_migration (migration_name, checksum)
VALUES (:'migration_name', :'migration_checksum');

COMMIT;
