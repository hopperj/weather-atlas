UPDATE simulation.run
SET status = CASE WHEN status = 'queued' THEN 'cancelled' ELSE 'cancellation_requested' END,
    cancellation_requested_at = clock_timestamp(),
    completed_at = CASE WHEN status = 'queued' THEN clock_timestamp() ELSE completed_at END
WHERE id = %(run_id)s
  AND status IN (
      'queued', 'resolving_inputs', 'emissions_running', 'transport_running',
      'processing_outputs', 'publishing'
  )
RETURNING id, status, cancellation_requested_at;
