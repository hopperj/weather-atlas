INSERT INTO simulation.run_artifact (
    run_id, artifact_kind, relative_path, sha256, size_bytes,
    mime_type, metadata, status
)
VALUES (
    %(run_id)s, %(artifact_kind)s, %(relative_path)s, %(sha256)s,
    %(size_bytes)s, %(mime_type)s, %(metadata)s::jsonb, %(status)s
)
ON CONFLICT (run_id, artifact_kind, relative_path) DO UPDATE
SET sha256 = EXCLUDED.sha256,
    size_bytes = EXCLUDED.size_bytes,
    mime_type = EXCLUDED.mime_type,
    metadata = EXCLUDED.metadata,
    status = EXCLUDED.status
RETURNING run_id, artifact_kind, relative_path, status;
