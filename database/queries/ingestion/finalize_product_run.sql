-- Parameters: product_run_id, required_field_codes text[]
WITH source_counts AS (
    SELECT
        COUNT(*)::integer AS discovered_count,
        COUNT(*) FILTER (WHERE status = 'downloaded')::integer AS downloaded_count,
        COUNT(*) FILTER (WHERE status = 'failed')::integer AS failed_source_count
    FROM ingestion.source_object
    WHERE product_run_id = %(product_run_id)s
      AND status NOT IN ('pending_deletion', 'deleted')
),
asset_counts AS (
    SELECT
        COUNT(*) FILTER (WHERE status = 'available')::integer AS processed_count,
        COUNT(*) FILTER (WHERE status = 'failed')::integer AS failed_asset_count
    FROM catalogue.asset
    WHERE product_run_id = %(product_run_id)s
),
required_state AS (
    SELECT NOT EXISTS (
        SELECT 1
        FROM unnest(%(required_field_codes)s::text[]) AS required(field_code)
        WHERE NOT EXISTS (
            SELECT 1
            FROM catalogue.asset
            JOIN catalogue.product_field
                ON product_field.id = asset.product_field_id
            JOIN catalogue.variable ON variable.id = product_field.variable_id
            JOIN catalogue.vertical_level
                ON vertical_level.id = product_field.vertical_level_id
            WHERE asset.product_run_id = %(product_run_id)s
              AND asset.status = 'available'
              AND COALESCE(
                  product_field.metadata ->> 'field_code',
                  variable.code || '_' || vertical_level.code
              ) = required.field_code
        )
    ) AS core_available
)
UPDATE catalogue.product_run
SET source_status = CASE
        WHEN source_counts.failed_source_count > 0 THEN 'partially_available'
        WHEN source_counts.discovered_count > 0
             AND source_counts.discovered_count >= product_run.expected_asset_count
             AND source_counts.downloaded_count = source_counts.discovered_count THEN 'complete'
        ELSE 'partially_available'
    END,
    processing_status = CASE
        WHEN asset_counts.processed_count = 0 THEN 'failed'
        WHEN asset_counts.processed_count < product_run.expected_asset_count
            THEN 'partially_available'
        WHEN source_counts.failed_source_count > 0 OR asset_counts.failed_asset_count > 0
            THEN 'complete_with_warnings'
        ELSE 'complete'
    END,
    is_visible = required_state.core_available AND asset_counts.processed_count > 0,
    expected_asset_count = GREATEST(expected_asset_count, source_counts.discovered_count),
    discovered_asset_count = source_counts.discovered_count,
    downloaded_asset_count = source_counts.downloaded_count,
    processed_asset_count = asset_counts.processed_count,
    failed_asset_count = source_counts.failed_source_count + asset_counts.failed_asset_count,
    completed_at = CASE
        WHEN asset_counts.processed_count = 0
          OR asset_counts.processed_count >= product_run.expected_asset_count
            THEN clock_timestamp()
        ELSE NULL
    END,
    updated_at = clock_timestamp()
FROM source_counts, asset_counts, required_state
WHERE product_run.id = %(product_run_id)s
RETURNING
    product_run.id,
    product_run.source_status,
    product_run.processing_status,
    product_run.is_visible,
    product_run.expected_asset_count,
    product_run.discovered_asset_count,
    product_run.downloaded_asset_count,
    product_run.processed_asset_count,
    product_run.failed_asset_count,
    product_run.completed_at;
