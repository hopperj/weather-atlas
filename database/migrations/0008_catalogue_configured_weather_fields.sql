\set ON_ERROR_STOP on

BEGIN;

SET ROLE weather_owner;

-- Keep catalogue identifiers and units aligned with the reviewed YAML contract.
-- The initial seed used a more verbose precipitation code and UCUM-like display
-- units; the ingestion configurations are the canonical cross-service contract.
UPDATE catalogue.variable
SET code = 'precipitation',
    canonical_unit = 'mm',
    updated_at = clock_timestamp()
WHERE code = 'total_precipitation';

UPDATE catalogue.variable AS variable
SET canonical_unit = canonical.canonical_unit,
    updated_at = clock_timestamp()
FROM (
    VALUES
        ('air_temperature', 'degC'),
        ('relative_humidity', 'percent'),
        ('total_cloud_cover', 'percent'),
        ('surface_pressure', 'hPa'),
        ('mean_sea_level_pressure', 'hPa'),
        ('wind_u', 'm/s'),
        ('wind_v', 'm/s'),
        ('wind_gust', 'm/s'),
        ('visibility', 'km'),
        ('precipitation', 'mm'),
        ('snowfall', 'mm_water_equivalent'),
        ('pm25', 'ug/m^3'),
        ('pm10', 'ug/m^3'),
        ('ozone', 'ppb'),
        ('nitrogen_dioxide', 'ppb'),
        ('sulfur_dioxide', 'ppb')
) AS canonical(variable_code, canonical_unit)
WHERE variable.code = canonical.variable_code;

INSERT INTO catalogue.vertical_level (
    code,
    name,
    level_type,
    level_value,
    unit,
    display_order
)
VALUES (
    'mean_sea_level',
    'Mean sea level',
    'mean_sea_level',
    NULL,
    NULL,
    15
);

-- Domain dimensions are the current documented grids. Footprints intentionally
-- remain NULL: the authoritative WGS84 bounds are registered from each COG.
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
    domain.code,
    domain.name,
    domain.native_crs,
    domain.grid_resolution_x_m,
    domain.grid_resolution_y_m,
    domain.grid_width,
    domain.grid_height,
    jsonb_build_object(
        'grid', domain.native_crs,
        'resolution', domain.resolution,
        'documentation_url', domain.documentation_url,
        'bounds_source', 'processed_asset'
    ),
    true
FROM catalogue.product
JOIN (
    VALUES
        ('hrdps', 'continental', 'Pan-Canadian continental grid',
            'RLatLon0.0225', 2500::numeric, 2500::numeric, 2540, 1290, '2.5km',
            'https://eccc-msc.github.io/open-data/msc-data/nwp_hrdps/readme_hrdps-datamart_en/'),
        ('raqdps', 'north_america', 'North American air-quality grid',
            'RLatLon0.09', 10000::numeric, 10000::numeric, 729, 599, '10km',
            'https://eccc-msc.github.io/open-data/msc-data/nwp_raqdps/readme_raqdps-datamart_en/'),
        ('rdps', 'north_america', 'Regional rotated latitude-longitude grid',
            'RLatLon0.09', 10000::numeric, 10000::numeric, 1102, 1076, '10km',
            'https://eccc-msc.github.io/open-data/msc-data/nwp_rdps/readme_rdps-datamart_en/'),
        ('gdps', 'global', 'Global latitude-longitude grid',
            'LatLon0.15', NULL::numeric, NULL::numeric, 2400, 1201, '15km',
            'https://eccc-msc.github.io/open-data/msc-data/nwp_gdps/readme_gdps-datamart_en/')
) AS domain(
    product_code,
    code,
    name,
    native_crs,
    grid_resolution_x_m,
    grid_resolution_y_m,
    grid_width,
    grid_height,
    resolution,
    documentation_url
) ON product.code = domain.product_code
ON CONFLICT (product_id, code) DO UPDATE
SET name = EXCLUDED.name,
    native_crs = EXCLUDED.native_crs,
    grid_resolution_x_m = EXCLUDED.grid_resolution_x_m,
    grid_resolution_y_m = EXCLUDED.grid_resolution_y_m,
    grid_width = EXCLUDED.grid_width,
    grid_height = EXCLUDED.grid_height,
    source_grid_metadata = catalogue.domain.source_grid_metadata
        || EXCLUDED.source_grid_metadata,
    enabled = EXCLUDED.enabled,
    updated_at = clock_timestamp();

-- Each row below is a direct representation of one entry in config/variables.
-- Disabled fields are catalogued but retain their YAML safety flags; only
-- inventory-verified fields can be resolved for processing or public display.
WITH field_seed AS (
    SELECT *
    FROM (
        VALUES
            ('hrdps', 'air_temperature_2m', 'air_temperature', '2m_agl',
                'HRDPS', 'TMP', 'AGL-2m', 'AGL', 2::numeric, 'K', 'degC',
                'kelvin_to_celsius', true, true, true, 'Float32', -9999.0,
                'bilinear', 'temperature', 0, NULL),
            ('hrdps', 'relative_humidity_2m', 'relative_humidity', '2m_agl',
                'HRDPS', 'RH', 'AGL-2m', 'AGL', 2::numeric, 'percent', 'percent',
                'identity', false, false, false, 'Float32', -9999.0,
                'bilinear', 'humidity', 0, NULL),
            ('hrdps', 'total_cloud_cover', 'total_cloud_cover', 'surface',
                'HRDPS', 'TCDC', 'Sfc', 'Sfc', NULL::numeric, 'percent', 'percent',
                'identity', false, false, false, 'Float32', -9999.0,
                'bilinear', 'cloud', 0, NULL),
            ('hrdps', 'surface_pressure', 'surface_pressure', 'surface',
                'HRDPS', 'PRES', 'Sfc', 'Sfc', NULL::numeric, 'Pa', 'hPa',
                'pascals_to_hectopascals', false, false, false, 'Float32', -9999.0,
                'bilinear', 'pressure', 0, NULL),
            ('hrdps', 'mean_sea_level_pressure', 'mean_sea_level_pressure',
                'mean_sea_level', 'HRDPS', 'PRMSL', 'MSL', 'MSL', NULL::numeric,
                'Pa', 'hPa', 'pascals_to_hectopascals', false, false, false,
                'Float32', -9999.0, 'bilinear', 'pressure', 0, NULL),
            ('hrdps', 'wind_u_10m', 'wind_u', '10m_agl',
                'HRDPS', 'UGRD', 'AGL-10m', 'AGL', 10::numeric, 'm/s', 'm/s',
                'identity', false, false, false, 'Float32', -9999.0,
                'bilinear', 'wind', 0, NULL),
            ('hrdps', 'wind_v_10m', 'wind_v', '10m_agl',
                'HRDPS', 'VGRD', 'AGL-10m', 'AGL', 10::numeric, 'm/s', 'm/s',
                'identity', false, false, false, 'Float32', -9999.0,
                'bilinear', 'wind', 0, NULL),
            ('hrdps', 'wind_gust_10m', 'wind_gust', '10m_agl',
                'HRDPS', 'GUST', 'AGL-10m', 'AGL', 10::numeric, 'm/s', 'm/s',
                'identity', false, false, false, 'Float32', -9999.0,
                'bilinear', 'wind', 0, NULL),
            ('hrdps', 'visibility_surface', 'visibility', 'surface',
                'HRDPS-WEonG', 'VISIFG', 'Sfc', 'Sfc', NULL::numeric, 'm', 'km',
                'metres_to_kilometres', false, false, false, 'Float32', -9999.0,
                'bilinear', 'visibility', 1, 48),
            ('hrdps', 'total_precipitation_1h', 'precipitation', 'surface',
                'HRDPS', 'APCP-Accum1h', 'Sfc', 'Sfc', NULL::numeric, 'kg/m^2', 'mm',
                'identity', false, false, false, 'Float32', -9999.0,
                'bilinear', 'precipitation', 1, 48),

            ('raqdps', 'pm25_surface', 'pm25', 'surface',
                'RAQDPS', 'PM2.5', 'Sfc', 'Sfc', NULL::numeric, 'kg/m^3', 'ug/m^3',
                'kilograms_per_cubic_metre_to_micrograms_per_cubic_metre',
                true, true, true, 'Float32', -9999.0, 'bilinear', 'pm25', 0, NULL),
            ('raqdps', 'pm10_surface', 'pm10', 'surface',
                'RAQDPS', 'PM10', 'Sfc', 'Sfc', NULL::numeric, 'kg/m^3', 'ug/m^3',
                'kilograms_per_cubic_metre_to_micrograms_per_cubic_metre',
                true, true, true, 'Float32', -9999.0, 'bilinear', 'pm10', 0, NULL),
            ('raqdps', 'ozone_surface', 'ozone', 'surface',
                'RAQDPS', 'O3', 'Sfc', 'Sfc', NULL::numeric, 'ppb', 'ppb',
                'identity', true, true, true, 'Float32', -9999.0,
                'bilinear', 'ozone', 0, NULL),
            ('raqdps', 'nitrogen_dioxide_surface', 'nitrogen_dioxide', 'surface',
                'RAQDPS', 'NO2', 'Sfc', 'Sfc', NULL::numeric, 'ppb', 'ppb',
                'identity', true, true, true, 'Float32', -9999.0,
                'bilinear', 'nitrogen_dioxide', 0, NULL),
            ('raqdps', 'sulfur_dioxide_surface', 'sulfur_dioxide', 'surface',
                'RAQDPS', 'SO2', 'Sfc', 'Sfc', NULL::numeric, 'ppb', 'ppb',
                'identity', true, true, true, 'Float32', -9999.0,
                'bilinear', 'sulfur_dioxide', 0, NULL),

            ('rdps', 'air_temperature_2m', 'air_temperature', '2m_agl',
                'RDPS', 'AirTemp', 'AGL-2m', 'AGL', 2::numeric, 'K', 'degC',
                'kelvin_to_celsius', true, true, true, 'Float32', -9999.0,
                'bilinear', 'temperature', 0, NULL),
            ('rdps', 'relative_humidity_2m', 'relative_humidity', '2m_agl',
                'RDPS', 'RelativeHumidity', 'AGL-2m', 'AGL', 2::numeric,
                'percent', 'percent', 'identity', false, false, false,
                'Float32', -9999.0, 'bilinear', 'humidity', 0, NULL),
            ('rdps', 'total_cloud_cover', 'total_cloud_cover', 'surface',
                'RDPS', 'TotalCloudCover', 'Sfc', 'Sfc', NULL::numeric,
                'percent', 'percent', 'identity', false, false, false,
                'Float32', -9999.0, 'bilinear', 'cloud', 0, NULL),
            ('rdps', 'surface_pressure', 'surface_pressure', 'surface',
                'RDPS', 'Pressure', 'Sfc', 'Sfc', NULL::numeric, 'Pa', 'hPa',
                'pascals_to_hectopascals', false, false, false,
                'Float32', -9999.0, 'bilinear', 'pressure', 0, NULL),
            ('rdps', 'mean_sea_level_pressure', 'mean_sea_level_pressure',
                'mean_sea_level', 'RDPS', 'Pressure', 'MSL', 'MSL', NULL::numeric,
                'Pa', 'hPa', 'pascals_to_hectopascals', false, false, false,
                'Float32', -9999.0, 'bilinear', 'pressure', 0, NULL),
            ('rdps', 'wind_u_10m', 'wind_u', '10m_agl',
                'RDPS', 'WindU', 'AGL-10m', 'AGL', 10::numeric, 'm/s', 'm/s',
                'identity', false, false, false, 'Float32', -9999.0,
                'bilinear', 'wind', 0, NULL),
            ('rdps', 'wind_v_10m', 'wind_v', '10m_agl',
                'RDPS', 'WindV', 'AGL-10m', 'AGL', 10::numeric, 'm/s', 'm/s',
                'identity', false, false, false, 'Float32', -9999.0,
                'bilinear', 'wind', 0, NULL),
            ('rdps', 'wind_gust_10m', 'wind_gust', '10m_agl',
                'RDPS', 'WindGust', 'AGL-10m', 'AGL', 10::numeric, 'm/s', 'm/s',
                'identity', false, false, false, 'Float32', -9999.0,
                'bilinear', 'wind', 0, NULL),
            ('rdps', 'total_precipitation_1h', 'precipitation', 'surface',
                'RDPS', 'Precip-Accum1h', 'Sfc', 'Sfc', NULL::numeric,
                'kg/m^2', 'mm', 'identity', false, false, false,
                'Float32', -9999.0, 'bilinear', 'precipitation', 1, 84),
            ('rdps', 'snowfall_1h', 'snowfall', 'surface',
                'RDPS', 'Snow-Accum1h', 'Sfc', 'Sfc', NULL::numeric,
                'kg/m^2', 'mm_water_equivalent', 'identity', false, false, false,
                'Float32', -9999.0, 'bilinear', 'snowfall', 1, 84),

            ('gdps', 'air_temperature_2m', 'air_temperature', '2m_agl',
                'GDPS', 'AirTemp', 'AGL-2m', 'AGL', 2::numeric, 'K', 'degC',
                'kelvin_to_celsius', true, true, true, 'Float32', -9999.0,
                'bilinear', 'temperature', 0, NULL),
            ('gdps', 'relative_humidity_2m', 'relative_humidity', '2m_agl',
                'GDPS', 'RelativeHumidity', 'AGL-2m', 'AGL', 2::numeric,
                'percent', 'percent', 'identity', false, false, false,
                'Float32', -9999.0, 'bilinear', 'humidity', 0, NULL),
            ('gdps', 'total_cloud_cover', 'total_cloud_cover', 'surface',
                'GDPS', 'TotalCloudCover', 'Sfc', 'Sfc', NULL::numeric,
                'percent', 'percent', 'identity', false, false, false,
                'Float32', -9999.0, 'bilinear', 'cloud', 0, NULL),
            ('gdps', 'surface_pressure', 'surface_pressure', 'surface',
                'GDPS', 'Pressure', 'Sfc', 'Sfc', NULL::numeric, 'Pa', 'hPa',
                'pascals_to_hectopascals', false, false, false,
                'Float32', -9999.0, 'bilinear', 'pressure', 0, NULL),
            ('gdps', 'mean_sea_level_pressure', 'mean_sea_level_pressure',
                'mean_sea_level', 'GDPS', 'Pressure', 'MSL', 'MSL', NULL::numeric,
                'Pa', 'hPa', 'pascals_to_hectopascals', false, false, false,
                'Float32', -9999.0, 'bilinear', 'pressure', 0, NULL),
            ('gdps', 'wind_u_10m', 'wind_u', '10m_agl',
                'GDPS', 'WindU', 'AGL-10m', 'AGL', 10::numeric, 'm/s', 'm/s',
                'identity', false, false, false, 'Float32', -9999.0,
                'bilinear', 'wind', 0, NULL),
            ('gdps', 'wind_v_10m', 'wind_v', '10m_agl',
                'GDPS', 'WindV', 'AGL-10m', 'AGL', 10::numeric, 'm/s', 'm/s',
                'identity', false, false, false, 'Float32', -9999.0,
                'bilinear', 'wind', 0, NULL),
            ('gdps', 'wind_gust_10m', 'wind_gust', '10m_agl',
                'GDPS', 'WindGust', 'AGL-10m', 'AGL', 10::numeric, 'm/s', 'm/s',
                'identity', false, false, false, 'Float32', -9999.0,
                'bilinear', 'wind', 0, NULL),
            ('gdps', 'total_precipitation_1h', 'precipitation', 'surface',
                'GDPS', 'Precip-Accum1h', 'Sfc', 'Sfc', NULL::numeric,
                'kg/m^2', 'mm', 'identity', false, false, false,
                'Float32', -9999.0, 'bilinear', 'precipitation', 1, 84),
            ('gdps', 'snowfall_1h', 'snowfall', 'surface',
                'GDPS', 'Snow-Accum1h', 'Sfc', 'Sfc', NULL::numeric,
                'kg/m^2', 'mm_water_equivalent', 'identity', false, false, false,
                'Float32', -9999.0, 'bilinear', 'snowfall', 1, 84)
    ) AS configured(
        product_code,
        field_code,
        variable_code,
        level_code,
        source_producer,
        source_parameter,
        source_level,
        source_level_type,
        source_level_value,
        source_unit,
        canonical_unit,
        conversion_key,
        displayable,
        download_enabled,
        processing_enabled,
        output_data_type,
        nodata_value,
        resampling,
        default_style,
        start_forecast_hour,
        end_forecast_hour
    )
)
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
    field.source_parameter,
    field.source_level_type,
    field.source_level_value,
    field.source_unit,
    field.conversion_key,
    field.displayable,
    field.download_enabled,
    field.processing_enabled,
    jsonb_build_object(
        'field_code', field.field_code,
        'source_producer', field.source_producer,
        'source_level', field.source_level,
        'canonical_unit', field.canonical_unit,
        'output_data_type', field.output_data_type,
        'nodata_value', field.nodata_value,
        'resampling', field.resampling,
        'default_style', field.default_style,
        'availability', jsonb_build_object(
            'start_forecast_hour', field.start_forecast_hour,
            'end_forecast_hour', field.end_forecast_hour
        ),
        'configuration_source', 'config/variables'
    )
FROM field_seed AS field
JOIN catalogue.product ON product.code = field.product_code
JOIN catalogue.variable ON variable.code = field.variable_code
JOIN catalogue.vertical_level ON vertical_level.code = field.level_code
ON CONFLICT ON CONSTRAINT product_field_source_uk DO UPDATE
SET variable_id = EXCLUDED.variable_id,
    vertical_level_id = EXCLUDED.vertical_level_id,
    source_unit = EXCLUDED.source_unit,
    conversion_key = EXCLUDED.conversion_key,
    displayable = EXCLUDED.displayable,
    download_enabled = EXCLUDED.download_enabled,
    processing_enabled = EXCLUDED.processing_enabled,
    metadata = EXCLUDED.metadata,
    updated_at = clock_timestamp();

-- These palette codes mirror the default_style values in configuration.
-- Pollutant ramps are presentation defaults, not health or regulatory limits.
INSERT INTO display.palette (code, name, description, revision, definition)
VALUES
    ('humidity', 'Relative humidity', 'Continuous relative-humidity display ramp.', 1,
        '{"interpolation":"linear","stops":[{"value":0,"color":"#fff7fb00"},{"value":25,"color":"#d0d1e6"},{"value":50,"color":"#74a9cf"},{"value":75,"color":"#2b8cbe"},{"value":100,"color":"#045a8d"}]}'::jsonb),
    ('cloud', 'Cloud cover', 'Cloud-cover ramp with clear sky transparent.', 1,
        '{"interpolation":"linear","stops":[{"value":0,"color":"#ffffff00"},{"value":20,"color":"#eef2f640"},{"value":50,"color":"#d5dde5a0"},{"value":80,"color":"#aeb9c5dc"},{"value":100,"color":"#f8fafcff"}]}'::jsonb),
    ('wind', 'Wind', 'Diverging wind-component ramp also suitable for nonnegative gusts.', 1,
        '{"interpolation":"linear","stops":[{"value":-40,"color":"#762a83"},{"value":-20,"color":"#af8dc3"},{"value":0,"color":"#f7f7f7"},{"value":10,"color":"#7fbf7b"},{"value":25,"color":"#1b7837"},{"value":50,"color":"#00441b"}]}'::jsonb),
    ('snowfall', 'Snowfall', 'Threshold-oriented snowfall water-equivalent ramp.', 1,
        '{"interpolation":"step","stops":[{"value":0,"color":"#ffffff00"},{"value":0.2,"color":"#eff3ff"},{"value":2,"color":"#bdd7e7"},{"value":10,"color":"#6baed6"},{"value":25,"color":"#756bb1"},{"value":50,"color":"#54278f"}]}'::jsonb),
    ('pm25', 'PM2.5', 'PM2.5 concentration display ramp; not a regulatory scale.', 1,
        '{"interpolation":"linear","stops":[{"value":0,"color":"#f7fcf5"},{"value":10,"color":"#c7e9c0"},{"value":25,"color":"#74c476"},{"value":50,"color":"#fe9929"},{"value":100,"color":"#8c2d04"}]}'::jsonb),
    ('pm10', 'PM10', 'PM10 concentration display ramp; not a regulatory scale.', 1,
        '{"interpolation":"linear","stops":[{"value":0,"color":"#fff7ec"},{"value":20,"color":"#fee8c8"},{"value":50,"color":"#fdbb84"},{"value":100,"color":"#e34a33"},{"value":150,"color":"#7f0000"}]}'::jsonb),
    ('ozone', 'Ozone', 'Ozone concentration display ramp; not a regulatory scale.', 1,
        '{"interpolation":"linear","stops":[{"value":0,"color":"#f7fcfd"},{"value":20,"color":"#ccece6"},{"value":40,"color":"#66c2a4"},{"value":60,"color":"#238b45"},{"value":100,"color":"#54278f"}]}'::jsonb),
    ('nitrogen_dioxide', 'Nitrogen dioxide',
        'Nitrogen-dioxide concentration display ramp; not a regulatory scale.', 1,
        '{"interpolation":"linear","stops":[{"value":0,"color":"#ffffcc"},{"value":20,"color":"#c2e699"},{"value":50,"color":"#78c679"},{"value":100,"color":"#238443"},{"value":200,"color":"#004529"}]}'::jsonb),
    ('sulfur_dioxide', 'Sulfur dioxide',
        'Sulfur-dioxide concentration display ramp; not a regulatory scale.', 1,
        '{"interpolation":"linear","stops":[{"value":0,"color":"#fff7fb"},{"value":10,"color":"#d4b9da"},{"value":25,"color":"#c994c7"},{"value":50,"color":"#df65b0"},{"value":100,"color":"#7a0177"}]}'::jsonb);

WITH style_seed AS (
    SELECT *
    FROM (
        VALUES
            ('air_temperature_2m', 'temperature', -40.0, 40.0, 'linear', 1),
            ('relative_humidity_2m', 'humidity', 0.0, 100.0, 'linear', 0),
            ('total_cloud_cover', 'cloud', 0.0, 100.0, 'linear', 0),
            ('surface_pressure', 'pressure', 940.0, 1060.0, 'linear', 0),
            ('mean_sea_level_pressure', 'pressure', 940.0, 1060.0, 'linear', 0),
            ('wind_u_10m', 'wind', -40.0, 40.0, 'diverging', 1),
            ('wind_v_10m', 'wind', -40.0, 40.0, 'diverging', 1),
            ('wind_gust_10m', 'wind', 0.0, 50.0, 'linear', 1),
            ('visibility_surface', 'visibility', 0.0, 50.0, 'linear', 1),
            ('total_precipitation_1h', 'precipitation', 0.0, 50.0, 'threshold', 1),
            ('snowfall_1h', 'snowfall', 0.0, 50.0, 'threshold', 1),
            ('pm25_surface', 'pm25', 0.0, 100.0, 'linear', 1),
            ('pm10_surface', 'pm10', 0.0, 150.0, 'linear', 1),
            ('ozone_surface', 'ozone', 0.0, 100.0, 'linear', 1),
            ('nitrogen_dioxide_surface', 'nitrogen_dioxide', 0.0, 200.0, 'linear', 1),
            ('sulfur_dioxide_surface', 'sulfur_dioxide', 0.0, 100.0, 'linear', 1)
    ) AS configured(field_code, palette_code, default_min, default_max, scale_type, precision)
)
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
    product_field.variable_id,
    product_field.id,
    palette.id,
    'default',
    product.name || ' ' || replace(style.field_code, '_', ' '),
    1,
    style.default_min,
    style.default_max,
    style.scale_type,
    true,
    0.8,
    product_field.metadata ->> 'resampling',
    style.precision,
    true,
    jsonb_build_object(
        'configuration_style', product_field.metadata ->> 'default_style',
        'configuration_source', 'config/variables'
    )
FROM catalogue.product_field
JOIN catalogue.product ON product.id = product_field.product_id
JOIN style_seed AS style
    ON style.field_code = product_field.metadata ->> 'field_code'
JOIN display.palette ON palette.code = style.palette_code AND palette.revision = 1
WHERE product.code IN ('hrdps', 'raqdps', 'rdps', 'gdps');

-- app.schema_migration predates the weather_owner default privileges. Grant the
-- backup account explicit read access to it and to every current sequence;
-- retain the future-object defaults without broadening this role beyond SELECT.
GRANT SELECT ON app.schema_migration TO weather_backup;
GRANT SELECT ON ALL SEQUENCES IN SCHEMA app, catalogue, ingestion, display, audit
    TO weather_backup;
ALTER DEFAULT PRIVILEGES IN SCHEMA app, catalogue, ingestion, display, audit
    GRANT SELECT ON TABLES TO weather_backup;
ALTER DEFAULT PRIVILEGES IN SCHEMA app, catalogue, ingestion, display, audit
    GRANT SELECT ON SEQUENCES TO weather_backup;

RESET ROLE;

INSERT INTO app.schema_migration (migration_name, checksum)
VALUES (:'migration_name', :'migration_checksum');

COMMIT;
