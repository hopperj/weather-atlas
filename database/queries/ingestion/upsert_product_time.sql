-- Parameters:
--   product_run_id, valid_time, forecast_hour, interval_start, interval_end,
--   time_kind
INSERT INTO catalogue.product_time (
    product_run_id,
    valid_time,
    forecast_hour,
    interval_start,
    interval_end,
    time_kind
)
VALUES (
    %(product_run_id)s,
    %(valid_time)s,
    %(forecast_hour)s,
    %(interval_start)s,
    %(interval_end)s,
    %(time_kind)s
)
ON CONFLICT (
    product_run_id,
    valid_time,
    forecast_hour,
    interval_start,
    interval_end,
    time_kind
) DO UPDATE SET valid_time = EXCLUDED.valid_time
RETURNING id, product_run_id, valid_time, forecast_hour, interval_start, interval_end, time_kind;
