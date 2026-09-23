WITH target_scenario AS (
    SELECT scenario.id
    FROM simulation.scenario
    WHERE scenario.id = %(scenario_id)s
      AND scenario.archived_at IS NULL
    FOR UPDATE
),
next_revision AS (
    SELECT
        target_scenario.id AS scenario_id,
        COALESCE(max(existing.revision_number), 0) + 1 AS revision_number
    FROM target_scenario
    LEFT JOIN simulation.scenario_revision AS existing
        ON existing.scenario_id = target_scenario.id
    GROUP BY target_scenario.id
),
inserted AS (
    INSERT INTO simulation.scenario_revision (
        scenario_id, revision_number, canonical_config, config_sha256
    )
    SELECT
        next_revision.scenario_id,
        next_revision.revision_number,
        %(canonical_config)s::jsonb,
        %(config_sha256)s
    FROM next_revision
    ON CONFLICT (scenario_id, config_sha256) DO NOTHING
    RETURNING id, scenario_id, revision_number, canonical_config, config_sha256, created_at
)
SELECT
    inserted.id,
    inserted.scenario_id,
    inserted.revision_number,
    inserted.canonical_config,
    inserted.config_sha256,
    inserted.created_at
FROM inserted
UNION ALL
SELECT
    existing.id,
    existing.scenario_id,
    existing.revision_number,
    existing.canonical_config,
    existing.config_sha256,
    existing.created_at
FROM simulation.scenario_revision AS existing
WHERE existing.scenario_id = %(scenario_id)s
  AND existing.config_sha256 = %(config_sha256)s
  AND NOT EXISTS (SELECT 1 FROM inserted)
LIMIT 1;
