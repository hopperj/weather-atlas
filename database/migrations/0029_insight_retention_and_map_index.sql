\set ON_ERROR_STOP on
BEGIN;
SET ROLE weather_owner;
-- Geography serves radius/distance queries; geometry serves exact rectangular map bounds.
CREATE INDEX weather_station_map_bounds ON catalogue.weather_station USING gist ((location::geometry));
-- Only bounded age-based maintenance of these new feature records is allowed.
GRANT DELETE ON catalogue.forecast_revision, catalogue.weather_observation,
    catalogue.weather_station_revision TO weather_ingest;
RESET ROLE;
INSERT INTO app.schema_migration (migration_name, checksum)
VALUES (:'migration_name', :'migration_checksum');
COMMIT;
