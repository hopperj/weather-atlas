SELECT f.id, f.relative_path, f.content_sha256, f.bounds, f.provenance
FROM catalogue.imagery_frame f
JOIN catalogue.imagery_product p ON p.code = f.product_code AND p.enabled
WHERE f.id = %(id)s;
