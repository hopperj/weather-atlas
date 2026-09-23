SELECT
    run.id,
    run.status,
    run.run_kind,
    run.requested_at,
    run.scenario_revision_id,
    scenario_revision.scenario_id,
    scenario_revision.canonical_config,
    scenario_revision.config_sha256
FROM simulation.run
JOIN simulation.scenario_revision ON scenario_revision.id = run.scenario_revision_id
WHERE run.id = %(run_id)s;
