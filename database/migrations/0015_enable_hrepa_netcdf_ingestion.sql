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
    'canada_northern_us',
    'Canadian and northern United States ensemble-analysis grid',
    'RLatLon0.0225',
    2500,
    2500,
    2438,
    1188,
    jsonb_build_object(
        'grid', 'RLatLon0.0225',
        'resolution', '2.5km',
        'format', 'NetCDF',
        'time_semantics', 'analysis_valid_time',
        'documentation_url',
            'https://eccc-msc.github.io/open-data/msc-data/nwp_hrepa/readme_hrepa-datamart_en/'
    ),
    true
FROM catalogue.product
WHERE product.code = 'hrepa'
ON CONFLICT (product_id, code) DO UPDATE
SET name = EXCLUDED.name,
    native_crs = EXCLUDED.native_crs,
    grid_resolution_x_m = EXCLUDED.grid_resolution_x_m,
    grid_resolution_y_m = EXCLUDED.grid_resolution_y_m,
    grid_width = EXCLUDED.grid_width,
    grid_height = EXCLUDED.grid_height,
    source_grid_metadata = catalogue.domain.source_grid_metadata
        || EXCLUDED.source_grid_metadata,
    enabled = true,
    updated_at = clock_timestamp();

WITH field_seed AS (
    SELECT *
    FROM (
        VALUES
            (
                'precipitation_6h_ensemble',
                'Precip-Accum06h',
                'ensemble_members',
                'Precip-Accum06h',
                100.0
            ),
            (
                'precipitation_6h_percentile_25',
                'Precip-Accum06h-Pct25',
                'percentile_25',
                'q025',
                50.0
            ),
            (
                'precipitation_6h_percentile_75',
                'Precip-Accum06h-Pct75',
                'percentile_75',
                'q075',
                100.0
            )
    ) AS configured(
        field_code,
        source_parameter,
        revision,
        netcdf_variable,
        default_max
    )
),
inserted_fields AS (
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
        'HREPA',
        field.source_parameter,
        'Sfc',
        NULL,
        'kg/m^2',
        'identity',
        true,
        true,
        true,
        jsonb_build_object(
            'field_code', field.field_code,
            'source_producer', 'HREPA',
            'source_level', 'Sfc',
            'canonical_unit', 'mm',
            'output_data_type', 'Float32',
            'nodata_value', -9999.0,
            'resampling', 'bilinear',
            'default_style', 'precipitation',
            'source_band', 1,
            'netcdf_variable', field.netcdf_variable,
            'retention_policy', 'historical_archive',
            'analysis', jsonb_build_object(
                'accumulation_hours', 6,
                'revision', field.revision,
                'interval_end_semantics', 'valid_time'
            ),
            'ensemble_source', CASE
                WHEN field.revision = 'ensemble_members'
                    THEN '25_members_control_member_published_to_map'
                ELSE 'ensemble_percentile'
            END
        )
    FROM field_seed AS field
    JOIN catalogue.product ON product.code = 'hrepa'
    JOIN catalogue.variable ON variable.code = 'precipitation'
    JOIN catalogue.vertical_level ON vertical_level.code = 'surface'
    ON CONFLICT ON CONSTRAINT product_field_source_uk DO UPDATE
    SET variable_id = EXCLUDED.variable_id,
        vertical_level_id = EXCLUDED.vertical_level_id,
        source_unit = EXCLUDED.source_unit,
        conversion_key = EXCLUDED.conversion_key,
        displayable = true,
        download_enabled = true,
        processing_enabled = true,
        metadata = EXCLUDED.metadata,
        updated_at = clock_timestamp()
    RETURNING id
)
SELECT count(*) FROM inserted_fields;

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
    product.name || ' ' || replace(product_field.metadata ->> 'field_code', '_', ' '),
    1,
    0.0,
    CASE product_field.metadata ->> 'field_code'
        WHEN 'precipitation_6h_percentile_25' THEN 50.0
        ELSE 100.0
    END,
    'threshold',
    true,
    0.8,
    'bilinear',
    1,
    true,
    jsonb_build_object(
        'configuration_style', 'precipitation',
        'configuration_source', 'config/variables/precipitation_analysis.yaml'
    )
FROM catalogue.product_field
JOIN catalogue.product ON product.id = product_field.product_id
JOIN display.palette ON palette.code = 'precipitation' AND palette.revision = 1
WHERE product.code = 'hrepa'
ON CONFLICT (variable_id, product_field_id, code, revision) DO UPDATE
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
    updated_at = clock_timestamp();

UPDATE catalogue.product
SET schedule_config = schedule_config || jsonb_build_object(
        'ingestion_enabled', true,
        'format', 'NetCDF',
        'schedule', '15 * * * *'
    ),
    retention_config = retention_config || jsonb_build_object(
        'retain_forever', true
    ),
    updated_at = clock_timestamp()
WHERE code = 'hrepa';

RESET ROLE;

INSERT INTO app.schema_migration (migration_name, checksum)
VALUES (:'migration_name', :'migration_checksum');

COMMIT;
