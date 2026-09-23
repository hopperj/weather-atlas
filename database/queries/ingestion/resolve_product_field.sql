-- Parameters: product_code, field_code
SELECT
    product.id AS product_id,
    product_field.id AS product_field_id,
    product_field.vertical_level_id,
    variable.code AS variable_code,
    vertical_level.code AS level_code
FROM catalogue.product_field
JOIN catalogue.product ON product.id = product_field.product_id
JOIN catalogue.variable ON variable.id = product_field.variable_id
JOIN catalogue.vertical_level ON vertical_level.id = product_field.vertical_level_id
WHERE product.code = %(product_code)s
  AND COALESCE(
      product_field.metadata ->> 'field_code',
      variable.code || '_' || vertical_level.code
  ) = %(field_code)s
  AND product_field.processing_enabled
LIMIT 1;
