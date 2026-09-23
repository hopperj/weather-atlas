WITH existing AS (
    SELECT
        run.id,
        run.scenario_revision_id,
        run.run_kind,
        run.status,
        run.requested_at,
        run.queued_at
    FROM simulation.run AS run
    WHERE run.run_key = %(run_key)s
),
inserted AS (
    INSERT INTO simulation.run (
        scenario_revision_id, run_kind, requested_by, run_key, random_seed_policy
    )
    SELECT
        %(scenario_revision_id)s, %(run_kind)s, %(requested_by)s, %(run_key)s,
        %(random_seed_policy)s::jsonb
    WHERE NOT EXISTS (SELECT 1 FROM existing)
      AND (
          SELECT count(*)
          FROM simulation.run AS queued_run
          WHERE queued_run.status = 'queued'
      ) < %(maximum_queued_runs)s
    ON CONFLICT (run_key) DO NOTHING
    RETURNING id, scenario_revision_id, run_kind, status, requested_at, queued_at
)
SELECT
    inserted.id,
    inserted.scenario_revision_id,
    inserted.run_kind,
    inserted.status,
    inserted.requested_at,
    inserted.queued_at,
    true AS created
FROM inserted
UNION ALL
SELECT
    existing.id,
    existing.scenario_revision_id,
    existing.run_kind,
    existing.status,
    existing.requested_at,
    existing.queued_at,
    false AS created
FROM existing
WHERE NOT EXISTS (SELECT 1 FROM inserted)
LIMIT 1;
