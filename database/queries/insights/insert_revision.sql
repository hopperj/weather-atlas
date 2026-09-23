INSERT INTO catalogue.forecast_revision
    (area_id, source, version, issued_at, coordinate_version, payload)
VALUES (%(area_id)s, %(source)s, %(version)s, %(issued_at)s, %(coordinate_version)s, %(payload)s)
ON CONFLICT DO NOTHING;
