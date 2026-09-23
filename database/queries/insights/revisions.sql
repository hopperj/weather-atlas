SELECT version, issued_at, coordinate_version, payload, collected_at
FROM catalogue.forecast_revision
WHERE area_id = %(area_id)s AND source = %(source)s
ORDER BY issued_at DESC, collected_at DESC, version DESC LIMIT 24;
