-- Public enabled products, including the newest visible run when one exists.
SELECT
    product.code,
    product.name,
    NULLIF(product.description, '') AS description,
    product.product_kind AS kind,
    product.priority,
    latest_run.run_time AS latest_run_time
FROM catalogue.product AS product
LEFT JOIN LATERAL (
    SELECT product_run.run_time
    FROM catalogue.product_run
    WHERE product_run.product_id = product.id
      AND product_run.is_visible
      AND EXISTS (
          SELECT 1
          FROM catalogue.asset
          WHERE asset.product_run_id = product_run.id
            AND asset.status = 'available'
            AND asset.asset_role IN ('processed_cog', 'derived_cog')
      )
    ORDER BY product_run.run_time DESC
    LIMIT 1
) AS latest_run ON true
WHERE product.enabled
ORDER BY product.priority, product.code;
