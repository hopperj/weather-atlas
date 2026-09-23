-- Parameters: product_code, keep_product_run_id
WITH keep_run AS (
    SELECT product_run.product_id, product_run.run_time
    FROM catalogue.product_run
    JOIN catalogue.product ON product.id = product_run.product_id
    WHERE product_run.id = %(keep_product_run_id)s
      AND product.code = %(product_code)s
), updated AS (
    UPDATE catalogue.product_run AS product_run
    SET source_status = 'expired',
        processing_status = 'expired',
        is_visible = false,
        completed_at = COALESCE(product_run.completed_at, clock_timestamp()),
        updated_at = clock_timestamp()
    FROM keep_run
    WHERE product_run.product_id = keep_run.product_id
      AND product_run.run_time < keep_run.run_time
      AND (
          product_run.source_status <> 'expired'
          OR product_run.processing_status <> 'expired'
          OR product_run.is_visible
      )
    RETURNING product_run.id, product_run.run_time
), recorded AS (
    INSERT INTO audit.event (event_type, object_type, object_key, details)
    SELECT
        'maintenance.product_run_superseded',
        'catalogue.product_run',
        updated.id::text,
        jsonb_build_object('run_time', updated.run_time)
    FROM updated
)
SELECT count(*)::integer AS expired_count
FROM updated;
