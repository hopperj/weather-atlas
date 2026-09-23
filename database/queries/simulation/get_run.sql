SELECT
    run.id,
    run.scenario_revision_id,
    scenario_revision.scenario_id,
    run.run_kind,
    run.status,
    run.requested_at,
    run.queued_at,
    run.started_at,
    run.completed_at,
    run.requested_by,
    run.gfs_cycle_time,
    run.metrics,
    run.warnings,
    run.error_class,
    run.error_message,
    run.cancellation_requested_at
FROM simulation.run
JOIN simulation.scenario_revision ON scenario_revision.id = run.scenario_revision_id
WHERE run.id = %(run_id)s;
