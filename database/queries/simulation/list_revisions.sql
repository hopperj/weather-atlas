SELECT
    scenario_revision.id,
    scenario_revision.scenario_id,
    scenario_revision.revision_number,
    scenario_revision.canonical_config,
    scenario_revision.config_sha256,
    scenario_revision.created_at
FROM simulation.scenario_revision
WHERE scenario_revision.scenario_id = %(scenario_id)s
ORDER BY scenario_revision.revision_number DESC;
