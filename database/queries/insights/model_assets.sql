-- Explicit runs, never the mixed-run display timeline. Bound both cycles and lead.
WITH runs AS (
    SELECT r.id, r.run_time FROM catalogue.product_run r
    JOIN catalogue.product p ON p.id = r.product_id
    JOIN catalogue.domain d ON d.id = r.domain_id
    WHERE p.code = 'gdps' AND d.code = 'global' AND r.is_visible
      AND r.run_time <= %(now)s AND r.run_time >= %(now)s - INTERVAL '36 hours'
    ORDER BY r.run_time DESC LIMIT 3
)
SELECT DISTINCT ON (r.run_time, t.valid_time, f.metadata->>'field_code')
    r.run_time, t.valid_time, t.interval_start, t.interval_end,
    f.metadata->>'field_code' AS field, v.canonical_unit AS unit,
    a.relative_path, a.sha256
FROM runs r
JOIN catalogue.product_time t ON t.product_run_id = r.id
JOIN catalogue.asset a ON a.product_time_id = t.id
JOIN catalogue.product_field f ON f.id = a.product_field_id
JOIN catalogue.variable v ON v.id = f.variable_id
WHERE a.status = 'available' AND a.asset_role IN ('processed_cog', 'derived_cog')
  AND t.forecast_hour BETWEEN 0 AND 84
  AND f.metadata->>'field_code' = ANY(%(fields)s)
ORDER BY r.run_time DESC, t.valid_time, f.metadata->>'field_code',
    CASE a.asset_role WHEN 'derived_cog' THEN 0 ELSE 1 END, a.created_at DESC
LIMIT 1500;
