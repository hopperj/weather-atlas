SELECT
    scenario.id,
    scenario.name,
    scenario.description,
    scenario.owner_label,
    scenario.created_at,
    scenario.updated_at,
    scenario.archived_at,
    count(scenario_revision.id)::integer AS revision_count
FROM simulation.scenario
LEFT JOIN simulation.scenario_revision ON scenario_revision.scenario_id = scenario.id
WHERE scenario.archived_at IS NULL
GROUP BY scenario.id
ORDER BY scenario.updated_at DESC, scenario.id
LIMIT %(limit)s;
