-- Parameters: product_code
SELECT
    product_run.id,
    product_run.run_time
FROM catalogue.product_run
JOIN catalogue.product ON product.id = product_run.product_id
WHERE product.code = %(product_code)s
  AND product_run.is_visible
ORDER BY product_run.run_time DESC
LIMIT 1;
