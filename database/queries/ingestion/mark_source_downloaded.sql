-- Parameters:
--   source_object_id, local_raw_path, actual_size_bytes, sha256, downloaded_at
UPDATE ingestion.source_object
SET local_raw_path = %(local_raw_path)s,
    actual_size_bytes = %(actual_size_bytes)s,
    sha256 = %(sha256)s,
    status = 'downloaded',
    downloaded_at = %(downloaded_at)s,
    last_error_class = NULL,
    last_error_message = NULL,
    last_error_detail = '{}'::jsonb,
    updated_at = clock_timestamp()
WHERE id = %(source_object_id)s
  AND status = 'downloading'
RETURNING
    id,
    product_id,
    product_run_id,
    canonical_key,
    local_raw_path,
    actual_size_bytes,
    sha256,
    status,
    download_attempts,
    downloaded_at,
    updated_at;
