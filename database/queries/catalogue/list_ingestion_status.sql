-- Latest ingestion state for each enabled product; no parameters.
SELECT
    product.code AS product_code,
    latest.run_time,
    latest.source_status,
    latest.processing_status,
    COALESCE(latest.is_visible, false) AS is_visible,
    COALESCE(latest.expected_asset_count, 0) AS expected_asset_count,
    COALESCE(latest.discovered_asset_count, 0) AS discovered_asset_count,
    COALESCE(latest.downloaded_asset_count, 0) AS downloaded_asset_count,
    COALESCE(latest.processed_asset_count, 0) AS processed_asset_count,
    COALESCE(latest.failed_asset_count, 0) AS failed_asset_count,
    latest.first_discovered_at,
    latest.completed_at
FROM catalogue.product
LEFT JOIN LATERAL (
    SELECT
        product_run.run_time,
        product_run.source_status,
        product_run.processing_status,
        product_run.is_visible,
        product_run.expected_asset_count,
        product_run.discovered_asset_count,
        product_run.downloaded_asset_count,
        product_run.processed_asset_count,
        product_run.failed_asset_count,
        product_run.first_discovered_at,
        product_run.completed_at
    FROM catalogue.product_run
    WHERE product_run.product_id = product.id
    ORDER BY product_run.run_time DESC
    LIMIT 1
) AS latest ON true
WHERE product.enabled
ORDER BY product.priority, product.code;
