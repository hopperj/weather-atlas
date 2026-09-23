-- Parameters:
--   product_code, domain_code, run_time, source_status, processing_status,
--   source_manifest, expected_asset_count, discovered_asset_count
WITH resolved_identity AS (
    SELECT
        product.id AS product_id,
        domain.id AS domain_id
    FROM catalogue.product AS product
    JOIN catalogue.domain AS domain ON domain.product_id = product.id
    WHERE product.code = %(product_code)s
      AND domain.code = %(domain_code)s
)
INSERT INTO catalogue.product_run (
    product_id,
    domain_id,
    run_time,
    source_status,
    processing_status,
    source_manifest,
    expected_asset_count,
    discovered_asset_count
)
SELECT
    resolved_identity.product_id,
    resolved_identity.domain_id,
    %(run_time)s,
    %(source_status)s,
    %(processing_status)s,
    %(source_manifest)s,
    %(expected_asset_count)s,
    %(discovered_asset_count)s
FROM resolved_identity
ON CONFLICT (product_id, domain_id, run_time) DO UPDATE
SET source_status = CASE
        WHEN catalogue.product_run.source_status = 'expired'
            THEN EXCLUDED.source_status
        WHEN catalogue.product_run.completed_at IS NOT NULL
            THEN catalogue.product_run.source_status
        ELSE EXCLUDED.source_status
    END,
    processing_status = CASE
        WHEN catalogue.product_run.processing_status = 'expired'
            THEN EXCLUDED.processing_status
        WHEN catalogue.product_run.completed_at IS NOT NULL
            THEN catalogue.product_run.processing_status
        ELSE EXCLUDED.processing_status
    END,
    source_manifest = EXCLUDED.source_manifest,
    expected_asset_count = GREATEST(
        catalogue.product_run.expected_asset_count,
        EXCLUDED.expected_asset_count
    ),
    discovered_asset_count = GREATEST(
        catalogue.product_run.discovered_asset_count,
        EXCLUDED.discovered_asset_count
    ),
    completed_at = CASE
        WHEN catalogue.product_run.source_status = 'expired'
          OR catalogue.product_run.processing_status = 'expired'
            THEN NULL
        ELSE catalogue.product_run.completed_at
    END,
    updated_at = clock_timestamp()
RETURNING
    id,
    product_id,
    domain_id,
    run_time,
    source_status,
    processing_status,
    is_visible,
    expected_asset_count,
    discovered_asset_count,
    downloaded_asset_count,
    processed_asset_count,
    failed_asset_count,
    first_discovered_at,
    completed_at,
    created_at,
    updated_at;
