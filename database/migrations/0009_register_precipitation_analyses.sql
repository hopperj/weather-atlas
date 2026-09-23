\set ON_ERROR_STOP on

BEGIN;

SET ROLE weather_owner;

ALTER TABLE catalogue.product_field
    ADD COLUMN source_producer text;

UPDATE catalogue.product_field AS product_field
SET source_producer = COALESCE(
    product_field.metadata ->> 'source_producer',
    upper((
        SELECT product.code
        FROM catalogue.product
        WHERE product.id = product_field.product_id
    ))
);

ALTER TABLE catalogue.product_field
    ALTER COLUMN source_producer SET NOT NULL,
    ADD CONSTRAINT product_field_source_producer_ck
        CHECK (btrim(source_producer) <> '');

ALTER TABLE catalogue.product_field
    DROP CONSTRAINT product_field_source_uk;
ALTER TABLE catalogue.product_field
    ADD CONSTRAINT product_field_source_uk UNIQUE NULLS NOT DISTINCT (
        product_id,
        source_producer,
        source_parameter,
        source_level_type,
        source_level_value
    );

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
    domain.resolution_m,
    domain.resolution_m,
    domain.grid_width,
    domain.grid_height,
    jsonb_build_object(
        'grid', domain.native_crs,
        'resolution', domain.resolution,
        'documentation_url', domain.documentation_url,
        'time_semantics', 'analysis_valid_time'
    ),
    true
FROM catalogue.product
JOIN (
    VALUES
        ('hrdpa', 'continental', 'Pan-Canadian high-resolution precipitation-analysis grid',
            'RLatLon0.0225', 2500::numeric, 2538, 1288, '2.5km',
            'https://eccc-msc.github.io/open-data/msc-data/nwp_hrdpa/readme_hrdpa-datamart_en/'),
        ('rdpa', 'north_america', 'North American regional precipitation-analysis grid',
            'RLatLon0.09', 10000::numeric, 1140, 1045, '10km',
            'https://eccc-msc.github.io/open-data/msc-data/nwp_rdpa/readme_rdpa-datamart_en/')
) AS domain(
    product_code,
    code,
    name,
    native_crs,
    resolution_m,
    grid_width,
    grid_height,
    resolution,
    documentation_url
) ON product.code = domain.product_code;

WITH field_seed AS (
    SELECT *
    FROM (
        VALUES
            ('hrdpa', 'precipitation_6h_preliminary', 'HRDPA-Prelim',
                'APCP-Accum6h', 6, 'preliminary'),
            ('hrdpa', 'precipitation_6h_final', 'HRDPA',
                'APCP-Accum6h', 6, 'final'),
            ('hrdpa', 'precipitation_24h_preliminary', 'HRDPA-Prelim',
                'APCP-Accum24h', 24, 'preliminary'),
            ('hrdpa', 'precipitation_24h_final', 'HRDPA',
                'APCP-Accum24h', 24, 'final'),
            ('rdpa', 'precipitation_6h_preliminary', 'RDPA-Prelim',
                'APCP-Accum6h', 6, 'preliminary'),
            ('rdpa', 'precipitation_6h_final', 'RDPA',
                'APCP-Accum6h', 6, 'final'),
            ('rdpa', 'precipitation_24h_preliminary', 'RDPA-Prelim',
                'APCP-Accum24h', 24, 'preliminary'),
            ('rdpa', 'precipitation_24h_final', 'RDPA',
                'APCP-Accum24h', 24, 'final')
    ) AS configured(
        product_code,
        field_code,
        source_producer,
        source_parameter,
        accumulation_hours,
        revision
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
    field.source_producer,
    field.source_parameter,
    'Sfc',
    NULL,
    'kg/m^2',
    'identity',
    false,
    true,
    false,
    jsonb_build_object(
        'field_code', field.field_code,
        'source_producer', field.source_producer,
        'source_level', 'Sfc',
        'canonical_unit', 'mm',
        'output_data_type', 'Float32',
        'nodata_value', -9999.0,
        'resampling', 'bilinear',
        'default_style', 'precipitation',
        'source_band', 1,
        'analysis', jsonb_build_object(
            'accumulation_hours', field.accumulation_hours,
            'revision', field.revision,
            'interval_end_semantics', 'valid_time'
        ),
        'processing_activation_gate',
            'real_payload_metadata_unit_band_and_pixel_validation'
    )
FROM field_seed AS field
JOIN catalogue.product ON product.code = field.product_code
JOIN catalogue.variable ON variable.code = 'precipitation'
JOIN catalogue.vertical_level ON vertical_level.code = 'surface';

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
    CASE
        WHEN (product_field.metadata #>> '{analysis,accumulation_hours}')::integer = 24
            THEN 100.0
        ELSE 50.0
    END,
    'threshold',
    true,
    0.8,
    product_field.metadata ->> 'resampling',
    1,
    true,
    jsonb_build_object(
        'configuration_style', 'precipitation',
        'activation_state', 'processing_disabled_pending_payload_verification'
    )
FROM catalogue.product_field
JOIN catalogue.product ON product.id = product_field.product_id
JOIN display.palette ON palette.code = 'precipitation' AND palette.revision = 1
WHERE product.code IN ('hrdpa', 'rdpa');

CREATE FUNCTION catalogue.enforce_product_time_semantics()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog, catalogue
AS $function$
DECLARE
    resolved_kind text;
BEGIN
    SELECT product.product_kind
    INTO resolved_kind
    FROM catalogue.product_run
    JOIN catalogue.product ON product.id = product_run.product_id
    WHERE product_run.id = NEW.product_run_id;

    IF resolved_kind IS NULL THEN
        RAISE EXCEPTION 'product run % does not exist', NEW.product_run_id
            USING ERRCODE = '23503';
    END IF;
    IF resolved_kind = 'forecast' AND NEW.forecast_hour IS NULL THEN
        RAISE EXCEPTION 'forecast product times require forecast_hour'
            USING ERRCODE = '23514';
    END IF;
    IF resolved_kind <> 'forecast' AND NEW.forecast_hour IS NOT NULL THEN
        RAISE EXCEPTION 'analysis product times require forecast_hour to be NULL'
            USING ERRCODE = '23514';
    END IF;
    IF resolved_kind <> 'forecast' AND NEW.time_kind = 'instant' THEN
        RAISE EXCEPTION 'precipitation analysis times require an interval time_kind'
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END
$function$;

REVOKE ALL ON FUNCTION catalogue.enforce_product_time_semantics() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION catalogue.enforce_product_time_semantics() TO weather_ingest;

CREATE TRIGGER product_time_semantics_trigger
BEFORE INSERT OR UPDATE OF product_run_id, forecast_hour, time_kind
ON catalogue.product_time
FOR EACH ROW
EXECUTE FUNCTION catalogue.enforce_product_time_semantics();

RESET ROLE;

INSERT INTO app.schema_migration (migration_name, checksum)
VALUES (:'migration_name', :'migration_checksum');

COMMIT;
