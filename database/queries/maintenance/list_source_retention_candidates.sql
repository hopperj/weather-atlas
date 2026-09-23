-- Parameters: as_of timestamptz, limit integer.
-- Source objects without a run use their observed/download timestamp.
SELECT
    source_object.id,
    source_object.local_raw_path AS relative_path,
    source_object.actual_size_bytes AS file_size_bytes,
    source_object.sha256,
    source_object.status,
    product.code AS product_code,
    COALESCE(product_run.run_time, source_object.downloaded_at,
        source_object.last_observed_at) AS source_time,
    COALESCE((product.retention_config ->> 'raw_days')::integer, 30)
        AS retention_days
FROM ingestion.source_object AS source_object
JOIN catalogue.product AS product ON product.id = source_object.product_id
LEFT JOIN catalogue.product_run AS product_run ON product_run.id = source_object.product_run_id
WHERE source_object.local_raw_path IS NOT NULL
  AND NOT EXISTS (
      SELECT 1
      FROM simulation.run_input
      WHERE run_input.relative_path = source_object.local_raw_path
  )
  AND (
      source_object.status = 'pending_deletion'
      OR (
          NOT COALESCE(
              (product.retention_config ->> 'retain_forever')::boolean,
              false
          )
          AND
          source_object.status IN ('downloaded', 'validated', 'quarantined', 'failed')
          AND COALESCE(product_run.run_time, source_object.downloaded_at,
              source_object.last_observed_at) < (
              %(as_of)s::timestamptz
              - make_interval(
                  days => COALESCE(
                      (product.retention_config ->> 'raw_days')::integer,
                      30
                  )
              )
          )
      )
  )
ORDER BY
    (source_object.status = 'pending_deletion') DESC,
    COALESCE(product_run.run_time, source_object.downloaded_at,
        source_object.last_observed_at),
    source_object.id
LIMIT %(limit)s;
