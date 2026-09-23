-- Parameters: source_object_id bigint.
WITH updated AS (
    UPDATE ingestion.source_object
    SET status = 'deleted', updated_at = clock_timestamp()
    WHERE id = %(source_object_id)s
      AND status = 'pending_deletion'
    RETURNING id, local_raw_path AS relative_path, status
), recorded AS (
    INSERT INTO audit.event (event_type, object_type, object_key, details)
    SELECT
        'maintenance.source_deleted',
        'ingestion.source_object',
        updated.id::text,
        jsonb_build_object('relative_path', updated.relative_path)
    FROM updated
)
SELECT updated.id, updated.relative_path, updated.status
FROM updated;
