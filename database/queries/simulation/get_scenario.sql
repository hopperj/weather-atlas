SELECT
    scenario.id,
    scenario.name,
    scenario.description,
    scenario.owner_label,
    scenario.created_at,
    scenario.updated_at,
    scenario.archived_at
FROM simulation.scenario
WHERE scenario.id = %(scenario_id)s;
