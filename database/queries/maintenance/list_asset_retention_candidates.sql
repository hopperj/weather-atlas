-- Parameters: as_of timestamptz, limit integer.
-- Pending rows are always resumable. Other rows qualify by the owning
-- product's processed retention policy and model run time. Files retained as
-- simulation inputs or artifacts are never candidates.
WITH classified AS (
    SELECT
        asset.id,
        asset.relative_path,
        asset.file_size_bytes,
        asset.sha256,
        asset.status,
        product.code AS product_code,
        product_run.run_time,
        CASE
            WHEN product.code = 'flexpart_smoke'
                AND simulation_run.run_kind = 'operational'
            THEN COALESCE(
                (product.retention_config ->> 'operational_days')::integer,
                14
            )
            WHEN product.code = 'flexpart_smoke'
            THEN COALESCE(
                (product.retention_config ->> 'interactive_days')::integer,
                30
            )
            ELSE COALESCE(
                (product.retention_config ->> 'processed_days')::integer,
                180
            )
        END AS retention_days,
        COALESCE(
            (product.retention_config ->> 'retain_forever')::boolean,
            false
        ) AS retain_forever
    FROM catalogue.asset AS asset
    JOIN catalogue.product AS product ON product.id = asset.product_id
    JOIN catalogue.product_run AS product_run ON product_run.id = asset.product_run_id
    LEFT JOIN simulation.run AS simulation_run
        ON simulation_run.id = product_run.simulation_run_id
    WHERE asset.storage_backend = 'local'
      AND NOT EXISTS (
          SELECT 1
          FROM simulation.run_artifact
          WHERE run_artifact.relative_path = asset.relative_path
            AND run_artifact.status <> 'deleted'
      )
      AND NOT EXISTS (
          SELECT 1
          FROM simulation.run_input
          WHERE run_input.relative_path = asset.relative_path
      )
)
SELECT
    classified.id,
    classified.relative_path,
    classified.file_size_bytes,
    classified.sha256,
    classified.status,
    classified.product_code,
    classified.run_time,
    classified.retention_days
FROM classified
WHERE classified.status = 'pending_deletion'
   OR (
       NOT classified.retain_forever
       AND classified.status IN ('available', 'failed')
       AND classified.run_time < (
           %(as_of)s::timestamptz
           - make_interval(days => classified.retention_days)
       )
   )
ORDER BY
    (classified.status = 'pending_deletion') DESC,
    classified.run_time,
    classified.id
LIMIT %(limit)s;
