SELECT DISTINCT ON (observed_at) observed_at, payload
FROM catalogue.weather_observation
WHERE station_id = %(id)s AND observed_at >= %(start)s AND observed_at <= %(end)s
ORDER BY observed_at, correction DESC, received_at DESC LIMIT 3000;
