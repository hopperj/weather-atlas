INSERT INTO catalogue.forecast_prepared
    (area_id, kind, payload, content_version, generated_at, valid_until)
VALUES (%(area_id)s, %(kind)s, %(payload)s, %(version)s, %(generated_at)s, %(valid_until)s)
ON CONFLICT (area_id, kind) DO UPDATE SET
    payload = EXCLUDED.payload, content_version = EXCLUDED.content_version,
    generated_at = EXCLUDED.generated_at, valid_until = EXCLUDED.valid_until
WHERE EXCLUDED.generated_at >= forecast_prepared.generated_at;
