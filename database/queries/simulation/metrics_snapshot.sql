WITH run_counts AS (
    SELECT run.status, count(*) AS run_count
    FROM simulation.run AS run
    GROUP BY run.status
),
latest_terminal AS (
    SELECT run.metrics, run.completed_at
    FROM simulation.run AS run
    WHERE run.status IN ('complete', 'complete_with_warnings', 'cancelled', 'failed')
    ORDER BY run.completed_at DESC, run.id DESC
    LIMIT 1
)
SELECT
    COALESCE(
        (SELECT jsonb_object_agg(run_counts.status, run_counts.run_count) FROM run_counts),
        '{}'::jsonb
    ) AS run_counts,
    COALESCE(latest_terminal.metrics, '{}'::jsonb) AS latest_metrics,
    COALESCE(extract(epoch FROM latest_terminal.completed_at), 0) AS last_completed_epoch
FROM (VALUES (1)) AS singleton(value)
LEFT JOIN latest_terminal ON true;
