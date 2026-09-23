UPDATE simulation.run
SET status = 'resolving_inputs',
    started_at = COALESCE(started_at, clock_timestamp())
WHERE id = (
    SELECT candidate.id
    FROM simulation.run AS candidate
    WHERE candidate.status = 'queued'
      AND (
          %(allowed_run_kind)s::text IS NULL
          OR candidate.run_kind = %(allowed_run_kind)s::text
      )
    ORDER BY candidate.requested_at, candidate.id
    FOR UPDATE SKIP LOCKED
    LIMIT 1
)
RETURNING id, scenario_revision_id, status, requested_at, started_at;
