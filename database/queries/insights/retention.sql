-- Retain latest revisions even if a station/feed has stopped, so stale data remains explicit.
WITH old_forecasts AS (
    SELECT area_id, source, version FROM catalogue.forecast_revision r
    WHERE issued_at < %(cutoff)s AND EXISTS (
        SELECT 1 FROM catalogue.forecast_revision n
        WHERE n.area_id = r.area_id AND n.source = r.source AND n.issued_at > r.issued_at
    ) ORDER BY issued_at LIMIT 5000
), removed_forecasts AS (
    DELETE FROM catalogue.forecast_revision r USING old_forecasts o
    WHERE r.area_id = o.area_id AND r.source = o.source AND r.version = o.version RETURNING 1
), old_observations AS (
    SELECT station_id, observed_at, report_type, version FROM catalogue.weather_observation r
    WHERE observed_at < %(cutoff)s AND EXISTS (
        SELECT 1 FROM catalogue.weather_observation n
        WHERE n.station_id = r.station_id AND n.observed_at > r.observed_at
    ) ORDER BY observed_at LIMIT 5000
), removed_observations AS (
    DELETE FROM catalogue.weather_observation r USING old_observations o
    WHERE r.station_id = o.station_id AND r.observed_at = o.observed_at
      AND r.report_type = o.report_type AND r.version = o.version RETURNING 1
)
SELECT (SELECT count(*) FROM removed_forecasts) AS forecasts,
       (SELECT count(*) FROM removed_observations) AS observations;
