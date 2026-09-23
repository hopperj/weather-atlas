INSERT INTO catalogue.imagery_frame (
    id, product_code, valid_time, configuration_sha256, content_sha256, relative_path, bounds, provenance
) VALUES (
    %(id)s, %(code)s, %(valid_time)s, %(configuration_sha256)s, %(content_sha256)s,
    %(relative_path)s, %(bounds)s, %(provenance)s
) ON CONFLICT (product_code, valid_time, configuration_sha256) DO NOTHING;
