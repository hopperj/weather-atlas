-- Parameters: product_code text, run_time timestamptz nullable
SELECT
    COALESCE(
        product_field.metadata ->> 'field_code',
        variable.code || '_' || vertical_level.code
    ) AS code,
    variable.code AS variable_code,
    COALESCE(product_field.metadata ->> 'display_name', variable.name) AS name,
    variable.variable_class,
    vertical_level.code AS level_code,
    vertical_level.name AS level_name,
    variable.canonical_unit AS unit,
    palette.definition -> 'stops' AS palette,
    variable_style.default_min,
    variable_style.default_max
FROM catalogue.product_field
JOIN catalogue.product ON product.id = product_field.product_id
JOIN catalogue.variable ON variable.id = product_field.variable_id
JOIN catalogue.vertical_level ON vertical_level.id = product_field.vertical_level_id
JOIN LATERAL (
    SELECT candidate.*
    FROM display.variable_style AS candidate
    WHERE candidate.variable_id = variable.id
      AND candidate.enabled
      AND candidate.code = 'default'
      AND (candidate.product_field_id = product_field.id OR candidate.product_field_id IS NULL)
    ORDER BY (candidate.product_field_id IS NOT NULL) DESC, candidate.revision DESC
    LIMIT 1
) AS variable_style ON true
JOIN display.palette ON palette.id = variable_style.palette_id AND palette.enabled
WHERE product.code = %(product_code)s
  AND product.enabled
  AND variable.enabled
  AND product_field.displayable
  AND (
      %(run_time)s::timestamptz IS NULL
      OR EXISTS (
          SELECT 1
          FROM catalogue.asset
          JOIN catalogue.product_run ON product_run.id = asset.product_run_id
          WHERE asset.product_field_id = product_field.id
            AND asset.status = 'available'
            AND product_run.run_time = %(run_time)s::timestamptz
            AND product_run.is_visible
      )
  )
ORDER BY variable.variable_class, variable.name, vertical_level.display_order;
