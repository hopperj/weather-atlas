-- Parameters: product_run_ids bigint[]
SELECT
    asset.relative_path,
    asset.provenance ->> 'conversion_key' AS conversion_key
FROM catalogue.asset
WHERE asset.product_run_id = ANY(%(product_run_ids)s::bigint[])
  AND asset.asset_role = 'processed_cog'
  AND asset.status = 'available';
