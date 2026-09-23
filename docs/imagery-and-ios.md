# Collected radar/satellite imagery and native iPhone client

Implemented 2026-09-07. The server owns acquisition, validation, transformation,
storage and PostgreSQL registration. Both clients may consume the resulting
read-only APIs; no request handler fetches upstream imagery.

## Data path

    Airflow eccc_imagery_ingest (every six minutes, bounded)
      → GeoMet GetCapabilities → advertised observation times
      → GeoMet GetMap with explicit TIME, CRS:84 and configured bounding box
      → raw PNG + capabilities XML on server
      → validated RGB(A) COG on server
      → catalogue.imagery_frame in PostgreSQL
      → read-only imagery catalogue and PNG tile API
      → native SwiftUI/MapKit app (and other read-only clients)

These are pre-rendered, georeferenced observation images for display, not raw
scientific radar reflectivity/satellite radiances or model scalar assets. They
are intentionally registered in separate imagery tables. Point sampling applies
to scalar COGs only; RGB colours must not be interpreted as numeric weather values.

## Installation on the ETL/API server

1. Apply the new handwritten migration through the existing migration runner:
   ./scripts/apply_migration.sh database/migrations/0027_add_collected_imagery.sql.
   Application startup does not apply migrations.
2. Review config/imagery.json. Defaults cover Atlantic Canada
   [-69, 41, -52, 50], at 2048 × 1536 display pixels, a three-hour source window,
   at most four new frames per product per invocation, at least 20 GiB free disk
   and at most 100 GiB in the imagery archive.
3. Rebuild/deploy the weather API, tile API and Airflow images so their packaged
   Python and SQL files include this change. Caddy and Nginx already route/cache
   /tiles/*; their configuration requires no new public upstream routes.
4. Unpause eccc_imagery_ingest in Airflow. The deployment's default is to create
   new DAGs paused. The existing eccc_downloads pool is used. Verify a successful
   cycle and inspect /api/v1/imagery.

For one operator-run invocation, in the configured server environment:

    python -m weather_ingest.imagery --config config/imagery.json

WEATHER_DATABASE_URL must use weather_ingest, WEATHER_DATA_ROOT is the shared
server archive root, and WEATHER_SQL_ROOT locates the reviewed query files.
Airflow already provides these variables. The API and tile server use their
existing read-only database roles and read-only data mounts.

Changing the bounding box or image dimensions creates a new configuration
identity. Check coverage and effective display resolution before broadening
the area: a larger area at the same pixel dimensions reduces map detail.
The initial imagery coverage is Atlantic Canada, while model/forecast coverage
continues to follow the existing server catalogue.

## APIs

- GET /api/v1/imagery: enabled imagery products, attribution, stale state and
  collected frames within the most recent 24 hours (bounded to 240 per product).
  Each frame includes UUID, valid time, bounds and a relative tile template.
- GET /tiles/imagery/{frame_id}/{z}/{x}/{y}.png: render a 256-pixel tile from
  the registered local COG. No arbitrary path, source URL or WMS parameters are
  accepted. Invalid UUIDs/tile coordinates are rejected. Outside coverage yields
  a transparent tile. ETag/immutable caching uses the stored content identity.
- GET /tiles/imagery/{frame_id}/legend.png: the provider legend collected by ETL,
  stored locally and linked to the frame's provenance.
- GET /api/v1/forecast/nearest?latitude=44.65&longitude=-63.57: the nearest
  collected forecast-region representative point within 200 km, with distance
  and matchKind: nearest_representative_point. This is a proximity match,
  not a polygon lookup or a hyperlocal forecast.

An imagery product is stale when no stored frame exists or the latest observation
is over 30 minutes old. A missing migration returns 503; it does not trigger a
fallback fetch from GeoMet.

## Storage and failure behaviour

PostgreSQL is authoritative. It registers a frame only after validated files are
published. Unique product/time/configuration keys make repeated collection
idempotent. Content-derived filenames preserve immutable cache identities.
Frame provenance records explicit WMS parameters, raw source path, and source,
capabilities and COG SHA-256 checksums.

Requests have timeouts and byte limits, XML entity/DTD declarations are rejected,
and dimensions and time intervals are bounded. Failures leave prior registered
frames available and fail the Airflow task for its normal retry/logging handling.
Files published before a failed DB commit may be orphaned; reconciliation can
reuse their identities. Archive accounting includes these files.

Collection stops at the disk/archive budget. No automatic history deletion is
introduced; this follows the project's append-only weather archive policy.
Increase capacity or design an explicit retention change before the cap is
reached. Low-disk admission requires capacity for one source/COG staging operation.
Public API handlers never enqueue ETL or fill missing frames on demand.

## Sources and current scope

The allowlist currently includes RADAR_1KM_RRAI,
GOES-East_1km_NaturalColor and GOES-East_2km_NightIR. Radar extrapolation,
GOES-West, additional bands and long-history browsing are not included yet.
Layer IDs and timestamps were checked against live GeoMet capabilities.

Official references:

- [ECCC radar WMS layers and temporal availability](https://eccc-msc.github.io/open-data/msc-data/obs_radar/readme_radar_geomet_en/)
- [ECCC GOES imagery WMS layers](https://eccc-msc.github.io/open-data/msc-data/obs_satellite/readme_satellite_geomet_en/)

## Verification

The new migration was applied to an isolated temporary PostgreSQL database.
One live frame from each of the three sources was collected and served back as
PNG tiles through the read-only API. The serving role was verified unable to
mutate the imagery table. This validation did not alter the deployment database.

Automated tests in tests/test_imagery.py cover temporal gaps/future-time
filtering, invalid capabilities, budgets, invalid image rejection, COG
georeferencing/alpha, bounded downloads, local-only tile reads and HTTP caching.
The existing forecast and catalogue regression suites also run alongside them.

## LAN serving update — 2026-09-07

The running weather API had been built before the coordinate-lookup endpoint was
added. A phone with a valid location therefore received HTTP 404 `Not Found` at
`/api/v1/forecast/nearest`, even though regional and hourly forecasts worked.
This was a server-version mismatch, not an iOS permission rejection.

The weather API and tile API were rebuilt and recreated on the existing Compose
deployment at `http://wolf359.iolan:18080`. Migration 0027 was applied and its
checksum verified after adding the migration-runner registration statement that
was missing from the unapplied file. PostgreSQL and existing Airflow/ETL processes
were left running.

Live verification confirmed both services ready, the forecast page responding
with HTTP 200, Halifax coordinate lookup returning 13 day/night periods, and its
hourly endpoint returning all 72 hours complete. The imagery catalogue now responds
successfully, but imagery collection remains paused and there are no stored frames
yet. This serving update did not activate new collection schedules.

The iPhone simulator was then launched against this real HTTP server with a
simulated Halifax GPS fix. It displayed "Current location", the real Halifax Metro
bulletin, and the server's precipitation estimate without a server-update error.
Verification also passed 64 server tests, 38 iOS unit tests, and 6 simulator UI tests,
including the normal location-permission prompt and denied-permission fallback.

Rollback images were retained as `weather-platform-weather-api:before-ios-20260907`
and `weather-platform-tile-api:before-ios-20260907`. A verified custom-format
database backup is under
`weatherapp_data/backups/postgres/ios-server-update.vd3EPk/weather_app.dump`.
The standard backup role could not read an existing sequence, so this deployment
backup used the existing local PostgreSQL administrator without changing grants.

The iPhone client also now falls back to the server's Halifax regional forecast
when an older server lacks coordinate lookup, separately from the GPS-denied or
timeout fallback. It does not label a working lookup's lack of regional coverage
as a location-permission failure.

## Imagery collection activation — 2026-09-07

The iPhone's "No collected frames" message reflected an empty server catalogue:
`eccc_imagery_ingest` was paused, had never run, and the running Airflow image
contained neither `weather_ingest.imagery` nor the imagery SQL query files. The
earlier LAN serving update had installed the API/schema only, not the collector.

The Airflow image was rebuilt and its API server, scheduler, DAG processor and
triggerer recreated. No queued or running tasks were present before the update;
PostgreSQL and the weather/tile serving services were left running. The former
image is retained as `weather-platform-airflow:before-imagery-20260907`.

`eccc_imagery_ingest` is now unpaused on its existing six-minute schedule. Its
first scheduled run (`scheduled__2026-09-07T18:48:00+00:00`) succeeded at
18:51:17 UTC, registering 12 frames: four per radar, natural-colour satellite and
night-infrared product. The initial archive was approximately 51 MiB, with the
existing disk/archive limits unchanged. Collection remains exclusively server-side.
The "run all data collection DAGs" script now includes this job as well.

Verification against `http://wolf359.iolan:18080` confirmed all three products
non-stale, their latest Halifax-area tiles and legends returning PNG/HTTP 200,
and conditional tile requests returning HTTP 304. All four Airflow services and
both serving APIs were healthy. The imagery, operator-script and imagery-DAG
regression checks passed (27 tests).

No iPhone rebuild is required. Switching to Radar or Satellite reloads the server
catalogue; an active imagery map also checks for updates every 60 seconds. Initial
coverage remains Atlantic Canada, as specified in `config/imagery.json`.
