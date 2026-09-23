UPDATE simulation.run
SET status = %(new_status)s,
    metrics = metrics || %(metrics)s::jsonb,
    warnings = warnings || %(warnings)s::jsonb,
    error_class = %(error_class)s,
    error_message = %(error_message)s,
    completed_at = CASE
        WHEN %(new_status)s IN ('complete', 'complete_with_warnings', 'cancelled', 'failed')
        THEN clock_timestamp()
        ELSE completed_at
    END
WHERE id = %(run_id)s
  AND status = %(expected_status)s
RETURNING id, status, started_at, completed_at;
