-- Parameters: product_code, keep_product_run_id, limit
WITH keep_run AS (
    SELECT product_run.product_id, product_run.run_time
    FROM catalogue.product_run
    JOIN catalogue.product ON product.id = product_run.product_id
    WHERE product_run.id = %(keep_product_run_id)s
      AND product.code = %(product_code)s
), superseded_file AS (
    SELECT
        'asset'::text AS object_kind,
        asset.id,
        asset.relative_path,
        asset.file_size_bytes,
        asset.sha256,
        asset.status,
        product_run.run_time
    FROM catalogue.asset AS asset
    JOIN catalogue.product_run ON product_run.id = asset.product_run_id
    JOIN catalogue.product_field ON product_field.id = asset.product_field_id
    JOIN keep_run ON keep_run.product_id = product_run.product_id
    WHERE (
          product_run.run_time < keep_run.run_time
          OR NOT product_field.processing_enabled
      )
      AND asset.storage_backend = 'local'
      AND asset.status IN ('available', 'failed', 'pending_deletion')

    UNION ALL

    SELECT
        'source'::text AS object_kind,
        source_object.id,
        source_object.local_raw_path AS relative_path,
        source_object.actual_size_bytes AS file_size_bytes,
        source_object.sha256,
        source_object.status,
        product_run.run_time
    FROM ingestion.source_object AS source_object
    JOIN catalogue.product_run ON product_run.id = source_object.product_run_id
    JOIN keep_run ON keep_run.product_id = product_run.product_id
    WHERE (
          product_run.run_time < keep_run.run_time
          OR EXISTS (
              SELECT 1
              FROM catalogue.asset AS source_asset
              JOIN catalogue.product_field
                ON product_field.id = source_asset.product_field_id
              WHERE source_asset.product_run_id = source_object.product_run_id
                AND source_asset.provenance ->> 'source_sha256' = source_object.sha256
                AND NOT product_field.processing_enabled
          )
      )
      AND source_object.local_raw_path IS NOT NULL
      AND source_object.status IN (
          'downloaded', 'validated', 'quarantined', 'failed', 'pending_deletion'
      )
)
SELECT
    object_kind,
    id,
    relative_path,
    file_size_bytes,
    sha256,
    status
FROM superseded_file
ORDER BY run_time, object_kind, id
LIMIT %(limit)s;
