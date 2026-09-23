-- Parameters: product_code, domain_code, run_times timestamptz[]
SELECT
    product_run.run_time,
    COALESCE(product_time.forecast_hour, 0) AS forecast_hour,
    COALESCE(
        product_field.metadata ->> 'field_code',
        variable.code || '_' || vertical_level.code
    ) AS field_code,
    asset.relative_path,
    asset.provenance ->> 'conversion_key' AS conversion_key
FROM catalogue.asset
JOIN catalogue.product_run ON product_run.id = asset.product_run_id
JOIN catalogue.product ON product.id = product_run.product_id
JOIN catalogue.domain ON domain.id = product_run.domain_id
JOIN catalogue.product_time ON product_time.id = asset.product_time_id
JOIN catalogue.product_field ON product_field.id = asset.product_field_id
JOIN catalogue.variable ON variable.id = product_field.variable_id
JOIN catalogue.vertical_level ON vertical_level.id = product_field.vertical_level_id
WHERE product.code = %(product_code)s
  AND domain.code = %(domain_code)s
  AND product_run.run_time = ANY(%(run_times)s::timestamptz[])
  AND asset.asset_role = 'processed_cog'
  AND asset.status = 'available';
