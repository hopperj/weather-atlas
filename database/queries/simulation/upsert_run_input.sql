INSERT INTO simulation.run_input (
    run_id, input_kind, relative_path, sha256, size_bytes, metadata
)
VALUES (
    %(run_id)s, %(input_kind)s, %(relative_path)s, %(sha256)s,
    %(size_bytes)s, %(metadata)s::jsonb
)
ON CONFLICT (run_id, input_kind, relative_path) DO UPDATE
SET sha256 = EXCLUDED.sha256,
    size_bytes = EXCLUDED.size_bytes,
    metadata = EXCLUDED.metadata
RETURNING run_id, input_kind, relative_path;
