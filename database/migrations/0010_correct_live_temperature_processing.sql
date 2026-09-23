\set ON_ERROR_STOP on

BEGIN;

SET ROLE weather_owner;

-- ECCC's live RDPS GRIB2 grid on 2026-07-17 reports Ni=1140, Nj=1045.
UPDATE catalogue.domain AS domain
SET grid_width = 1140,
    grid_height = 1045,
    source_grid_metadata = domain.source_grid_metadata || jsonb_build_object(
        'dimensions_verified_at', '2026-07-17T17:30:00Z',
        'dimensions_source', 'live_grib2_eccodes'
    ),
    updated_at = clock_timestamp()
FROM catalogue.product AS product
WHERE product.id = domain.product_id
  AND product.code = 'rdps'
  AND domain.code = 'north_america';

-- ecCodes reports the GRIB values in Kelvin, but GDAL's GRIB driver exposes
-- the decoded raster band in Celsius (GRIB_UNIT=[C]). COG processing therefore
-- copies the decoded values rather than subtracting 273.15 a second time.
UPDATE catalogue.product_field AS product_field
SET conversion_key = 'identity',
    metadata = product_field.metadata || jsonb_build_object(
        'gdal_source_unit', 'C',
        'conversion_verified_at', '2026-07-17T18:05:00Z'
    ),
    updated_at = clock_timestamp()
FROM catalogue.product AS product
WHERE product.id = product_field.product_id
  AND product.code IN ('gdps', 'hrdps', 'rdps')
  AND product_field.metadata ->> 'field_code' = 'air_temperature_2m';

RESET ROLE;

INSERT INTO app.schema_migration (migration_name, checksum)
VALUES (:'migration_name', :'migration_checksum');

COMMIT;
