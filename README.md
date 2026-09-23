# ECCC Weather Model Map Platform

A self-hosted platform that turns selected Environment and Climate Change Canada
(ECCC) model data into time-enabled layers on an interactive web map.

The implemented data path is:

```text
ECCC MSC Datamart
  -> bounded Airflow ingestion
  -> raw GRIB2 on local storage
  -> ecCodes validation and GDAL COG conversion
  -> PostgreSQL/PostGIS catalogue
  -> signed raster tiles, point samples, and wind-vector grids
  -> React + MapLibre timeline map
```

PostgreSQL is the system of record for catalogue and ingestion state. Raster
payloads stay on the filesystem as raw source files and Cloud-Optimized
GeoTIFFs. Application SQL is handwritten, stored under `database/`, and applied
manually; the project has no ORM.

The reviewed design is in [docs/implementation-plan.md](docs/implementation-plan.md).
Ingestion and production operations are covered by
[docs/ingestion.md](docs/ingestion.md) and
[docs/operations.md](docs/operations.md).
The acceptance-gated wildfire workflow is documented in the
[smoke implementation report](docs/smoke-pipeline-implementation-report.md).
Its external scientific validation is governed by the frozen
[validation protocol](docs/smoke-validation-protocol.md), with actions and
results preserved in the [research log](docs/smoke-validation-log.md).

## What is implemented

- A native SwiftUI iPhone app in [weatheratlas-ios](../weatheratlas-ios/README.md),
  with server-backed model maps, daily/hourly forecasts, saved places, wind arrows,
  hotspots and collected radar/satellite playback. See the
  [server imagery activation guide](docs/imagery-and-ios.md) for its ETL and
  PostgreSQL migration requirements.

- Server-prepared forecast changes, nearby ECCC station observations, and iPhone
  Home/Lock Screen widgets. The initial observation/model rollout is Atlantic
  Canada; collection, history, quality checks, and comparisons stay on the server.
  See [implementation and operations](docs/forecast-insights-implementation.md)
  for coverage, migrations, schedules, tests, and the remaining device widget checks.

- A dedicated `/forecast` page with Canada-wide regional seven-day outlooks and
  a 72-hour GDPS table for temperature, humidity, precipitation, wind and gusts.
  Nova Scotia regions are directly selectable; other locations use province/
  territory and region selectors.
  Open **Daily & hourly forecast** in the map header. Sources, gap handling and
  rollout are documented in [the forecast page guide](docs/forecast-page-2026-09-06.md).
- One-server Docker Compose deployment with Caddy, PostgreSQL/PostGIS, Redis,
  Airflow 3 `LocalExecutor`, FastAPI services, React, MapLibre, and an Nginx tile
  cache.
- Least-privilege PostgreSQL roles and numbered, checksum-verified SQL
  migrations that are never applied at application startup.
- Configuration-driven ECCC adapters for HRDPS, RAQDPS, RDPS, and GDPS, plus
  analysis-aware inventory adapters for HRDPA, RDPA, and HREPA.
- Live-inventory CLI with strict filename/timing/grid parsing, storage estimates,
  explicit unknown-field reporting, and offline fixtures.
- Bounded, dynamically mapped Airflow forecast DAGs that stream source files,
  validate GRIB envelopes and ecCodes timing/grid metadata, generate validated
  COGs atomically, and idempotently register assets.
- Catalogue, timeline, layer-resolution, ingestion-status, readiness,
  multi-field point-sampling, and viewport-bounded wind-vector APIs backed by
  reviewed `.sql` files.
- Restricted raster tile service. Public requests can render only
  catalogue-registered assets through signed, expiring layer tokens; arbitrary
  URLs, paths, and raster expressions are not accepted.
- Responsive map UI with variable-first selection, compatible data-product
  filtering, selectable UTC animation windows, shortest-lead forecast selection
  across retained model runs, up to three overlays, opacity and visibility
  controls, per-layer low-value transparency cutoffs, dynamic legends,
  animation, adjacent-frame prefetch, cross-fades, click-to-sample values, and
  speed-coloured 10 m wind arrows with responsive density.
- A feature-gated CWFIS → CFFEPS 4.1 → FLEXPART 11.1 wildfire workflow with
  deterministic fire events, archived GFS inputs, primary PM2.5/CO/BC,
  vertical injection and deposition fields, immutable run provenance, and a
  bounded map-based run builder.
- Redis response caching and point-sample rate limiting, JSON request logs,
  Prometheus metrics, a provisioned Grafana dashboard, optional automatic TLS,
  disk-backed tile caching, low-disk admission checks, backup tooling, storage
  integrity reporting, historical weather-data retention, dry-run-first Airflow
  integrity/temporary-file DAGs, and a systemd unit example.

All configured HRDPS, RDPS, and GDPS forecast fields are enabled, along with
RAQDPS PM2.5, PM10, ozone, nitrogen dioxide, and sulfur dioxide and the
configured HRDPA/RDPA/HREPA precipitation analyses. Live archive inventories
must remain part of any future field activation because the source catalogue is
larger than this deliberately bounded configuration.

## ECCC retrieval boundary

The AMQPS service is the primary systematic real-time retrieval path:

- `weather-ingest inspect-source` is an operator-run inventory command;
- Sarracenia subscribes to AMQPS, rejects unmatched model messages, and writes
  only enabled fields to a persistent local inbox;
- generated ingestion DAGs run hourly at minute 15 with no parameters;
- each DAG reconciles every candidate cycle in its retry window against the
  immutable Datamart archive, covering subscriber downtime and queues created
  after publication;
- every completed cycle remains visible and its registered raw and processed
  payloads are retained as an append-only historical archive.

Completed slots are skipped, while all new data follows one registered-object
validation and ETL pipeline. The run selector loads history in bounded pages,
so an older cycle can be selected without an unbounded initial API response.

## Prerequisites

- Docker Engine or Docker Desktop with Docker Compose v2
- Bash, `make`, OpenSSL, `awk`, and either `sha256sum` or `shasum`
- `jq` for optional JSON diagnostics
- [`uv`](https://docs.astral.sh/uv/) for host-side Python checks
- Node.js 24 and npm 11 for host-side frontend checks

Allow at least 6 GB of Docker memory for the full development stack. Weather
archives need substantially more disk; run the capacity check before enabling a
product or backfill. Host-side `weather-ingest check-tools` additionally requires
ecCodes (`grib_ls`) and GDAL (`gdal_translate`, `gdalinfo`, and `gdal_calc.py`).
Those geospatial tools are already installed in the project Airflow image and
are not host prerequisites for a Compose-only deployment.

The project builds its own PostgreSQL 18/PostGIS 3.6 image from the official
multi-architecture PostgreSQL Alpine image, so the same Compose configuration
runs natively on both AMD64 Linux and ARM64 hosts.

## Quick start

The zero-argument installer generates secrets for a new deployment, prepares
storage, pulls dependencies, and builds every application image. The runner
starts all required containers plus Prometheus and Grafana, applies and verifies
the handwritten SQL migrations, waits for health checks, and prints every local
endpoint:

```bash
./install.sh
./run.sh
```

Both scripts are idempotent and reject arguments. `run.sh` always performs the
installer's lightweight prerequisite, configuration, secret, storage, and disk
checks before building and starting Compose, so it can be used on its own. It
preserves existing credentials when the PostgreSQL data directory already
exists; secret rotation must be coordinated separately so persisted database
and Airflow credentials remain usable. Equivalent Make targets are available
as `make install` and `make run`.

A slow first image pull or startup can use a larger wait timeout through the
environment without changing the zero-argument command:

```bash
COMPOSE_WAIT_TIMEOUT=900 ./run.sh
```

`run.sh` explicitly invokes the manual migration runner; the application
containers never apply migrations at startup. Re-running the script is a
supported no-op for applied migrations and reports them as `unchanged`.

For development workflows where services or migrations need to be controlled
individually, the original commands remain available:

```bash
cp .env.example .env
make dev-up
make db-create
make db-verify
make test
make airflow-test
```

Never use the example `change-me` secrets outside an isolated development
machine. Generate the layer-token, Airflow JWT, and Grafana credentials before a
production start. Use URL-safe hexadecimal database passwords because Compose
embeds them in connection URLs. The app and API are HTTPS-only, with automatically
renewed Let's Encrypt certificates. Set `CADDY_SITE_ADDRESS` to one public DNS
hostname (no scheme or port) and route public TCP ports 80/443 to the gateway's
redirect/HTTPS ports. HTTP, including local/LAN addresses, only redirects to that
canonical HTTPS hostname. See [HTTPS deployment and verification](docs/https.md).

## Persistent data

All mutable container data is bind-mounted below
`WEATHERAPP_DATA_DIR` (default `./weatherapp_data`). Stopping, recreating, or
upgrading a container therefore does not discard its data. The installer creates
the complete tree, and Compose runs a short `storage-init` service before
PostgreSQL or Redis to enforce the ownership required by the pinned images.

| Host subdirectory | Persistent contents |
|---|---|
| `postgres/` | PostgreSQL/PostGIS cluster |
| `redis/` | Redis append-only data |
| `weather/` | Raw, staging, processed, derived, quarantine, cache, and temporary weather files |
| `airflow/logs/` | Airflow task logs |
| `caddy/data/`, `caddy/config/` | Caddy certificates, state, and configuration data |
| `tile-cache/` | Nginx raster tile cache |
| `prometheus/` | Prometheus time-series data |
| `grafana/` | Grafana database and runtime state |
| `backups/postgres/` | Default host destination for PostgreSQL backups |

`WEATHER_DATA_DIR` defaults to `./weatherapp_data/weather` and must remain
inside `WEATHERAPP_DATA_DIR`. Both relative paths are resolved from the project
root. Place `WEATHERAPP_DATA_DIR` on the intended data filesystem before the
first start; changing it later selects a different, initially empty deployment.

Older releases used Docker named volumes and `./data`. This configuration does
not delete or automatically import those stores. Back up and explicitly migrate
any existing data before switching an established deployment.

## Endpoints

| Component | Address |
|---|---|
| Map application | <https://weatheratlas.ioresearch.ca/> |
| Weather API liveness | <https://weatheratlas.ioresearch.ca/health/live> |
| Weather API readiness | <https://weatheratlas.ioresearch.ca/health/ready> |
| Weather API documentation | <https://weatheratlas.ioresearch.ca/docs> |
| Airflow UI | <http://localhost:8081/> |
| Prometheus, optional | <http://localhost:9090/> |
| Grafana, optional | <http://localhost:3000/> |

These are the `.env.example` defaults. If another local service already owns a
port, change `APP_PORT`, `HTTPS_PORT`, `AIRFLOW_PORT`,
`POSTGRES_HOST_PORT`, `PROMETHEUS_PORT`, or `GRAFANA_PORT` in `.env` before
starting. `run.sh` prints the effective browser endpoints after a successful
start.

The web gateway binds to `APP_BIND_ADDRESS=0.0.0.0`. Use
`https://weatheratlas.ioresearch.ca/forecast` on both LAN and external devices;
`0.0.0.0` is a listen address, not a browser destination. HTTP links no longer
serve app data. LAN clients need working NAT loopback or equivalent local routing
for the HTTPS hostname. Administrative and database ports remain loopback-only.
See [local-network setup](docs/operations.md#local-network-access).

Start the optional monitoring profile with:

```bash
make observability-up
```

PostgreSQL, Redis, the tile API, and the upstream application services are not
publicly exposed by the reverse proxy. The development PostgreSQL port defaults
to a loopback-only `127.0.0.1:5433` binding.

## Database migrations

Apply every pending migration:

```bash
make db-create
```

Apply one reviewed migration interactively:

```bash
./scripts/apply_migration.sh database/migrations/0008_catalogue_configured_weather_fields.sql
```

The runner displays the target identity and SHA-256, requires confirmation,
executes with `ON_ERROR_STOP`, and refuses a previously applied filename whose
contents have changed. Never edit an applied migration; add another numbered SQL
file. See [database/README.md](database/README.md).

The PostgreSQL server contains separate databases:

- `weather_app`, changed only by the manual application migrations;
- `weather_airflow`, owned and migrated by Airflow.

Runtime services use separate `weather_api`, `weather_tiles`, and
`weather_ingest` roles instead of migration credentials.

## Inspect and ingest a model run

Validate all seven product configurations:

```bash
uv run weather-ingest --config-root config validate-config
```

When developing or processing rasters directly on the host, also validate the
optional host geospatial toolchain:

```bash
uv run weather-ingest --config-root config check-tools
```

Create an ad hoc metadata inventory without downloading model payloads:

```bash
uv run weather-ingest --config-root config inspect-source \
  --product hrdps \
  --run 2026-07-16T12:00:00Z \
  --format json \
  --summary-only
```

Trigger one product's parameterless discovery and ETL workflow:

```bash
./scripts/trigger_ingestion.sh hrdps
```

Run every data-collection DAG immediately:

```bash
./scripts/run_all_data_collection_dags.sh
```

This includes the server-collected radar and satellite imagery job. For its
six-minute schedule, coverage and deployment requirements, see
[collected imagery](docs/imagery-and-ios.md).

Collect the latest complete NOAA GFS pressure-grid cycle for FLEXPART:

```bash
./scripts/trigger_gfs_ingestion.sh
```

`noaa_gfs_ingest` runs every six hours after the 00Z, 06Z, 12Z, and 18Z GFS
cycles. See [docs/ingestion.md](docs/ingestion.md#noaa-gfs-collection-for-flexpart)
for storage layout, validation, schedule rationale, and configuration.

Collect and normalize the latest finalized NRCan CWFIS Fire M3 VIIRS hotspot
data as map-ready GeoJSON:

```bash
./scripts/trigger_hotspot_ingestion.sh
```

`nrcan_cwfis_hotspots_ingest` runs daily at 07:15 UTC. See
[docs/ingestion.md](docs/ingestion.md#nrcan-cwfis-wildfire-hotspots) for the
source choice, limitations, storage layout, and schedule rationale.

Each DAG reconciles registered-but-incomplete sources before discovering recent
provider inventory, skips COGs already available in the catalogue, downloads or
stages only missing GRIB2/NetCDF objects, and publishes them through the ETL
pipeline. It checks every candidate cycle in the configured retry window,
restores recoverable rows left by the retired latest-only policy, and retains
every completed cycle. No Airflow trigger parameters are required. The commands
wait for completion and report failures through their exit status. See
[docs/ingestion.md](docs/ingestion.md) for discovery and idempotency details.
The configured pools initially permit four ECCC downloads and four COG
transformations at once, two concurrent NOAA GFS downloads, and one NRCan CWFIS
download.

Do not enable every listed model field. A single HRDPS run contains tens of
gigabytes across all fields; configuration, inventory estimates, retention, and
the capacity admission check exist to keep the server within its storage budget.

## Development and verification

```bash
make deps
make lint
make test
make airflow-test
docker compose config --quiet
docker compose --profile observability config --quiet
```

`make test` runs Python tests, frontend tests, and the production frontend build.
Database integration tests use a disposable or running PostGIS database when
`WEATHER_TEST_DATABASE_URL` is set. Python dependencies are locked in `uv.lock`;
frontend dependencies are locked in `frontend/package-lock.json`.

Useful runtime commands:

```bash
make ps
make dev-logs
docker compose logs --follow --tail=200 airflow-scheduler
docker compose logs --follow --tail=200 weather-api
make dev-restart
make dev-down
```

`make dev-down` preserves every bind-mounted store under `weatherapp_data/`.
Compose's `--volumes` option does not delete bind-mounted data; removing that
host directory is the destructive operation.

## Operations

Check capacity before a download or backfill:

```bash
./scripts/check_disk_capacity.sh --required-gib 45
```

Create verified, owner-only PostgreSQL backups:

```bash
./scripts/backup_postgres.sh
```

Run the read-only retention and integrity report:

```bash
./scripts/report_storage_maintenance.sh \
  --check-catalogue \
  --fail-on-integrity
```

Backups must be replicated off-host and restore-tested. Review
[docs/operations.md](docs/operations.md) before production deployment; it covers
safe retention ordering, checksum audits, systemd startup, secret handling, and
the restore drill.

## Deliberate limitations

- Automated discovery covers only fields whose download and processing flags
  are enabled. The Sarracenia subscriber does not mirror complete model trees.
- Most high-volume atmospheric fields are configured but disabled by default;
  enable them only after a live inventory and capacity review.
- HREPA is distributed as multi-member NetCDF and requires a dedicated,
  semantics-aware extraction path rather than the GRIB-to-COG forecast path.
- User accounts, saved views, browser-based run comparison, particle wind animation, and
  pressure-contour vector tiles are post-MVP features.
- The default OpenFreeMap vector basemap is an external geography service.
  Keep its attribution visible and review service availability for public traffic;
  self-hosted geography can be configured independently of the weather server.
  See [map readability and basemap configuration](docs/map-readability.md).
