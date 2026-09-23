WITH linked_run AS (
    UPDATE simulation.run
    SET product_run_id = %(product_run_id)s,
        output_manifest_path = %(output_manifest_path)s
    WHERE id = %(run_id)s
    RETURNING id, product_run_id, output_manifest_path
)
UPDATE catalogue.product_run
SET simulation_run_id = linked_run.id,
    updated_at = clock_timestamp()
FROM linked_run
WHERE catalogue.product_run.id = linked_run.product_run_id
RETURNING linked_run.id, linked_run.product_run_id, linked_run.output_manifest_path;
