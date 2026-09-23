-- Parameters:
--   source_object_id (nullable), asset_id (nullable), attempt_type,
--   attempt_number, status, started_at, worker_hostname, input_paths,
--   output_paths, command_line, tool_versions
INSERT INTO ingestion.processing_attempt (
    source_object_id,
    asset_id,
    attempt_type,
    attempt_number,
    status,
    started_at,
    worker_hostname,
    input_paths,
    output_paths,
    command_line,
    tool_versions
)
VALUES (
    %(source_object_id)s,
    %(asset_id)s,
    %(attempt_type)s,
    %(attempt_number)s,
    %(status)s,
    %(started_at)s,
    %(worker_hostname)s,
    %(input_paths)s,
    %(output_paths)s,
    %(command_line)s,
    %(tool_versions)s
)
ON CONFLICT (source_object_id, asset_id, attempt_type, attempt_number) DO NOTHING
RETURNING
    id,
    source_object_id,
    asset_id,
    attempt_type,
    attempt_number,
    status,
    started_at,
    worker_hostname,
    created_at;
