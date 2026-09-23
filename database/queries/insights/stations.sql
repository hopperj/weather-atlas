-- Geographic filtering happens before bounded observation lookups. Wrapped bounds are supported.
WITH candidates AS MATERIALIZED (
    SELECT s.*, CASE WHEN %(longitude)s::float8 IS NOT NULL THEN
        ST_Distance(s.location, ST_SetSRID(ST_MakePoint(%(longitude)s, %(latitude)s), 4326)::geography)
        / 1000 END AS distance_km
    FROM catalogue.weather_station s
    WHERE (%(id)s::text IS NULL OR s.id = %(id)s)
      AND (%(longitude)s::float8 IS NULL OR ST_DWithin(s.location,
        ST_SetSRID(ST_MakePoint(%(longitude)s, %(latitude)s), 4326)::geography, %(radius)s * 1000))
      AND (%(west)s::float8 IS NULL OR (
        CASE WHEN %(west)s <= %(east)s THEN
            s.location::geometry && ST_MakeEnvelope(%(west)s, %(south)s, %(east)s, %(north)s, 4326)
        ELSE s.location::geometry && ST_MakeEnvelope(%(west)s, %(south)s, 180, %(north)s, 4326)
          OR s.location::geometry && ST_MakeEnvelope(-180, %(south)s, %(east)s, %(north)s, 4326) END
        AND
        ST_Y(s.location::geometry) BETWEEN %(south)s AND %(north)s AND
        CASE WHEN %(west)s <= %(east)s THEN ST_X(s.location::geometry) BETWEEN %(west)s AND %(east)s
        ELSE ST_X(s.location::geometry) >= %(west)s OR ST_X(s.location::geometry) <= %(east)s END))
    ORDER BY distance_km NULLS LAST, s.id LIMIT 2000
)
SELECT s.id, s.metadata, s.distance_km, o.payload,
    (o.payload->>'expiresAt')::timestamptz <= %(now)s AS stale
FROM candidates s
JOIN LATERAL (
    SELECT payload FROM catalogue.weather_observation o
    WHERE o.station_id = s.id AND o.observed_at <= %(now)s + INTERVAL '5 minutes'
    ORDER BY observed_at DESC, correction DESC, received_at DESC LIMIT 1
) o ON true
ORDER BY stale, (o.payload->'values'->>%(field)s) IS NULL, s.distance_km NULLS LAST, s.id
LIMIT %(limit)s OFFSET %(offset)s;
