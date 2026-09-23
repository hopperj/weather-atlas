INSERT INTO catalogue.weather_station(id, location, metadata, metadata_time)
VALUES (%(id)s, ST_SetSRID(ST_MakePoint(%(longitude)s, %(latitude)s), 4326)::geography,
    %(metadata)s, %(observed_at)s)
ON CONFLICT (id) DO UPDATE SET location = EXCLUDED.location, metadata = EXCLUDED.metadata,
    metadata_time = EXCLUDED.metadata_time
WHERE EXCLUDED.metadata_time >= weather_station.metadata_time;
