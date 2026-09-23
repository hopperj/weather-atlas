-- Parameters: source_object_id
UPDATE ingestion.source_object
SET status = 'downloading',
    download_attempts = download_attempts + 1,
    last_error_class = NULL,
    last_error_message = NULL,
    last_error_detail = '{}'::jsonb,
    updated_at = clock_timestamp()
WHERE id = %(source_object_id)s
  AND status NOT IN ('pending_deletion', 'deleted')
RETURNING
    id,
    status,
    download_attempts,
    updated_at;
