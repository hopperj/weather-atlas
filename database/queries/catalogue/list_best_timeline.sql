-- Parameters: product_code text, domain_code text, field_code text,
-- start_time timestamptz nullable, end_time timestamptz nullable, limit integer
--
-- A valid time can be present in several forecast cycles. Select the frame with
-- the shortest non-negative forecast lead; a newer run wins any remaining tie.
-- Analysis products have no forecast lead, so their newest revision wins.
WITH available_frames AS MATERIALIZED (
    SELECT
        product_run.run_time,
        product_time.valid_time,
        product_time.forecast_hour,
        product_time.interval_start,
        product_time.interval_end,
        product_time.time_kind,
        ROW_NUMBER() OVER (
            PARTITION BY product_time.valid_time
            ORDER BY
                product_time.forecast_hour ASC NULLS FIRST,
                product_run.run_time DESC,
                product_time.id DESC
        ) AS preference
    FROM catalogue.product_time
    JOIN catalogue.product_run
        ON product_run.id = product_time.product_run_id
    JOIN catalogue.product
        ON product.id = product_run.product_id
    JOIN catalogue.domain
        ON domain.id = product_run.domain_id
    WHERE product.code = %(product_code)s
      AND domain.code = %(domain_code)s
      AND product.enabled
      AND product_run.is_visible
      AND EXISTS (
          SELECT 1
          FROM catalogue.asset
          JOIN catalogue.product_field
              ON product_field.id = asset.product_field_id
          JOIN catalogue.variable
              ON variable.id = product_field.variable_id
          JOIN catalogue.vertical_level
              ON vertical_level.id = product_field.vertical_level_id
          WHERE asset.product_time_id = product_time.id
            AND asset.status = 'available'
            AND asset.asset_role IN ('processed_cog', 'derived_cog')
            AND COALESCE(
                product_field.metadata ->> 'field_code',
                variable.code || '_' || vertical_level.code
            ) = %(field_code)s
      )
),
best_frames AS MATERIALIZED (
    SELECT
        run_time,
        valid_time,
        forecast_hour,
        interval_start,
        interval_end,
        time_kind
    FROM available_frames
    WHERE preference = 1
),
selected_bounds AS (
    SELECT
        COALESCE(
            %(start_time)s::timestamptz,
            MAX(valid_time) FILTER (WHERE valid_time <= clock_timestamp()),
            MIN(valid_time)
        ) AS start_time,
        %(end_time)s::timestamptz AS requested_end_time,
        MAX(valid_time) AS latest_time
    FROM best_frames
),
effective_bounds AS (
    SELECT
        start_time,
        COALESCE(
            requested_end_time,
            LEAST(start_time + INTERVAL '24 hours', latest_time)
        ) AS end_time
    FROM selected_bounds
)
SELECT
    best_frames.run_time,
    best_frames.valid_time,
    best_frames.forecast_hour,
    best_frames.interval_start,
    best_frames.interval_end,
    best_frames.time_kind
FROM best_frames
CROSS JOIN effective_bounds
WHERE best_frames.valid_time >= effective_bounds.start_time
  AND best_frames.valid_time <= effective_bounds.end_time
ORDER BY best_frames.valid_time
LIMIT %(limit)s;
