# GDPS seven-day forecast overlay implementation record

**Date:** 2026-07-28  
**Provider:** Environment and Climate Change Canada, Meteorological Service of
Canada  
**Product:** Global Deterministic Prediction System (GDPS), 15 km

## Objective

Collect ECCC's general deterministic forecast at the cadence at which it is
published and make its temperature, moisture, wind, pressure, cloud,
precipitation, and snowfall fields available as time-selectable raster overlays
in the weather application.

## Publication and scheduling rationale

GDPS initializes at 00 and 12 UTC and publishes forecast fields progressively.
A twice-daily polling job would introduce avoidable latency and would be brittle
when publication is delayed or partially missed. The implementation therefore
uses two complementary paths:

1. ECCC's anonymous AMQPS notification stream delivers matching completed files
   into the persistent inbox as they are published.
2. `eccc_gdps_ingest` reconciles provider inventory every 15 minutes. It
   recovers queue outages, late files, incomplete conversions, and data
   published before the subscriber began listening.

The reconciliation schedule is `*/15 * * * *`. Each invocation processes at
most 128 source objects. Recovery can occupy at most 96 positions, leaving at
least 32 positions for newly discovered data. This makes the job bounded while
ensuring fresh fields cannot be hidden behind an older processing backlog.

## Source inventory findings

The source contract was sampled against the live ECCC Datamart for the
2026-07-27 12Z cycle:

- `WindSpeed_AGL-10m` is published through forecast hour 240;
- `Precip-Accum1h_Sfc` is published through forecast hour 144;
- `Precip-Accum3h_Sfc` is published on three-hour boundaries through forecast
  hour 168.

The overall GDPS forecast cadence remains hourly from 000 through 084 and every
three hours from 087 through 240. Field-specific availability is encoded in
YAML and enforced during source discovery so the DAG does not request
nonexistent precipitation files.

## Data and display contract

The implementation adds a direct 10-metre wind-speed mapping and a
three-hour precipitation-accumulation mapping. It extends the existing
one-hour precipitation window from hour 84 to hour 144. Display labels include
the accumulation duration so a user cannot confuse a 1-hour total with a
3-hour total.

Every accepted source is:

1. downloaded from ECCC HTTPS or staged from the completed AMQP inbox;
2. size-bounded and hashed;
3. validated as GRIB with matching initialization time, valid time, forecast
   lead, grid, dimensions, parameter, level, and unit;
4. converted to a tiled, compressed Cloud-Optimized GeoTIFF using the reviewed
   conversion key;
5. validated again for raster geometry and registered as an available asset;
6. exposed by the catalogue API and rendered through the existing signed layer
   and tile services.

The web client builds its two-level variable menu from the catalogue. No
hard-coded frontend field list is required: once the first validated COG exists,
the newly registered field and its style become selectable automatically.

## Reproducibility

Relevant implementation files:

- `config/models/gdps.yaml`
- `config/variables/deterministic_atmospheric.yaml`
- `config/variables/deterministic_precipitation.yaml`
- `docker/sarracenia/weatherapp.conf`
- `airflow/dags/eccc_ingestion.py`
- `database/migrations/0026_add_seven_day_gdps_overlays.sql`
- `frontend/src/mapBounds.ts`

Configuration validation expands GDPS to 1,477 expected field/time slots per
cycle. The automated suite asserts the forecast-step semantics, source
availability windows, generated DAG schedule and batch limit, and catalogue
style count. Database migration verification ensures the reviewed SQL state
matches all 26 immutable migrations.

## Operational acceptance record

The first post-deployment manual reconciliation completed from 01:24:00 to
01:26:13 UTC. All 128 downloads, GRIB validations, and COG conversions
succeeded. It published 24 direct wind-speed frames and eight 3-hour
precipitation frames. The first automatically scheduled 15-minute cycle then
started at 01:30:01 UTC and completed successfully at 01:32:08 UTC, proving the
deployed timetable rather than only a manual trigger.

After those two bounded batches, the 2026-07-27 12Z cycle had 48 wind-speed
frames through forecast hour 47 and 16 3-hour precipitation frames through hour
48. Subsequent scheduled reconciliations continue from those slots toward the
configured hour-240 and hour-168 limits without redownloading available COGs.

Browser acceptance selected both new variables from the nested catalogue menu.
For 3-hour precipitation the UI reported one weather layer ready, displayed the
millimetre legend, rendered the raster over the global basemap, and retained the
`YYYY-MM-DD HH:MM:SS` valid-time overlay. A direct tile request returned HTTP
200 with a valid WebP payload.

GDPS raster envelopes include half a 0.15-degree cell outside the geographic
longitude and latitude limits. Those source and catalogue bounds are preserved.
Only the MapLibre camera-fit extent is clamped to Web Mercator's legal
longitude/latitude range, preventing the global overlay selection from
crashing while leaving raster rendering and scientific metadata unchanged.
