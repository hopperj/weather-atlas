\set ON_ERROR_STOP on
BEGIN;
SET ROLE weather_owner;

CREATE TABLE catalogue.forecast_revision (
    area_id text NOT NULL,
    source text NOT NULL CHECK (source IN ('bulletin', 'gdps')),
    version text NOT NULL CHECK (version ~ '^[a-f0-9]{64}$'),
    issued_at timestamptz NOT NULL,
    coordinate_version text NOT NULL,
    payload jsonb NOT NULL CHECK (jsonb_typeof(payload) = 'object'),
    collected_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (area_id, source, version)
);
CREATE INDEX forecast_revision_history ON catalogue.forecast_revision
    (area_id, source, issued_at DESC, collected_at DESC);

CREATE TABLE catalogue.forecast_prepared (
    area_id text NOT NULL,
    kind text NOT NULL CHECK (kind IN ('hourly', 'changes', 'widget')),
    payload jsonb NOT NULL CHECK (jsonb_typeof(payload) = 'object'),
    content_version text NOT NULL,
    generated_at timestamptz NOT NULL,
    valid_until timestamptz NOT NULL,
    PRIMARY KEY (area_id, kind)
);

CREATE TABLE catalogue.weather_station (
    id text PRIMARY KEY CHECK (id ~ '^[A-Za-z0-9_-]{1,64}$'),
    location geography(Point, 4326) NOT NULL,
    metadata jsonb NOT NULL,
    metadata_time timestamptz NOT NULL
);
CREATE INDEX weather_station_location ON catalogue.weather_station USING gist(location);
CREATE TABLE catalogue.weather_station_revision (
    station_id text NOT NULL REFERENCES catalogue.weather_station(id),
    version text NOT NULL,
    metadata jsonb NOT NULL,
    collected_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (station_id, version)
);
CREATE TABLE catalogue.weather_observation (
    station_id text NOT NULL REFERENCES catalogue.weather_station(id),
    observed_at timestamptz NOT NULL,
    report_type text NOT NULL,
    correction integer NOT NULL DEFAULT 0 CHECK (correction >= 0),
    version text NOT NULL,
    payload jsonb NOT NULL,
    received_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (station_id, observed_at, report_type, version)
);
CREATE INDEX weather_observation_latest ON catalogue.weather_observation
    (station_id, observed_at DESC, correction DESC, received_at DESC);

GRANT SELECT ON catalogue.forecast_revision, catalogue.forecast_prepared,
    catalogue.weather_station, catalogue.weather_station_revision, catalogue.weather_observation
    TO weather_api, weather_readonly, weather_backup, weather_ingest;
GRANT INSERT ON catalogue.forecast_revision, catalogue.weather_station_revision,
    catalogue.weather_observation TO weather_ingest;
GRANT INSERT, UPDATE ON catalogue.forecast_prepared, catalogue.weather_station TO weather_ingest;
RESET ROLE;
INSERT INTO app.schema_migration (migration_name, checksum)
VALUES (:'migration_name', :'migration_checksum');
COMMIT;
