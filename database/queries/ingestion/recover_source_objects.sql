-- Parameters: product_code text, limit integer
-- Return registered source objects that still have no available derived asset.
-- Rows deleted by the retired latest-run policy are revived in place so their
-- stable archive URLs can be downloaded again without requiring rediscovery.
WITH candidates AS MATERIALIZED (
    SELECT
        source_object.id,
        source_object.product_run_id
    FROM ingestion.source_object AS source_object
    JOIN catalogue.product ON product.id = source_object.product_id
    JOIN catalogue.product_run ON product_run.id = source_object.product_run_id
    WHERE product.code = %(product_code)s
      -- Keep confirmed historical gaps as failed records, not an endless queue.
      -- A fresh inventory/AMQP rediscovery can still explicitly enqueue them.
      AND source_object.last_error_class IS DISTINCT FROM 'SourceUnavailableError'
      AND source_object.status IN (
          'discovered',
          'downloading',
          'downloaded',
          'failed',
          'pending_deletion',
          'deleted'
      )
      AND NOT EXISTS (
          SELECT 1
          FROM catalogue.asset
          WHERE asset.product_run_id = source_object.product_run_id
            AND asset.status = 'available'
            AND source_object.sha256 IS NOT NULL
            AND asset.provenance ->> 'source_sha256' = source_object.sha256
      )
    ORDER BY product_run.run_time DESC, source_object.id
    LIMIT %(limit)s
    FOR UPDATE OF source_object SKIP LOCKED
),
revived_sources AS (
    UPDATE ingestion.source_object AS source_object
    SET status = CASE
            WHEN source_object.status IN (
                'downloading',
                'failed',
                'pending_deletion',
                'deleted'
            ) THEN 'discovered'
            ELSE source_object.status
        END,
        local_raw_path = CASE
            WHEN source_object.status IN ('pending_deletion', 'deleted') THEN NULL
            ELSE source_object.local_raw_path
        END,
        actual_size_bytes = CASE
            WHEN source_object.status IN ('pending_deletion', 'deleted') THEN NULL
            ELSE source_object.actual_size_bytes
        END,
        sha256 = CASE
            WHEN source_object.status IN ('pending_deletion', 'deleted') THEN NULL
            ELSE source_object.sha256
        END,
        downloaded_at = CASE
            WHEN source_object.status IN ('pending_deletion', 'deleted') THEN NULL
            ELSE source_object.downloaded_at
        END,
        last_error_class = NULL,
        last_error_message = NULL,
        last_error_detail = '{}'::jsonb,
        updated_at = clock_timestamp()
    FROM candidates
    WHERE source_object.id = candidates.id
    RETURNING source_object.id, source_object.product_run_id
),
revived_runs AS (
    UPDATE catalogue.product_run AS product_run
    SET source_status = CASE
            WHEN product_run.source_status IN ('expired', 'failed') THEN 'discovered'
            ELSE product_run.source_status
        END,
        processing_status = CASE
            WHEN product_run.processing_status IN ('expired', 'failed') THEN 'processing'
            ELSE product_run.processing_status
        END,
        completed_at = CASE
            WHEN product_run.source_status IN ('expired', 'failed')
              OR product_run.processing_status IN ('expired', 'failed')
                THEN NULL
            ELSE product_run.completed_at
        END,
        updated_at = clock_timestamp()
    WHERE product_run.id IN (
        SELECT DISTINCT revived_sources.product_run_id
        FROM revived_sources
    )
    RETURNING product_run.id
)
SELECT
    revived_sources.product_run_id,
    revived_sources.id AS source_object_id
FROM revived_sources
ORDER BY revived_sources.product_run_id, revived_sources.id;
