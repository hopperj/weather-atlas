# ECCC Weather Model Map Platform

## Reviewed implementation plan

**Status:** Implemented platform foundation; deployment acceptance remains operator-run  
**Audience:** Project owner, Codex, and future maintainers  
**Deployment target:** One self-hosted Linux server  
**Last reviewed:** 2026-07-17

## 1. Executive summary

Build a self-hosted web application that ingests selected Environment and Climate
Change Canada (ECCC) numerical weather products, converts map-ready fields to
Cloud-Optimized GeoTIFFs (COGs), catalogues them in PostgreSQL/PostGIS, and serves
them as animated raster layers in a MapLibre web client.

The core data path is:

```text
ECCC MSC Datamart (GRIB2/NetCDF)
          |
          v
AMQPS delivery plus missing-slot inventory reconciliation
          |
          v
Bounded Airflow ingestion
          |
          +--> raw GRIB2 on local storage
          |
          v
ecCodes/GDAL validation and transformation
          |
          +--> map-ready COGs on local storage
          |
          +--> catalogue and ingest state in PostgreSQL/PostGIS
          |
          v
Weather API + restricted raster tile API
          |
          v
React + TypeScript + MapLibre web application
```

The architecture is sound for a single server, with these non-negotiable
constraints:

- PostgreSQL is the authoritative catalogue and application database, not the
  primary raster store.
- Application schema changes are handwritten `.sql` files applied manually.
- Application code uses `psycopg` and SQL files; no ORM is permitted.
- Raw GRIB2 and processed COG data live on the host filesystem initially.
- Airflow uses `LocalExecutor`; Kubernetes, Celery, and MinIO are out of scope.
- Public tile routes can only render catalogue-registered assets. They must never
  accept an arbitrary URL or filesystem path.
- The first complete vertical slice is HRDPS 2 m air temperature.

## 2. Review findings and revisions

The supplied plan has a good overall architecture. The following revisions make
it safer and more directly executable.

### 2.1 Treat the live ECCC inventory as discoverable data

ECCC changes operational systems, filenames, grids, and directory layouts. The
implementation must not assume the earlier model inventory or example URLs are
permanent. Each source adapter must be based on current official documentation
and verified against a live run before its ingestion DAG is enabled.

The MSC Datamart is an HTTPS raw-data service with a date-based directory tree and
a `/today` alias. ECCC currently documents a roughly 30-day server retention
window. AMQPS remains the primary real-time discovery and transfer path.
Sarracenia consumes it into a persistent local inbox. Parameterless operational
DAGs run hourly at minute 15 and reconcile only catalogue slots that are still
missing against recent immutable archive listings. This bounded reconciliation
covers subscriber downtime and queues created after publication without
re-listing completed slots.

Official references:

- [MSC Datamart](https://eccc-msc.github.io/open-data/msc-datamart/readme_en/)
- [MSC Open Data usage overview](https://eccc-msc.github.io/open-data/usage/readme_en/)
- [HRDPS documentation](https://eccc-msc.github.io/open-data/msc-data/nwp_hrdps/readme_hrdps_en/)
- [GDPS documentation](https://eccc-msc.github.io/open-data/msc-data/nwp_gdps/readme_gdps_en/)
- [RAQDPS documentation](https://eccc-msc.github.io/open-data/msc-data/nwp_raqdps/readme_raqdps_en/)
- [RAQDPS Datamart layout](https://eccc-msc.github.io/open-data/msc-data/nwp_raqdps/readme_raqdps-datamart_en/)

### 2.2 Separate forecast and analysis semantics

HRDPS, RDPS, GDPS, and RAQDPS have model initialization times and forecast lead
times. HRDPA, RDPA, and HREPA are analyses and must not be forced into a forecast
schema or displayed with a fictitious forecast hour. The catalogue therefore
uses a general product/run/time model that can represent both forecasts and
analyses.

### 2.3 Build a custom Airflow image before ingestion work

`LocalExecutor` is appropriate for a small, single-machine deployment, but its
workers run as scheduler subprocesses. The scheduler container therefore needs
all ingestion and geospatial dependencies, the shared Python packages, and the
weather data mount. CPU, memory, temporary disk, Airflow pools, and `parallelism`
must be deliberately constrained so GDAL jobs cannot starve the scheduler or the
serving APIs.

See the official [Airflow LocalExecutor documentation](https://airflow.apache.org/docs/apache-airflow/stable/core-concepts/executor/local.html).

### 2.4 Enforce least-privilege database roles

The implementation uses separate `weather_api`, `weather_tiles`,
`weather_ingest`, `weather_readonly`, and `weather_backup` roles. The non-login
`weather_owner` role owns application objects, while only `weather_migrator`
applies reviewed schema changes. Automated tests exercise the service-role
boundaries and `PUBLIC` has no application-schema access.

### 2.5 Keep source objects separate from display assets

A source GRIB2 file can contain one or many messages, while a display COG has one
specific semantic identity. Raw downloads therefore belong in
`ingestion.source_object`; processed and derived outputs belong in
`catalogue.asset`. Do not force raw files into the same uniqueness constraint as
map-ready products.

### 2.6 Make storage capacity a release gate

The server must not begin mirroring all variables from all models. The inventory
CLI must report file count and estimated bytes per run/day before a model is
enabled. Retention settings must be derived from measured data volume and actual
free space. Ingestion must stop safely at a configurable low-disk threshold.

### 2.7 Persist tile-layer identity

Redis may cache layer definitions, but it must not be the only source of truth.
An opaque tile token should resolve through a deterministic signed payload or a
database-backed layer specification. A Redis eviction or restart must not make
otherwise valid catalogue data permanently unrenderable.

### 2.8 Do not depend on the public OpenStreetMap tile service in production

The prototype may use it during local development. Before public deployment,
select a basemap provider whose usage policy matches expected traffic, or host a
basemap separately. This weather platform does not need to build its own basemap
for the MVP.

## 3. Current repository baseline

The repository now contains the working single-server platform rather than the
original Phase 0 scaffold:

- Docker Compose services for Caddy, the production frontend, weather API,
  restricted tile API, disk tile cache, PostgreSQL/PostGIS, Redis, Airflow 3,
  and optional Prometheus/Grafana monitoring.
- Handwritten, checksum-tracked migrations with tested least-privilege roles and
  separate `weather_app` and `weather_airflow` databases.
- Configuration-driven ingestion routes for HRDPS, RAQDPS, RDPS, GDPS, HRDPA,
  RDPA, and HREPA, including format-specific GRIB2 and NetCDF validation.
- Atomic source/COG storage, GRIB envelope/ecCodes and NetCDF/GDAL validation,
  SQL-backed ingestion state, and idempotent asset publication.
- A real catalogue/timeline/layer/sample API and signed-token raster renderer.
- A responsive MapLibre application driven entirely by catalogue availability,
  with multi-layer controls, animation, prefetch, cross-fades, legends, and point
  sampling.
- Backup, capacity, integrity, logging, metrics, monitoring, TLS, and systemd
  operational support.

The code and automated checks are complete enough for deployment review. A new
host must still perform the environment-specific acceptance work: pull/build all
images, initialize the fresh `weatherapp_data` tree, run the real ingest chosen
by the operator, measure storage and tile performance, configure the AMQPS feed
for unattended retrieval, select a production basemap, and complete an off-host
restore drill.

## 4. Product scope

### 4.1 Initial supported products

| Priority | Product | Kind | Initial purpose |
|---:|---|---|---|
| 1 | HRDPS | Deterministic forecast | First vertical slice and primary Canadian high-resolution display |
| 2 | RAQDPS | Air-quality forecast | Surface pollutant maps |
| 3 | RDPS | Deterministic forecast | Regional medium-range comparison |
| 4 | GDPS | Deterministic forecast | Global and longer-range coverage |
| 5 | HRDPA | Precipitation analysis | High-resolution observed/analysed precipitation |
| 6 | RDPA | Precipitation analysis | Regional precipitation analysis |
| 7 | HREPA | Ensemble precipitation analysis | Probabilistic/ensemble analysis after semantics are verified |

CAPS, Scribe, RDAQA, land, ocean, wave, ice, hydrology, and storm-surge products
are not part of the initial implementation. They may be proposed later through a
separate design change after availability and user value are established.

### 4.2 Initial variables

Do not download all fields. Begin with the following configured subset.

**HRDPS**

- 2 m air temperature
- 2 m relative humidity
- total cloud cover
- surface pressure
- mean sea-level pressure
- 10 m wind U and V components
- derived 10 m wind speed and direction
- wind gust
- total precipitation
- snowfall or snow accumulation, after its source semantics are documented
- visibility

**RAQDPS**

- PM2.5
- PM10
- ground-level ozone (O3)
- nitrogen dioxide (NO2)
- sulfur dioxide (SO2)
- any additional directly distributed field only after inventory verification

The current RAQDPS documentation describes 00 UTC and 12 UTC runs, hourly output
through 72 hours, and a roughly 10 km North American grid. Configuration must
still be generated from live inventory rather than inferred from this summary.

**Later pressure levels**

- 850 hPa temperature and humidity
- 700 hPa humidity
- 500 hPa geopotential height
- pressure-level wind components

### 4.3 Explicit non-goals for the first release

- Ocean, wave, sea-ice, storm-surge, and hydrology products
- Browser downloads of complete GRIB files
- Full forecast cubes in the browser
- Particle wind animation
- Pressure contour vector tiles
- Run-to-run comparison
- User accounts and saved views
- Kubernetes, distributed workers, S3, MinIO, or a CDN
- A general-purpose raster-processing endpoint

## 5. Target single-server architecture

```text
Internet
   |
   v
Caddy (TLS, routing, compression, cache headers)
   |
   +----------------------+----------------------+
   |                      |                      |
   v                      v                      v
React static app      Weather FastAPI       Restricted tile API
                                                  |
                                  +---------------+---------------+
                                  |                               |
                                  v                               v
                           PostgreSQL/PostGIS                 COG files
                                  ^                               ^
                                  |                               |
                                  +---------------+---------------+
                                                  |
                                     Airflow LocalExecutor
                                                  |
                                         ECCC MSC Datamart

Redis caches catalogue responses, layer resolution, samples, and locks. It is
not the system of record.
```

### 5.1 Services

Required Compose services:

```text
reverse-proxy
frontend
weather-api
tile-api
postgres
redis
airflow-api-server
airflow-scheduler
airflow-dag-processor
airflow-triggerer
airflow-init (one-shot)
storage-init (one-shot)
tile-cache
prometheus (optional profile)
grafana (optional profile)
```

The Airflow scheduler uses `LocalExecutor`. There is no separate worker service.
All Airflow services should use a project-built image derived from a pinned
official Airflow image once ingestion packages are introduced.

### 5.2 Host data layout

Production defaults should be rooted at `/srv/weather-platform` and overridden
through configuration in development.

```text
/srv/weather-platform/
|-- config/
|-- secrets/
`-- weatherapp_data/
    |-- airflow/logs/
    |-- backups/postgres/
    |-- caddy/
    |   |-- config/
    |   `-- data/
    |-- grafana/
    |-- postgres/
    |-- prometheus/
    |-- redis/
    |-- tile-cache/
    `-- weather/
        |-- raw/
        |-- staging/
        |-- processed/
        |-- derived/
        |-- quarantine/
        |-- cache/
        `-- temporary/
```

All jobs must receive the root path from configuration. No Python module may
hard-code the production path.

Processed assets use deterministic paths based on public semantic codes:

```text
processed/eccc/hrdps/continental/2026/07/16/12/
  air_temperature/2m_agl/f006.tif
```

Database IDs must not appear in storage paths.

## 6. Technology choices

| Area | Choice |
|---|---|
| Orchestration | Apache Airflow 3, LocalExecutor |
| ETL language | Python |
| GRIB metadata/validation | ecCodes |
| Raster transformation | GDAL, Rasterio, rio-cogeo where useful |
| Multidimensional processing | xarray/cfgrib only where it simplifies grouped calculations |
| Projection | pyproj |
| Array operations | NumPy |
| Database | PostgreSQL with PostGIS and `pgcrypto` |
| Database driver | psycopg 3 and psycopg-pool |
| Application API | FastAPI and Pydantic |
| Raster tiles | Restricted FastAPI service using TiTiler components |
| Cache | Redis plus reverse-proxy disk cache for rendered tiles |
| Frontend | React, TypeScript, Vite |
| Map | MapLibre GL JS |
| Server state | TanStack Query |
| Local UI state | Zustand |
| Reverse proxy | Caddy |
| Deployment | Docker Compose and systemd |
| Python packaging | `uv` with a committed lockfile |
| Testing | pytest and Vitest |

Version pins belong in lockfiles and container tags. Do not copy version numbers
from this document into code without checking the repository's current pins and
compatibility.

## 7. Repository target structure

Extend the existing monorepo toward this structure:

```text
weatherapp/
|-- README.md
|-- Makefile
|-- compose.yaml
|-- compose.dev.yaml
|-- pyproject.toml
|-- uv.lock
|-- docs/
|   |-- implementation-plan.md
|   |-- architecture.md
|   |-- ingestion.md
|   |-- database.md
|   |-- api.md
|   |-- frontend.md
|   |-- operations.md
|   `-- data-products/
|       |-- hrdps.md
|       |-- raqdps.md
|       |-- rdps.md
|       |-- gdps.md
|       |-- hrdpa.md
|       |-- rdpa.md
|       `-- hrepa.md
|-- config/
|   |-- models/
|   |-- variables/
|   `-- palettes/
|-- database/
|   |-- migrations/
|   |-- queries/
|   |-- seeds/
|   `-- README.md
|-- python/
|   |-- weather_common/
|   |-- weather_ingest/
|   |-- weather_api/
|   `-- weather_tiles/
|-- airflow/
|   |-- dags/
|   |-- include/
|   |-- plugins/
|   `-- tests/
|-- frontend/
|-- docker/
|-- scripts/
`-- tests/
```

Create directories only when a phase needs them. Empty architectural scaffolding
is not a deliverable.

## 8. Database design and management

### 8.1 Database boundaries

Use one PostgreSQL server and two databases:

```text
weather_app       application catalogue and state
weather_airflow   Airflow-owned metadata
```

Airflow may manage only `weather_airflow`. No application process may apply
`weather_app` migrations automatically at startup.

### 8.2 Roles

Create these roles before application tables:

| Role | Login | Purpose |
|---|---:|---|
| `weather_owner` | No | Own application schemas and objects |
| `weather_migrator` | Yes | Apply reviewed migrations only |
| `weather_api` | Yes | Read catalogue; write allowed application state |
| `weather_tiles` | Yes | Read the minimum asset/style data needed to render |
| `weather_ingest` | Yes | Write model runs, source state, assets, and quality results |
| `weather_readonly` | Yes | Troubleshooting/reporting |
| `weather_backup` | Yes | Backup access |

Default privileges must be set explicitly so new objects do not silently become
inaccessible or over-permissive.

### 8.3 Schemas

```text
app          application metadata and saved state
catalogue    providers, products, variables, runs, times, assets
ingestion    remote objects, processing attempts, quality checks
display      palettes, styles, persistent layer specifications
audit        important administrative events
```

Authentication tables are deferred until authentication is actually implemented.

### 8.4 Core relational model

The initial migrations should introduce these entities.

**`catalogue.provider`**

Identifies ECCC/MSC and stores stable documentation/base-service metadata.

**`catalogue.product`**

Represents HRDPS, RAQDPS, RDPS, GDPS, HRDPA, RDPA, or HREPA. Important columns:

```text
id
provider_id
code
name
product_kind          forecast | analysis | ensemble_analysis
enabled
priority
schedule_config jsonb
retention_config jsonb
created_at
updated_at
```

Use `product`, not `model`, for catalogue concepts that also include analyses.

**`catalogue.domain`**

Stores product domain code, native CRS, grid dimensions/resolution, footprint,
and source grid metadata. Add a GiST index to the EPSG:4326 footprint.

**`catalogue.variable`**

Stores a canonical variable code, name, class, canonical unit, value kind, and
vector-component metadata.

**`catalogue.product_field`**

Maps source parameter/level metadata to a canonical variable and level. Store a
safe `conversion_key`, not executable conversion expressions.

**`catalogue.vertical_level`**

Every field receives a level, including a real `surface` record. This avoids
nullable uniqueness ambiguity.

**`catalogue.product_run`**

Stores a forecast initialization or analysis production cycle, discovery and
processing states, completeness counts, source manifest summary, and timestamps.

**`catalogue.product_time`**

Stores valid time and optional forecast lead/interval metadata:

```text
id
product_run_id
valid_time
forecast_hour nullable
interval_start nullable
interval_end nullable
time_kind             instant | accumulation | average | maximum
```

For analysis products, `forecast_hour` is null. Add constraints that enforce the
correct relationship between product kind and forecast metadata where practical.

**`catalogue.asset`**

Stores only processed or derived asset identity and metadata:

```text
id
product_run_id
product_time_id
product_field_id
vertical_level_id
asset_role            processed_cog | derived_cog | thumbnail | vector
storage_backend       local initially
relative_path
mime_type
file_size_bytes
sha256
projection
bounds
width
height
band_count
nodata_value
minimum_value
maximum_value
statistics jsonb
provenance jsonb
status
created_at
updated_at
```

The semantic unique key is:

```text
(product_run_id, product_time_id, product_field_id,
 vertical_level_id, asset_role)
```

All members are non-null for a map-ready raster.

**`ingestion.source_object`**

Tracks a canonical remote object key, observed URLs/aliases, headers, expected
and actual size, local raw path, checksum, status, attempts, and last error. Use a
provider-scoped canonical key for uniqueness rather than the `/today` URL alone.

**`ingestion.processing_attempt`**

Records one attempt at validate, extract, transform, derive, or publish. Include
timestamps, worker, inputs/outputs, tool versions, metrics, and structured error
details.

**`ingestion.data_quality_result`**

Stores named quality checks for a source object or processed asset.

**`display.palette` and `display.variable_style`**

Store validated JSON palette definitions and default display behavior. The API
must validate definitions before returning them to the tile service or browser.

**`display.layer_specification`**

Optionally persists immutable combinations of asset, style revision, resampling,
and display range. Its public token is opaque and has no raw path.

### 8.5 SQL rules

- All application queries live in `database/queries/**/*.sql`.
- No SQL is assembled from user-provided identifiers.
- Values use psycopg parameter binding.
- Table and column names are schema-qualified.
- Queries explicitly list selected columns; do not use `SELECT *`.
- Python repositories remain thin and return typed domain objects.
- Transactions are explicit at the repository/service boundary.
- Important query plans and indexes are documented when the endpoint is added.
- JSONB is for model-specific metadata, provenance, and style definitions—not for
  core fields needed for identity, filtering, or constraints.

### 8.6 Manual migration contract

Numbered migrations remain immutable after they are applied anywhere shared:

```text
0001_initialize_application.sql
0002_create_roles_and_schemas.sql
0003_create_catalogue.sql
0004_create_ingestion.sql
0005_create_display.sql
0006_seed_initial_catalogue.sql
```

The migration tooling must:

1. Display server, port, database, and user.
2. Refuse an unexpected target database.
3. Calculate SHA-256 before execution.
4. Refuse a previously applied filename with a different checksum.
5. Treat an already-applied identical migration as a successful no-op when
   applying a directory of migrations.
6. Require confirmation unless `--yes` is supplied.
7. Execute with `psql` and `ON_ERROR_STOP`.
8. Apply the migration and migration record in the same transaction.
9. Run post-migration verification.

Every migration must have a disposable-database test. Rollback files are not a
substitute for restoring a backup; destructive production rollbacks require a
specific reviewed procedure.

## 9. Configuration design

### 9.1 Product configuration

Schedules, expected forecast times, source locations, enabled fields, retention,
and completeness policy belong in validated YAML configuration.

Conceptual example:

```yaml
code: hrdps
provider: eccc
kind: forecast
enabled: true
adapter: hrdps
domains:
  - code: continental
run_hours_utc: [0, 6, 12, 18]
discovery:
  mode: https_listing
  base_url: https://dd.weather.gc.ca/
  late_arrival_grace_minutes: 180
  retry_window_hours: 12
limits:
  maximum_parallel_downloads: 4
retention:
  raw_days: 30
  processed_days: 180
visibility:
  required_field_codes:
    - air_temperature_2m
```

The adapter owns directory and filename interpretation. The generic DAG must not
contain product-specific regular expressions.

### 9.2 Variable and palette configuration

Variable mappings must specify:

- canonical variable and level
- authoritative source parameter identifiers
- expected source unit
- `conversion_key`
- output data type and nodata policy
- resampling method
- whether download, processing, and display are enabled
- default style code

Conversion keys resolve to reviewed Python functions with unit tests. Never use
`eval`, arbitrary formulas from the database, or user-provided raster expressions.

## 10. Source discovery and inventory

### 10.1 Adapter interface

```python
class ProductSourceAdapter(Protocol):
    def list_candidate_runs(...) -> list[RemoteRun]: ...
    def list_run_objects(run: RemoteRun) -> list[RemoteObject]: ...
    def canonical_object_key(obj: RemoteObject) -> str: ...
    def parse_object(obj: RemoteObject) -> ParsedSourceObject: ...
    def expected_manifest(run: RemoteRun) -> ExpectedManifest: ...
```

Adapters contain source-specific naming and layout logic only. They do not write
the database, create COGs, or decide HTTP responses.

### 10.2 Inventory CLI

Before an adapter can be enabled, implement:

```bash
uv run weather-ingest --config-root config inspect-source \
  --product hrdps \
  --run 2026-07-16T12:00:00Z
```

It must report:

- resolved source directory and run
- remote object count and estimated total bytes
- parsed parameters, levels, units, and forecast/analysis times
- configured, ignored, and unknown objects with explicit reasons
- enabled download/display fields
- estimated daily raw and processed storage cost
- parser errors without silently discarding files

Persist the verified results in `docs/data-products/<product>.md`. A live network
inventory is an operator command, not a required offline unit test.

## 11. Airflow ingestion design

### 11.1 DAGs

Use a configuration-driven weather-data DAG factory. The implemented factory creates:

```text
eccc_hrdps_ingest
eccc_raqdps_ingest
eccc_rdps_ingest
eccc_gdps_ingest
eccc_hrdpa_ingest
eccc_rdpa_ingest
eccc_hrepa_ingest
```

The analysis routes share the bounded task graph and preserve accumulation time
semantics. HRDPA/RDPA use GRIB2 validation. HREPA selects and validates reviewed
NetCDF variables, retains the complete ensemble source, and publishes its
control member and percentile summaries.

The operational-hardening phase provides these manual, bounded maintenance DAGs:

```text
weather_integrity_audit
weather_asset_retention
weather_cleanup_temporary_files
```

### 11.2 Main ingestion flow

```text
discover missing recent inventory and merge AMQPS deliveries
   |
register run and source manifest
   |
download source objects [dynamic mapping, bounded pool]
   |
validate GRIB or NetCDF [dynamic mapping]
   |
enumerate/select messages
   |
normalize/derive fields
   |
create COGs
   |
validate COGs and compute statistics
   |
publish files atomically and register assets
   |
evaluate run visibility/completeness
```

XCom carries database IDs and small summaries only. It must not carry remote
directory listings, raster arrays, file bodies, or large manifests.

### 11.3 Download behavior

For every object:

1. Acquire an `eccc_downloads` Airflow pool slot; start with four slots.
2. Stream to a deterministic `.part` file.
3. Record headers and byte count.
4. Validate reported size when available.
5. Calculate SHA-256.
6. Atomically rename into `raw/`.
7. Update source state in one transaction.

Use bounded timeouts, exponential backoff with jitter, and a descriptive user
agent. Follow the ECCC service usage policy. A retry must resume safely or restart
the same deterministic temporary target without producing duplicates.

### 11.4 GRIB validation and selection

Use ecCodes as the authoritative metadata reader. Validate:

- readable GRIB messages exist
- grid definition and projection are recognized
- initialization/production and valid times match the parsed source identity
- parameter and level match filename/configuration expectations when ecCodes
  exposes an unambiguous standard definition
- dimensions and coordinates are plausible
- decoded grid dimensions and point counts are complete and consistent

ECCC-local fields may decode with an `unknown` short name/unit or a generic level
in a stock ecCodes installation. Those values are retained as informational
metadata rather than used as a false hard failure; the reviewed adapter filename
identity, timestamps, grid type, exact dimensions, and point count remain hard
checks. Unknown and unsupported source identities are recorded with a reason.
Corrupt or semantically inconsistent files retain their database history.

Use cfgrib/xarray only for operations that benefit from labelled multidimensional
arrays. A simple single-message transformation may go directly through GDAL.

### 11.5 Unit normalization and derived fields

Normalize map-facing values during processing and record source unit, target unit,
conversion key/version, and tool versions in provenance.

Initial canonical units:

| Variable | Canonical unit |
|---|---|
| Temperature | degrees Celsius |
| Relative humidity/cloud fraction | percent |
| Pressure | hPa |
| Wind components/speed | m/s internally; UI conversion allowed |
| Wind direction | degrees true |
| Precipitation | mm with accumulation interval retained |
| Visibility | km |
| PM2.5/PM10 | micrograms per cubic metre when source semantics agree |
| Other pollutants | documented source/canonical concentration unit |

Derived wind speed and direction must be generated from matched U/V grids with
the same run, valid time, level, grid, and units.

### 11.6 COG creation

One display COG normally represents one product, domain, run, valid time, field,
and vertical level. Starting GDAL options:

```text
driver: COG
block size: 512
compression: ZSTD or DEFLATE, benchmarked per field class
BigTIFF: IF_SAFER
overviews: automatic
threads: explicitly bounded per Airflow task
```

Do not use `ALL_CPUS` in every concurrent task on a single server. Configure a
small per-task thread count and cap concurrent COG work through an Airflow pool.

Use bilinear resampling for continuous display fields, nearest-neighbour for
categorical fields, and an explicitly reviewed method for accumulations. Create
into staging, validate, then atomically move to the deterministic final path.

Validation includes COG structure, tiling, overviews, CRS, bounds, dimensions,
band count, nodata, finite min/max, and non-empty data.

### 11.7 State and visibility

Run states:

```text
discovered
downloading
partially_available
processing
complete
complete_with_warnings
failed
expired
```

A run may become visible once its configured core fields pass quality checks and
at least one valid time is available. Completeness is product-specific; the UI
must show partial availability rather than pretending missing frames exist.

## 12. Application API

### 12.1 General contract

- Prefix versioned routes with `/api/v1`.
- Return JSON with UTC ISO 8601 timestamps.
- Prefer stable public codes over numeric IDs.
- Validate all inputs and cap collection sizes.
- Never expose host paths or source credentials.
- Use a consistent error envelope and request ID.
- Keep OpenAPI enabled for development and operator use.

### 12.2 Catalogue endpoints

```text
GET /api/v1/products
GET /api/v1/variables
GET /api/v1/products/{product_code}/domains
GET /api/v1/products/{product_code}/fields?run={timestamp}
GET /api/v1/products/{product_code}/runs?field={field_code}&limit={1..100}&before={timestamp}
GET /api/v1/products/{product_code}/runs/{run_time}/times?field={field_code}
GET /api/v1/products/{product_code}/timeline?domain={domain_code}&field={field_code}&start={timestamp}&end={timestamp}
GET /api/v1/status/ingestion
```

Filters and pagination must be bounded. Return only fields/times that have visible
assets unless an authenticated administrative endpoint explicitly requests ingest
state. The cross-run timeline returns one frame per valid time and prefers the
smallest forecast lead, then the newest run. With no explicit range it starts at
the closest available frame at or before now and ends 24 hours later or at the
latest available frame, whichever comes first.

### 12.3 Layer resolution

```text
GET /api/v1/layers/resolve
```

Input:

```text
product, domain, run, field, valid_time, style, format
optional paired minimum and maximum display overrides
optional finite opacity_cutoff in the field's canonical unit
```

Output includes product/run/time metadata, unit, bounds, legend/style metadata,
and a tokenized tile URL. It never includes a local file path.

The token must bind at least:

```text
asset identity
asset checksum or revision
style identity/revision
range and resampling choices
token format version
optional expiry
```

### 12.4 Point sampling

```text
GET /api/v1/sample
```

Accept one coordinate and a bounded list of visible layer selections. Resolve
registered COGs, transform the coordinate into each raster CRS, and read a small
window. Return value, canonical unit, run time, valid time, level, and nodata
status. Cache briefly in Redis.

### 12.5 Health and status

```text
GET /health/live
GET /health/ready
GET /api/v1/status/ingestion
```

Liveness has no dependencies. Readiness checks PostgreSQL, required data mounts,
and a minimal catalogue query. Redis failure should degrade caching; whether it
makes the service unready must be decided per service and tested. ECCC availability
must never be part of API readiness.

## 13. Restricted tile API

### 13.1 Route

```text
GET /tiles/v1/{layer_token}/{z}/{x}/{y}.webp
GET /tiles/v1/{layer_token}/{z}/{x}/{y}.png
```

The tile API:

1. validates the token format/signature,
2. resolves a registered active asset and validated style,
3. verifies the resolved path remains under the configured processed-data root,
4. renders only the requested tile,
5. returns cache headers and request metrics.

It must reject arbitrary URLs, `file://`, traversal, unbounded expressions,
unknown styles, excessive zoom, and invalid tile coordinates.

### 13.2 Cache behavior

Immutable asset/style tokens permit long browser and reverse-proxy cache
lifetimes. A source checksum or style revision change creates a new token. Caddy
may supply compression and cache headers, but a dedicated cache module or another
proxy may be required for disk caching; verify actual Caddy behavior rather than
assuming it caches upstream responses by default.

## 14. Frontend

### 14.1 Main interaction

Users can:

- choose product, variable, level, valid-time range, and active valid time
- pan and zoom the map
- play, pause, step, loop, and change animation speed
- add up to three compatible raster layers
- reorder layers and change opacity
- hide values below a per-layer opacity cutoff
- click the map to sample visible layers
- see unit, legend, the active frame's initialization/production time, valid
  time, and lead time
- distinguish forecasts, analyses, and ensemble analyses

### 14.2 State boundaries

TanStack Query owns server state: products, runs, fields, times, layer resolution,
and samples. Zustand owns transient client state: active selections, layer order,
opacity, playback, and viewport. Do not duplicate query responses in Zustand.

Validate API responses with Zod at the boundary.

### 14.3 Animation

Do not download a complete forecast cube. For each transition:

1. resolve and preload the next frame,
2. keep current and next raster layers mounted,
3. wait for the next source to load,
4. cross-fade opacity,
5. release the old layer,
6. prefetch a small bounded number of subsequent frames,
7. cancel stale work when model, field, run, or level changes.

Skip unavailable times explicitly and keep GPU/browser cache use bounded.

### 14.4 Legends and styles

The server supplies palette stops, range, unit, precision, interpolation, and
nodata behavior. React components must not hard-code weather-variable ranges.

### 14.5 Accessibility and mobile

- All controls must be keyboard accessible and labelled.
- Timeline stepping must work without dragging.
- Colour palettes require sufficient contrast and must not be the only carrier of
  categorical meaning.
- Respect reduced-motion preferences by disabling automatic cross-fades/playback.
- Mobile uses a full-screen map with a bottom sheet and collapsible timeline.

## 15. Operations

### 15.1 Resource controls

On one server, ingestion and serving compete for the same CPU, memory, and disk.
Set and document:

- Airflow `parallelism`
- ECCC download pool slots
- GDAL/COG processing pool slots
- per-task CPU/thread limits
- container memory limits or reservations
- temporary-directory capacity
- PostgreSQL connection-pool sizes
- tile request concurrency and timeouts

The initial conservative settings should favor a responsive API over ingest speed.

### 15.2 Retention

The operational application retains every displayable forecast and analysis
cycle, including raw sources and processed assets. Configured ECCC products set
`retain_forever: true`, so age-based maintenance does not select their payloads.
The age values remain available only for a future product that explicitly opts
out of permanent retention:

| Data class | Initial policy |
|---|---:|
| Raw GRIB2 | Indefinite |
| Staging | 2 days |
| Temporary | 1 day |
| Quarantine | 14 days |
| Processed forecast and analysis COGs | Indefinite |
| Catalogue identities/audit events | Indefinite (small operational records) |
| Tile cache | Size-based |

If a future product opts into deletion, the safe workflow is:

1. mark the asset pending deletion,
2. exclude it from new layer resolution,
3. delete the file,
4. verify absence,
5. mark the asset deleted while retaining identity/provenance.

Raw source deletion follows an equivalent recorded process. Never delete database
history first.

### 15.3 Backups

Back up both PostgreSQL databases, configuration, SQL migrations, palette/style
files, and secrets through separate secure handling. Use Restic or Borg to a
physically separate target. Processed files may be regenerable, but ECCC's source
retention is limited, so any historical data considered valuable must also be
backed up or replicated.

Run restore drills at least monthly and document the result.

### 15.4 Security

Expose only ports 80 and 443 publicly. Keep PostgreSQL, Redis, Airflow internals,
and direct API container ports private. Protect the Airflow UI with a private
network or authenticated reverse proxy.

Secrets must not be committed. Production secrets live in root-readable files or
an equivalent local secret mechanism with `0600` permissions. Use distinct
credentials per database role.

### 15.5 Observability

Emit structured JSON logs with request/run/asset correlation fields. Expose
Prometheus-compatible metrics for request latency, tile render time, cache results,
downloads, conversion duration, failures, queue depth, latest visible run, and
disk capacity.

Add Prometheus/Grafana only after core ingestion works; structured logs and health
endpoints are required from the beginning.

## 16. Testing strategy

### 16.1 Unit tests

- configuration validation
- directory and filename parsing
- canonical remote-object identity
- run/valid-time parsing
- unit conversions
- U/V derived-field matching and calculations
- deterministic paths
- token creation/verification
- palette validation/interpolation
- SQL loader behavior

### 16.2 Database tests

Against a disposable real PostgreSQL/PostGIS database:

- apply all migrations from empty
- apply the migration directory twice successfully
- detect a changed applied migration
- prove transaction rollback on failure
- verify constraints and indexes
- exercise core query files
- verify every service role's allowed and forbidden operations

### 16.3 Geospatial integration tests

Use small pinned fixtures with documented provenance or a separate fixture-fetch
command:

- open and inspect GRIB
- generate and validate a COG
- assert CRS, bounds, dimensions, nodata, and known pixel values
- sample a known coordinate
- render a tile with correct transparency
- reject malformed/all-nodata inputs

Tests must not require the live ECCC service unless explicitly marked as network
tests.

### 16.4 Airflow tests

- import every DAG
- enforce unique IDs and task dependencies
- validate schedules, retries, pools, and mapping boundaries
- reject invalid product configuration
- prove retry/idempotency behavior with test doubles and integration fixtures
- keep large data out of XCom

### 16.5 API, security, and frontend tests

- catalogue success/error contracts
- invalid codes, coordinates, times, and excessive collections
- Redis degradation behavior
- token expiry/tampering and arbitrary URL/path rejection
- map load, product/field/time selection, animation, sampling, and multiple layers
- mobile controls, keyboard use, reduced motion, loading, and failure states

### 16.6 Performance targets

Treat these as initial goals to measure, not guarantees:

| Operation | Goal |
|---|---:|
| Cached tile | < 100 ms |
| Uncached tile | < 1.5 s |
| Catalogue endpoint | < 200 ms |
| One-layer point sample | < 500 ms |
| Preloaded frame transition | < 250 ms |
| Initial map usable on broadband | < 4 s |

Record ingestion wall time, CPU, peak memory, temporary disk, final bytes per run,
and tile latency before enabling each additional model.

## 17. Implementation phases

No phase is complete until its acceptance tests pass and its operational notes are
updated.

Implementation snapshot on 2026-07-16:

| Phase | Repository state | Remaining deployment acceptance |
|---|---|---|
| 0 — scaffold | Implemented | Pull/build every image and exercise clean-host startup |
| 1 — database | Implemented and tested on PostgreSQL/PostGIS | Apply and verify migrations on the deployment database |
| 2 — inventory foundation | Implemented and live metadata-verified | Repeat inventory when ECCC announces product changes |
| 3 — HRDPS temperature | End-to-end code and synthetic COG path verified | Ingest and benchmark at least 12 real frames |
| 4 — core HRDPS/UI | Multi-layer UI and field mappings implemented; high-volume fields default disabled | Approve semantics/capacity, enable fields through reviewed config and SQL |
| 5 — RAQDPS | Adapter and five pollutant paths implemented | Ingest a run and verify values against an independent reference |
| 6 — RDPS/GDPS | Adapters and temperature paths implemented | Ingest, benchmark, and exercise GDPS antimeridian views |
| 7 — analyses | HRDPA/RDPA GRIB2 ETL enabled; HREPA inventory and time semantics implemented | Add a reviewed NetCDF processor before enabling HREPA ETL |
| 8 — operations | TLS, cache, metrics, dashboards, backups, capacity and integrity tooling implemented | Install AMQPS, exercise reboot/restore, and approve historical-archive capacity |

### Phase 0 — Complete and verify the platform scaffold

**Current state:** Implemented in the repository; clean-host acceptance is an
operator/deployment gate.

Deliverables:

- clean-machine Compose verification
- top-level README and startup/stop/restart/log instructions
- persistent PostgreSQL and Redis verification
- working Airflow UI and starter DAG
- working FastAPI and tile liveness routes
- working MapLibre shell
- reliable manual migration directory execution
- development-only credentials clearly distinguished from production setup
- committed Python and frontend lockfiles

Acceptance:

```bash
cp .env.example .env
make dev-up
make db-create
make db-verify
make test
make airflow-test
```

works from a clean checkout, a second `make db-create` is a successful no-op, and
no ORM package is present.

### Phase 1 — Database foundation and least privilege

Deliverables:

- owner and service roles with tested grants
- `catalogue`, `ingestion`, `display`, and `audit` schemas
- core tables and constraints from Section 8
- seed data for ECCC and initial canonical variables/levels/styles
- async SQL loader and thin psycopg repositories
- runtime services switched away from migration credentials

Acceptance:

- empty database builds solely from reviewed SQL
- checksum and rollback-on-error tests pass
- API, tiles, and ingest role boundary tests pass
- no application startup applies migrations

### Phase 2 — HRDPS inventory and processing foundation

Deliverables:

- custom project Airflow/ingest image with pinned geospatial tools
- validated product configuration framework
- HRDPS adapter and inventory CLI
- documented current HRDPS naming, grid, fields, timing, and storage estimate
- sample fixture download procedure
- shared download, GRIB inspection, deterministic path, and state modules

Acceptance:

- a live run can be inventoried without downloading everything
- every remote object is configured, ignored with a reason, or flagged unknown
- estimated bytes per run/day are reported
- parser and inventory fixtures pass offline tests

### Phase 3 — HRDPS 2 m temperature vertical slice

Implement the complete path:

```text
discover -> register -> download -> validate -> normalize -> COG -> validate
-> publish -> catalogue API -> tile -> MapLibre -> time step -> point sample
```

Acceptance:

- at least 12 real forecast frames are browsable
- animation only advances to loaded/available frames
- map click returns the correct canonical value/unit
- rerunning discovery and processing creates no duplicates
- an intentionally removed processed COG is detected and recreated
- arbitrary tile URLs and paths remain inaccessible
- measured storage and runtime are documented

### Phase 4 — Core HRDPS fields and multiple layers

Add humidity, cloud, pressure, wind, gust, precipitation, snow (if semantically
verified), and visibility. Add up to three layers, opacity, ordering, dynamic
legends, and bounded multi-field point sampling.

Acceptance:

- UI contents come from catalogue availability
- each field has unit/range/nodata tests
- U/V-derived wind is correctly paired
- accumulation intervals are visible and preserved
- missing frames are represented explicitly

### Phase 5 — RAQDPS

Add the RAQDPS adapter, pollutant mappings, air-quality styles, and UI grouping.
Do not label a model concentration palette as a health standard unless the
threshold source and unit conversion are documented.

Acceptance:

- PM2.5, ozone, and NO2 render and sample correctly
- run/grid metadata remains distinct from HRDPS
- RAQDPS failures do not block HRDPS ingestion or visibility
- storage and resource use remain within configured limits

### Phase 6 — RDPS and GDPS

Add adapters/configuration, model selection, different footprints and time
cadences, and GDPS global-wrap handling.

Acceptance:

- switching products does not reload the application
- only available fields and times are selectable
- historical run ordering and cursor pagination are deterministic
- antimeridian/global tile behavior is tested
- capacity review approves indefinite retention before routine ingestion is enabled

### Phase 7 — Precipitation analyses

Add HRDPA, RDPA, and HREPA after their payload semantics are verified.
Use analysis/ensemble-analysis UI labels and omit forecast lead time.

Acceptance:

- analysis valid and interval times are correct
- accumulation intervals and units are visible
- analyses are never represented as deterministic forecasts
- HREPA uncertainty/member/summary meaning is documented before display

### Phase 8 — Operational hardening

Deliverables:

- retention, reconciliation, integrity, and cleanup DAGs
- low-disk admission control
- backup and restore automation/documentation
- structured metrics and dashboards
- rate limiting and production TLS configuration
- reverse-proxy tile cache, sized and verified
- systemd startup and reboot recovery

Acceptance:

- reboot restores the service
- a database restore drill succeeds
- corrupt and missing files are surfaced and reconciled
- stalled ingestion is visible
- low disk stops new downloads safely before filesystem exhaustion

## 18. Codex execution rules

For every phase, Codex must:

1. inspect the existing repository and this document,
2. state the narrowly bounded phase or slice being implemented,
3. preserve handwritten SQL and the no-ORM rule,
4. update tests and relevant documentation with the code,
5. run the proportionate verification commands,
6. report results and known limitations,
7. stop at the phase acceptance gate for owner review.

Codex must not:

- introduce an ORM, Kubernetes, Celery, MinIO, or raster-in-PostgreSQL storage
- automatically apply application migrations
- add product-specific filename logic outside adapters
- put large manifests or binary data in XCom
- expose arbitrary TiTiler URLs, paths, or expressions
- create one copied DAG per field
- silently ignore unknown GRIB messages
- enable full-product ingestion before inventory and capacity review
- commit secrets or use migration credentials at runtime
- claim a phase is complete without running its acceptance checks

## 19. Next deployment task

The next task is deployment acceptance, not another greenfield build phase:

> On the target Linux server, clone this repository, replace every development
> secret, place `WEATHERAPP_DATA_DIR` on the intended data filesystem, keep
> `WEATHER_DATA_DIR` inside it, start the
> complete Compose stack, apply and verify migrations twice, run the automated
> test/build suite, and complete a single bounded HRDPS temperature ingest from a
> reviewed inventory. Confirm at least 12 frames in the timeline, compare a point
> sample with the source field, record disk/CPU/tile measurements, exercise a
> database backup and disposable restore, then configure the official ECCC AMQPS
> feed before enabling unattended retrieval. Keep additional fields disabled
> until their measured storage cost and semantics are approved.
