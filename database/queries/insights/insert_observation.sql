INSERT INTO catalogue.weather_observation
    (station_id, observed_at, report_type, correction, version, payload)
VALUES (%(id)s, %(observed_at)s, %(report_type)s, %(correction)s, %(version)s, %(payload)s)
ON CONFLICT DO NOTHING;
