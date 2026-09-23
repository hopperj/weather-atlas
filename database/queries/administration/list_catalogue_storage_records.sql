-- Read-only storage records for filesystem integrity reporting.
-- Parameters: none.
SELECT
    'asset' AS record_kind,
    relative_path,
    file_size_bytes::text AS expected_size,
    sha256 AS expected_sha256
FROM catalogue.asset
WHERE status IN ('available', 'pending_deletion')

UNION ALL

SELECT
    'source' AS record_kind,
    local_raw_path AS relative_path,
    COALESCE(actual_size_bytes::text, '') AS expected_size,
    COALESCE(sha256, '') AS expected_sha256
FROM ingestion.source_object
WHERE status IN ('downloaded', 'validated', 'quarantined', 'pending_deletion')
  AND local_raw_path IS NOT NULL

ORDER BY record_kind, relative_path;
