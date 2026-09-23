\set ON_ERROR_STOP on
BEGIN;
SET ROLE weather_owner;

-- Observation imagery is a rendered RGB(A) product, not a scalar model field.
CREATE TABLE catalogue.imagery_product (
    code text PRIMARY KEY CHECK (code ~ '^[a-z][a-z0-9_]{0,63}$'),
    name text NOT NULL,
    kind text NOT NULL CHECK (kind IN ('radar', 'satellite')),
    source_layer text NOT NULL,
    attribution text NOT NULL,
    enabled boolean NOT NULL DEFAULT true
);

CREATE TABLE catalogue.imagery_frame (
    id uuid PRIMARY KEY,
    product_code text NOT NULL REFERENCES catalogue.imagery_product(code),
    valid_time timestamptz NOT NULL,
    collected_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    configuration_sha256 text NOT NULL CHECK (configuration_sha256 ~ '^[a-f0-9]{64}$'),
    content_sha256 text NOT NULL CHECK (content_sha256 ~ '^[a-f0-9]{64}$'),
    relative_path text NOT NULL CHECK (relative_path LIKE 'processed/eccc/imagery/%'),
    bounds jsonb NOT NULL CHECK (jsonb_array_length(bounds) = 4),
    provenance jsonb NOT NULL CHECK (jsonb_typeof(provenance) = 'object'),
    UNIQUE (product_code, valid_time, configuration_sha256)
);
CREATE INDEX imagery_frame_product_time_idx ON catalogue.imagery_frame(product_code, valid_time DESC);
INSERT INTO catalogue.imagery_product(code, name, kind, source_layer, attribution) VALUES
    ('radar_rain', 'Radar · rain rate', 'radar', 'RADAR_1KM_RRAI', 'ECCC GeoMet · Radar precipitation rate (mm/h)'),
    ('satellite_natural', 'Satellite · natural colour', 'satellite', 'GOES-East_1km_NaturalColor', 'NOAA GOES-East / ECCC GeoMet · Natural colour'),
    ('satellite_ir', 'Satellite · night infrared', 'satellite', 'GOES-East_2km_NightIR', 'NOAA GOES-East / ECCC GeoMet · Night infrared');

GRANT SELECT ON catalogue.imagery_product, catalogue.imagery_frame TO weather_api, weather_tiles, weather_readonly, weather_backup, weather_ingest;
GRANT INSERT ON catalogue.imagery_frame TO weather_ingest;
RESET ROLE;

INSERT INTO app.schema_migration (migration_name, checksum)
VALUES (:'migration_name', :'migration_checksum');

COMMIT;
