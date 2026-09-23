-- Parameters: product_code text
SELECT
    domain.code,
    domain.name,
    CASE
        WHEN domain.footprint IS NULL THEN NULL
        ELSE ARRAY[
            ST_XMin(Box3D(domain.footprint)),
            ST_YMin(Box3D(domain.footprint)),
            ST_XMax(Box3D(domain.footprint)),
            ST_YMax(Box3D(domain.footprint))
        ]
    END AS bounds
FROM catalogue.domain
JOIN catalogue.product ON product.id = domain.product_id
WHERE product.code = %(product_code)s
  AND product.enabled
  AND domain.enabled
ORDER BY domain.code;
