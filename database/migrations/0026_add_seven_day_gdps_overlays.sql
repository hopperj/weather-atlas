\set ON_ERROR_STOP on

BEGIN;

SET ROLE weather_owner;

-- The GDPS publishes direct 10 m wind speed, so expose the user-facing scalar
-- instead of requiring users to interpret the separate U and V components.
UPDATE catalogue.variable
SET canonical_unit = 'm/s',
    description = 'Wind speed at the product-declared height.',
    metadata = metadata || '{"direct_source_available": true}'::jsonb,
    updated_at = clock_timestamp()
WHERE code = 'wind_speed';

-- The operational GDPS 1 h accumulation remains present through forecast hour
-- 144. Give it an interval-specific display name before adding the independent
-- 3 h accumulation that reaches the full seven-day boundary.
UPDATE catalogue.product_field AS product_field
SET metadata = product_field.metadata
        || jsonb_build_object(
            'display_name', 'Total precipitation · 1 hour',
            'availability', jsonb_build_object(
                'start_forecast_hour', 1,
                'end_forecast_hour', 144,
                'forecast_hour_step', 1
            )
        ),
    updated_at = clock_timestamp()
FROM catalogue.product AS product
WHERE product.id = product_field.product_id
  AND product.code = 'gdps'
  AND product_field.metadata ->> 'field_code' = 'total_precipitation_1h';

WITH field_seed AS (
    SELECT *
    FROM (
        VALUES
            (
                'wind_speed_10m',
                'wind_speed',
                '10m_agl',
                'WindSpeed',
                'AGL',
                10::numeric,
                'm/s',
                'm/s',
                'bilinear',
                'wind_speed',
                NULL::text,
                0,
                NULL::integer,
                1
            ),
            (
                'total_precipitation_3h',
                'precipitation',
                'surface',
                'Precip-Accum3h',
                'Sfc',
                NULL::numeric,
                'kg/m^2',
                'mm',
                'bilinear',
                'precipitation',
                'Total precipitation · 3 hours',
                3,
                168,
                3
            )
    ) AS configured(
        field_code,
        variable_code,
        level_code,
        source_parameter,
        source_level_type,
        source_level_value,
        source_unit,
        canonical_unit,
        resampling,
        default_style,
        display_name,
        start_forecast_hour,
        end_forecast_hour,
        forecast_hour_step
    )
)
INSERT INTO catalogue.product_field (
    product_id,
    variable_id,
    vertical_level_id,
    source_producer,
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
    'GDPS',
    field.source_parameter,
    field.source_level_type,
    field.source_level_value,
    field.source_unit,
    'identity',
    true,
    true,
    true,
    jsonb_strip_nulls(jsonb_build_object(
        'field_code', field.field_code,
        'source_producer', 'GDPS',
        'source_level',
            CASE
                WHEN field.source_level_type = 'AGL' THEN 'AGL-10m'
                ELSE field.source_level_type
            END,
        'canonical_unit', field.canonical_unit,
        'output_data_type', 'Float32',
        'nodata_value', -9999.0,
        'resampling', field.resampling,
        'default_style', field.default_style,
        'display_name', field.display_name,
        'availability', jsonb_strip_nulls(jsonb_build_object(
            'start_forecast_hour', field.start_forecast_hour,
            'end_forecast_hour', field.end_forecast_hour,
            'forecast_hour_step', field.forecast_hour_step
        )),
        'activation_evidence',
            'live GDPS 2026-07-27 12Z inventory at forecast hours 003, 084, 087, 144, 168'
    ))
FROM field_seed AS field
JOIN catalogue.product AS product ON product.code = 'gdps'
JOIN catalogue.variable AS variable ON variable.code = field.variable_code
JOIN catalogue.vertical_level AS vertical_level ON vertical_level.code = field.level_code
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

WITH style_seed AS (
    SELECT *
    FROM (
        VALUES
            ('wind_speed_10m', 'wind_speed', 0.0, 40.0, 'linear', 1),
            ('total_precipitation_3h', 'precipitation', 0.0, 50.0, 'threshold', 1)
    ) AS configured(
        field_code,
        palette_code,
        default_min,
        default_max,
        scale_type,
        precision
    )
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
JOIN display.palette AS palette
    ON palette.code = style.palette_code
   AND palette.revision = 1
WHERE product.code = 'gdps'
ON CONFLICT ON CONSTRAINT variable_style_identity_uk DO UPDATE
SET palette_id = EXCLUDED.palette_id,
    name = EXCLUDED.name,
    default_min = EXCLUDED.default_min,
    default_max = EXCLUDED.default_max,
    scale_type = EXCLUDED.scale_type,
    clamp_values = EXCLUDED.clamp_values,
    opacity = EXCLUDED.opacity,
    resampling_method = EXCLUDED.resampling_method,
    legend_precision = EXCLUDED.legend_precision,
    nodata_transparent = EXCLUDED.nodata_transparent,
    metadata = EXCLUDED.metadata,
    enabled = true,
    updated_at = clock_timestamp();

RESET ROLE;

INSERT INTO app.schema_migration (migration_name, checksum)
VALUES (:'migration_name', :'migration_checksum');

COMMIT;
