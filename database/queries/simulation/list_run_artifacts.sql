SELECT
    run_artifact.artifact_kind,
    run_artifact.relative_path,
    run_artifact.sha256,
    run_artifact.size_bytes,
    run_artifact.mime_type,
    run_artifact.metadata,
    run_artifact.status
FROM simulation.run_artifact
WHERE run_artifact.run_id = %(run_id)s
  AND run_artifact.status <> 'deleted'
ORDER BY run_artifact.artifact_kind, run_artifact.relative_path;
