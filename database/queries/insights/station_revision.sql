INSERT INTO catalogue.weather_station_revision(station_id, version, metadata)
VALUES (%(id)s, %(version)s, %(metadata)s) ON CONFLICT DO NOTHING;
