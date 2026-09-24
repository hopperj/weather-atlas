# Weather and tile APIs

The public JSON API is served below `/api/v1`. Timestamps are timezone-aware ISO
8601 values and response keys use camel case. Stable product/domain/field codes
are preferred over internal numeric IDs.

Interactive OpenAPI documentation is available at `/docs` on the weather API.

## Catalogue

```text
GET /api/v1/products
GET /api/v1/variables
GET /api/v1/products/{product}/domains
GET /api/v1/products/{product}/fields?run={timestamp}
GET /api/v1/products/{product}/runs?field={field}&limit=40&before={timestamp}
GET /api/v1/products/{product}/runs/{run_time}/times?field={field}
GET /api/v1/products/{product}/timeline?domain={domain}&field={field}&start={timestamp}&end={timestamp}
GET /api/v1/status/ingestion
```

The product catalogue includes enabled products even before their first ingest,
with `latestRunTime: null`. The variable catalogue lists displayable fields
independently and includes the product codes that currently provide each one.
Runs and times require available processed assets; `field` filters run history
to cycles and timeline frames that contain the selected variable. Fields are
filtered to the selected run whenever the `run` query parameter is present. An
analysis time has `forecastHour: null` and includes `intervalStart`,
`intervalEnd`, and its `timeKind`. Run history is ordered newest first. When
another page exists, `nextCursor` contains the timestamp to pass as `before`;
otherwise it is null.

The cross-run timeline returns one frame per valid time. When the same valid
time exists in several model runs, it chooses the smallest forecast hour—the
newest prediction made before that valid time—and uses the newest run as a
tie-breaker. Analysis revisions have no forecast hour, so their newest available
revision wins. Each frame includes both `runTime` and `validTime`.

Omit both `start` and `end` for the default window: the closest available valid
time at or before now through 24 hours later, capped at the latest available
time. Supply both UTC timestamps for a historical or custom window. `limit`
defaults to 1,000 and is capped at 2,000; `truncated` reports when more frames
exist than the requested limit.

## Official regional forecast labels

```text
GET /api/v1/city-forecasts
GET /api/v1/city-forecasts?valid_time={timestamp}
GET /api/v1/city-forecasts?valid_time={timestamp}&province=NS
```

This endpoint serves the latest normalized ECCC City Page Weather snapshot as a
GeoJSON FeatureCollection. Each point is one province/official-region pair and
contains the forecast period, high or low temperature in Celsius, relative
humidity, probability of precipitation, explicitly issued precipitation
amount, condition, issue time, and validity interval. Without `valid_time`, the
server selects the current UTC instant. `province` is an optional two-letter
uppercase code.

The response also reports the common available start/end and visible feature
count. It is ETagged and revalidates every five minutes. A site without an
active forecast bulletin is not returned.

## Combined daily and hourly forecast page

```text
GET /api/v1/forecast/regions
GET /api/v1/forecast/hourly?area_id={16-character-hex-region-id}
GET /api/v1/forecast/nearest?latitude={latitude}&longitude={longitude}
GET /api/v1/observations/nearby?latitude={latitude}&longitude={longitude}&radius=100
```

The regions endpoint returns all collected Canadian locations, including
`province` (two-letter code), `provinceName`, and each region's remaining
day/night periods within seven days, with issue time and a stale flag. Nova
Scotia regions sort first, followed by province/territory name and region name.
It keeps
locations selectable after their bulletin expires but omits expired periods.
The hourly endpoint returns exactly 72 UTC slots starting at the current hour,
sampled from GDPS at the selected Canadian region's representative coordinate. Temperature,
humidity, one-hour precipitation, wind and gusts are numeric or null. Every row
includes its model run and completeness status; wind is converted to km/h.
Missing hours remain in the result. See the
[forecast page guide](forecast-page-2026-09-06.md) for source and interval semantics.
The nearest-region endpoint supports the page's opt-in browser-location action.
The nearby-observations endpoint supplies current station temperature, humidity,
wind/gust, pressure, precipitation, observation time, distance, freshness, and
attribution; the page degrades to supported hourly model fields if it is unavailable.

## Resolve a layer

```text
GET /api/v1/layers/resolve
```

Required query values are `product`, `domain`, `run`, `field`, and `valid_time`.
`style` defaults to `default`; `format` is `webp` or `png`. Optional `minimum`
and `maximum` values customize the signed display range and must be supplied
together as a finite, increasing pair. Optional `opacity_cutoff` is a finite
value in the field's canonical unit; pixels below it are fully transparent.
The cutoff is signed into the layer token, so different cutoff values have
independent immutable tile-cache identities.

The response includes semantic metadata, bounds, a legend, and a tokenized tile
template such as:

```json
{
  "product": "hrdps",
  "domain": "continental",
  "runTime": "2026-07-16T12:00:00Z",
  "validTime": "2026-07-16T18:00:00Z",
  "forecastHour": 6,
  "field": "air_temperature_2m",
  "unit": "degC",
  "tileUrl": "/tiles/v1/<signed-token>/{z}/{x}/{y}.webp",
  "bounds": [-141.0, 39.0, -42.0, 84.0],
  "legend": {"minimum": -40.0, "maximum": 40.0, "palette": []}
}
```

The response never exposes a filesystem path. Invalid or expired tokens return a
generic 404 from the tile service.

## Point sample

```text
GET /api/v1/sample
```

Supply `product`, `domain`, `run`, `valid_time`, `longitude`, `latitude`, and one
to ten repeated `field` values. The endpoint reads all selected registered COGs
concurrently and returns canonical values and nodata flags in one response.

Sample results are cached briefly in Redis. A per-client fixed-window limit is
applied; a rejected request returns HTTP 429 and `Retry-After: 60`. Redis failure
does not make raster data unavailable, but `/health/ready` reports Redis as a
required dependency so an operator sees the degraded state.

## Tile route and caching

```text
GET /tiles/v1/{layer_token}/{z}/{x}/{y}.webp
GET /tiles/v1/{layer_token}/{z}/{x}/{y}.png
```

The token permits one registered asset/style/checksum/range/format combination.
Successful responses carry an ETag and `Cache-Control: public, immutable` up to
the token expiry. Nginx supplies a bounded 20 GB disk cache in front of the tile
service and uses short negative caching for 404 responses.

## Health

```text
GET /health/live
GET /health/ready
```

These public reverse-proxy routes report weather API health. Weather API
readiness checks PostgreSQL, Redis, and the data directory. The tile API has
separate `/health/live` and `/health/ready` routes on its Compose-network
endpoint; its readiness checks PostgreSQL and the data directory. Neither
readiness probe depends on current ECCC availability.

## Metrics

Prometheus scrapes separate internal endpoints over the Compose network:

```text
http://weather-api:8000/metrics
http://tile-api:8000/metrics
```

Caddy intentionally does not expose `/metrics` publicly. Use Prometheus or an
authenticated operator connection to inspect metrics rather than adding the
upstream services to the public reverse-proxy routes.
