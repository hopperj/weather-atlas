-- List displayable fields independently of their source product. A field is
-- exposed only after at least one visible run has an available processed asset.
WITH available_field AS (
    SELECT DISTINCT
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
        product.code AS product_code,
        product.priority
    FROM catalogue.product_field
    JOIN catalogue.product ON product.id = product_field.product_id
    JOIN catalogue.variable ON variable.id = product_field.variable_id
    JOIN catalogue.vertical_level
        ON vertical_level.id = product_field.vertical_level_id
    JOIN catalogue.asset ON asset.product_field_id = product_field.id
    JOIN catalogue.product_run ON product_run.id = asset.product_run_id
    WHERE product.enabled
      AND variable.enabled
      AND product_field.displayable
      AND product_run.is_visible
      AND asset.status = 'available'
      AND asset.asset_role IN ('processed_cog', 'derived_cog')
)
SELECT
    code,
    variable_code,
    name,
    variable_class,
    level_code,
    level_name,
    unit,
    array_agg(product_code ORDER BY priority, product_code) AS products
FROM available_field
GROUP BY
    code,
    variable_code,
    name,
    variable_class,
    level_code,
    level_name,
    unit
ORDER BY
    CASE variable_class
        WHEN 'atmosphere' THEN 1
        WHEN 'precipitation' THEN 2
        WHEN 'air_quality' THEN 3
        ELSE 4
    END,
    name,
    level_name,
    code;
