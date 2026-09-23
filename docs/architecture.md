# Architecture

The platform is a single-server, containerized weather-raster system. PostgreSQL
is authoritative for identity and state; local files hold the large immutable
payloads.

## Runtime topology

```text
                             ECCC Datamart
                                   |
                  AMQPS delivery + inventory reconciliation
                                   |
                                   v
                           Airflow LocalExecutor
                  register -> download -> validate -> COG
                          |                       |
                          v                       v
                    PostgreSQL/PostGIS      bind-mounted weather data
                          ^                       ^
                          |                       |
                +---------+---------+             |
                |                   |             |
          weather-api          restricted tile-api
                |                   |
                |              Nginx tile cache
                +---------+---------+
                          |
                         Caddy
                          |
                  React + MapLibre client
```

Airflow metadata lives in `weather_airflow`; application catalogue and ingestion
state live in `weather_app`. The scheduler runs task subprocesses through
`LocalExecutor`, with four global task slots, a four-slot ECCC download pool, and
a four-slot COG transformation pool.

## Data identity

A source object is identified by provider, product, domain, reference time,
forecast offset or analysis interval, and filename. A processed raster asset is
identified by product run, product time, configured field, level, and role.
Natural uniqueness constraints and deterministic paths make task retries
idempotent.

Forecast products store both initialization and valid time. Analysis products
use the analysis valid/end time, a null forecast hour, and explicit accumulation
interval bounds. The web client therefore never has to infer whether a timestamp
is a forecast lead or an analysis period.

## Storage lifecycle

```text
raw/*.part -> raw source -> staging/*.tmp -> validated processed COG
                                               |
                                               v
                                     catalogue.asset available
```

Downloads and transforms publish with atomic filesystem replacement. The
catalogue exposes only assets in `available` state. Source bytes, raster arrays,
directory listings, and COG metadata do not pass through Airflow XCom; mapped
tasks exchange database IDs and small summaries.

## Serving boundary

The weather API resolves a catalogue selection to an asset and signs a payload
containing the asset ID, style ID, source checksum, colour range, image format,
and expiry. The tile API verifies that signature, resolves the registered row
again, confines its relative path below `WEATHER_DATA_ROOT`, and renders one
PNG/WebP tile. It exposes no general `url=`, file, or expression parameter.

Point sampling uses the same registered COG identity and returns canonical units.
Redis caches short-lived sample responses and rate-limit counters. Signed layer
tokens are deterministic within an expiry bucket, so the reverse-proxy tile
cache can safely retain immutable tile responses.

## Trust and network boundary

Only Caddy's HTTP/HTTPS ports are intended for public exposure. The development
PostgreSQL port is loopback-only; Redis and the tile/API upstream ports remain on
the Compose network. Airflow and Grafana bind to loopback and require their own
credentials. Runtime database roles cannot migrate schemas, and the tile role
cannot write catalogue state.

## Scaling path

The filesystem storage adapter, semantic paths, SQL catalogue, signed tile
identity, and stateless serving APIs keep a future migration possible:

- local storage to S3-compatible object storage;
- LocalExecutor to isolated distributed workers;
- one tile renderer to horizontally scaled replicas behind a CDN;
- selected COGs plus optional Zarr cubes for analytical workloads.

Those changes are intentionally outside the first single-server deployment.
