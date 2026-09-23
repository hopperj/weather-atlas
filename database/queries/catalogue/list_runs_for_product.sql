-- Parameters: product_code text, field_code text nullable,
-- before timestamptz nullable, limit integer
SELECT
    product_run.run_time,
    product_run.processing_status AS status,
    COUNT(DISTINCT product_time.id)::integer AS available_time_count
FROM catalogue.product_run
JOIN catalogue.product ON product.id = product_run.product_id
JOIN catalogue.product_time ON product_time.product_run_id = product_run.id
WHERE product.code = %(product_code)s
  AND product.enabled
  AND product_run.is_visible
  AND (
      %(before)s::timestamptz IS NULL
      OR product_run.run_time < %(before)s::timestamptz
  )
  AND EXISTS (
      SELECT 1
      FROM catalogue.asset
      JOIN catalogue.product_field
          ON product_field.id = asset.product_field_id
      JOIN catalogue.variable
          ON variable.id = product_field.variable_id
      JOIN catalogue.vertical_level
          ON vertical_level.id = product_field.vertical_level_id
      WHERE asset.product_time_id = product_time.id
        AND asset.status = 'available'
        AND asset.asset_role IN ('processed_cog', 'derived_cog')
        AND (
            %(field_code)s::text IS NULL
            OR COALESCE(
                product_field.metadata ->> 'field_code',
                variable.code || '_' || vertical_level.code
            ) = %(field_code)s
        )
  )
GROUP BY product_run.id
ORDER BY product_run.run_time DESC
LIMIT %(limit)s;
