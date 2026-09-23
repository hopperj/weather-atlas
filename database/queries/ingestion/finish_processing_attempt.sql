-- Parameters:
--   processing_attempt_id, status, completed_at, output_paths, metrics,
--   error_class, error_message, error_detail
UPDATE ingestion.processing_attempt
SET status = %(status)s,
    completed_at = %(completed_at)s,
    output_paths = %(output_paths)s,
    metrics = %(metrics)s,
    error_class = %(error_class)s,
    error_message = %(error_message)s,
    error_detail = %(error_detail)s
WHERE id = %(processing_attempt_id)s
  AND status IN ('queued', 'running')
RETURNING
    id,
    source_object_id,
    asset_id,
    attempt_type,
    attempt_number,
    status,
    started_at,
    completed_at,
    metrics,
    error_class,
    error_message,
    error_detail;
