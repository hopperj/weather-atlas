-- Parameters: product_code text, run_time timestamptz, field_code text nullable
SELECT DISTINCT
    product_time.valid_time,
    product_time.forecast_hour,
    product_time.interval_start,
    product_time.interval_end,
    product_time.time_kind
FROM catalogue.product_time
JOIN catalogue.product_run ON product_run.id = product_time.product_run_id
JOIN catalogue.product ON product.id = product_run.product_id
WHERE product.code = %(product_code)s
  AND product_run.run_time = %(run_time)s
  AND product_run.is_visible
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
ORDER BY product_time.valid_time;
