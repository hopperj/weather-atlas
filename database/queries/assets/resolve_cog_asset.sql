-- Parameters: product_code, domain_code, run_time, field_code, valid_time, style_code
SELECT
    asset.id AS asset_id,
    asset.relative_path,
    variable_style.id AS style_id,
    asset.sha256 AS asset_sha256,
    product.code AS product,
    domain.code AS domain,
    product_run.run_time,
    product_time.valid_time,
    product_time.forecast_hour,
    COALESCE(
        product_field.metadata ->> 'field_code',
        variable.code || '_' || vertical_level.code
    ) AS field,
    variable.code AS variable,
    vertical_level.code AS level,
    variable.canonical_unit AS unit,
    ARRAY[
        ST_XMin(Box3D(asset.bounds)),
        ST_YMin(Box3D(asset.bounds)),
        ST_XMax(Box3D(asset.bounds)),
        ST_YMax(Box3D(asset.bounds))
    ] AS bounds,
    palette.definition AS palette_definition,
    asset.minimum_value AS data_min,
    asset.maximum_value AS data_max,
    variable_style.default_min AS display_min,
    variable_style.default_max AS display_max
FROM catalogue.asset
JOIN catalogue.product ON product.id = asset.product_id
JOIN catalogue.product_run ON product_run.id = asset.product_run_id
JOIN catalogue.domain ON domain.id = product_run.domain_id
JOIN catalogue.product_time ON product_time.id = asset.product_time_id
JOIN catalogue.product_field ON product_field.id = asset.product_field_id
JOIN catalogue.variable ON variable.id = product_field.variable_id
JOIN catalogue.vertical_level ON vertical_level.id = asset.vertical_level_id
JOIN LATERAL (
    SELECT candidate.*
    FROM display.variable_style AS candidate
    WHERE candidate.variable_id = variable.id
      AND candidate.enabled
      AND candidate.code = %(style_code)s
      AND (candidate.product_field_id = product_field.id OR candidate.product_field_id IS NULL)
    ORDER BY (candidate.product_field_id IS NOT NULL) DESC, candidate.revision DESC
    LIMIT 1
) AS variable_style ON true
JOIN display.palette ON palette.id = variable_style.palette_id AND palette.enabled
WHERE product.code = %(product_code)s
  AND domain.code = %(domain_code)s
  AND product_run.run_time = %(run_time)s
  AND product_run.is_visible
  AND product_time.valid_time = %(valid_time)s
  AND COALESCE(
      product_field.metadata ->> 'field_code',
      variable.code || '_' || vertical_level.code
  ) = %(field_code)s
  AND asset.status = 'available'
  AND asset.asset_role IN ('processed_cog', 'derived_cog')
ORDER BY CASE asset.asset_role WHEN 'derived_cog' THEN 0 ELSE 1 END
LIMIT 1;
