SELECT DISTINCT ON (valid_time) id, valid_time, bounds
FROM catalogue.imagery_frame
WHERE product_code = %(code)s AND valid_time >= now() - interval '24 hours'
ORDER BY valid_time DESC, collected_at DESC LIMIT 240;
