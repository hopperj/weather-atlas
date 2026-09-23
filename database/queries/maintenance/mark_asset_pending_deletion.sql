-- Parameters: asset_id bigint.
WITH updated AS (
    UPDATE catalogue.asset
    SET status = 'pending_deletion', updated_at = clock_timestamp()
    WHERE id = %(asset_id)s
      AND status IN ('available', 'failed', 'pending_deletion')
    RETURNING id, relative_path, status
), recorded AS (
    INSERT INTO audit.event (event_type, object_type, object_key, details)
    SELECT
        'maintenance.asset_pending_deletion',
        'catalogue.asset',
        updated.id::text,
        jsonb_build_object('relative_path', updated.relative_path)
    FROM updated
)
SELECT updated.id, updated.relative_path, updated.status
FROM updated;
