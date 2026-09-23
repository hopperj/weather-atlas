-- Parameters: source_object_id, error_class, error_message, error_detail
UPDATE ingestion.source_object
SET status = 'failed',
    last_error_class = %(error_class)s,
    last_error_message = %(error_message)s,
    last_error_detail = %(error_detail)s,
    updated_at = clock_timestamp()
WHERE id = %(source_object_id)s
  AND status NOT IN ('pending_deletion', 'deleted')
RETURNING
    id,
    status,
    download_attempts,
    last_error_class,
    last_error_message,
    last_error_detail,
    updated_at;
