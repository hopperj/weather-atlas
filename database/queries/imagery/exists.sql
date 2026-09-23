SELECT id FROM catalogue.imagery_frame
WHERE product_code = %(code)s AND valid_time = %(valid_time)s
  AND configuration_sha256 = %(configuration_sha256)s;
