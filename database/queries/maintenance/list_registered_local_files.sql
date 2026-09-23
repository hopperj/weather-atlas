-- Parameters: limit integer.
-- The window total lets the caller state when a bounded audit was truncated.
WITH registered_file AS (
    SELECT
        'asset'::text AS object_kind,
        asset.id AS object_id,
        asset.relative_path,
        asset.file_size_bytes,
        asset.sha256,
        asset.status
    FROM catalogue.asset AS asset
    WHERE asset.storage_backend = 'local'
      AND asset.status IN ('available', 'pending_deletion', 'failed')

    UNION ALL

    SELECT
        'source'::text AS object_kind,
        source_object.id AS object_id,
        source_object.local_raw_path AS relative_path,
        source_object.actual_size_bytes AS file_size_bytes,
        source_object.sha256,
        source_object.status
    FROM ingestion.source_object AS source_object
    WHERE source_object.local_raw_path IS NOT NULL
      AND source_object.status IN (
          'downloaded', 'validated', 'quarantined', 'failed', 'pending_deletion'
      )
)
SELECT
    object_kind,
    object_id,
    relative_path,
    file_size_bytes,
    sha256,
    status,
    count(*) OVER () AS total_registered
FROM registered_file
ORDER BY object_kind, object_id
LIMIT %(limit)s;
