# Weather data collection and ETL

The [2026-09-06 restart audit](etl-recovery-2026-09-06.md) documents the live
ETL inventory, unavailable-source recovery fix, RAQDPS publication-window
correction, tests, and the distinction between healthy DAGs and complete data.

## ECCC official seven-day regional forecasts

The `eccc_city_forecasts_ingest` DAG collects the official City Page Weather
XML files used by ECCC's public city forecast pages. ECCC documents that these
files are updated at least hourly and can be amended sooner. The DAG therefore
runs every 15 minutes (`*/15 * * * *`) and checks the current and recent issue
directories for all provinces and territories.

Discovery keeps only the newest English issue for each SiteNameCode. A source
file is downloaded only when its issue filename changes; unchanged quarter-hour
checks do not redownload it. The deployment retains one atomic latest XML file
per site rather than an unbounded hourly archive:

```text
raw/eccc/citypage_weather/latest/{PROVINCE}/{SITE_CODE}.xml
```

The parser validates the location, UTC issue time, forecast periods,
coordinates, temperature, forecast relative humidity, POP, and condition. Sites
that contain current observations but no active forecast bulletin are recorded
as unavailable and omitted. Duplicate city sites are collapsed by
province/official region name, with their coordinates averaged and the newest
bulletin used. The normalized product is published atomically at:

```text
processed/eccc/citypage_weather/latest.json
processed/eccc/citypage_weather/manifest.json
```

Precipitation amount is extracted only from an explicit ECCC phrase such as
`Rainfall amount 10 to 20 mm`. A missing amount remains null, except when ECCC
explicitly supplies POP 0, which is represented as `0 mm`. This prevents the
display from presenting an unissued amount as a deterministic zero.

The first live collection on 2026-07-28 discovered 844 sites, retained 840
sites with active bulletins, and normalized them into 641 regional forecasts.
The web API and contour-free map view use this snapshot.

## NRCan CWFIS wildfire hotspots

The `nrcan_cwfis_hotspots_ingest` DAG collects the Canadian Wildland Fire
Information System (CWFIS) Fire M3 daily hotspot file. The operational output is
filtered to `VIIRS-I`, the 375 m active-fire detector carried by the NOAA-20 and
NOAA-21 satellites. MODIS remains valuable for its record back to 2000, but its
active-fire product has a coarser nominal resolution of 1 km.

CWFIS is used instead of the raw NASA FIRMS API for this deployment because it
requires no personal API key, removes known industrial heat sources, and adds
Canadian Forest Fire Danger Rating System context such as Fire Weather Index,
fuel type, rate of spread, fuel consumption, head-fire intensity, and estimated
area. The source includes detections from Canada and the contiguous United
States. A hotspot is a detected thermal anomaly, not a reported wildfire or an
observed fire perimeter; clouds can conceal fires and residual false positives
remain possible.

CWFIS documents Fire M3 as a daily product from May through September. Its
dated files normally finalize shortly after 06:00 UTC, so the DAG runs at
07:15 UTC (`15 7 * * *`) with retries. It targets the previous UTC day and
looks back seven days to recover up to three missing daily files per run.

The untouched source is retained under:

```text
raw/nrcan/cwfis/firem3/YYYY/MM/DD/YYYYMMDD.csv
```

Each source is size-bounded, hashed with SHA-256, schema-checked, row-bounded,
and validated for coordinates and timestamps. The normalized visualization
artifact and its manifest are stored under:

```text
processed/nrcan/cwfis/firem3/YYYY/MM/DD/hotspots_viirs.geojson
processed/nrcan/cwfis/firem3/YYYY/MM/DD/manifest.json
```

`processed/nrcan/cwfis/firem3/latest.geojson` is a stable, map-ready GeoJSON
FeatureCollection for QGIS, MapLibre, or another web map. Its point properties
preserve the CWFIS `fwi`, `fuel`, `ros`, `sfc`, `tfc`, `bfc`, `hfi`, and
`estarea` fields. `latest.json` records its source day and manifest. The weather
API serves the latest validated snapshot at `/api/v1/hotspots`, a dated snapshot
at `/api/v1/hotspots?date=YYYY-MM-DD`, and the archive inventory at
`/api/v1/hotspots/dates`. The web map's observation-date picker uses that
inventory.

Recent CWFIS files are rechecked on every daily discovery pass. If CWFIS changes
the size, ETag, or modification time after an initial publication, the raw file,
normalized GeoJSON, manifest, and latest pointer are replaced atomically. This
matters because satellite swaths and contributing sources can arrive at
different times; geographic coverage and counts can therefore vary sharply
between UTC days.

Trigger the DAG immediately and wait for it:

```bash
./scripts/trigger_hotspot_ingestion.sh
```

Runtime bounds and recovery behavior are configured with the `CWFIS_*`
environment variables documented in `.env.example`.

## NOAA GFS collection for FLEXPART

The `noaa_gfs_ingest` DAG stores complete NOAA/NCEP GFS pressure-grid GRIB2
files for FLEXPART. GFS initializes four times daily, so the DAG runs at
05:15, 11:15, 17:15, and 23:15 UTC—five hours and fifteen minutes after the
00Z, 06Z, 12Z, and 18Z cycles. This delay allows the configured forecast window
to finish publishing.

The default collection is the global 1-degree product for forecast hours
0 through 24 every three hours. It stores nine approximately 40–50 MB files per
cycle under:

```text
raw/noaa/gfs/global_1p00/YYYY/MM/DD/HH/
```

Each file is downloaded atomically, checked against NOAA's reported size,
hashed with SHA-256, validated as GRIB2 with ecCodes, and checked for matching
cycle/valid time, a 360×181 regular latitude-longitude grid, and common
pressure-level U, V, vertical velocity, temperature, and relative humidity.
A cycle becomes complete only when `manifest.json` has been atomically
published. `latest.json` points to the newest completed cycle.

Trigger the DAG immediately and wait for it:

```bash
./scripts/trigger_gfs_ingestion.sh
```

The schedule is intentionally six-hourly rather than daily. Daily collection
would discard three of the four operational analyses and make the wind archive
up to 24 hours stale. Discovery looks back across recent nominal cycles and
recovers missing data; already manifested cycles do not contact NOAA or
redownload files.

Runtime settings are configured with `GFS_*` environment variables documented
in `.env.example`. The 1-degree default adds roughly 1.5–1.8 GB per day. No GFS
retention deletion is enabled: the files remain in the persistent archive until
an explicit retention policy is added.

The deployment creates one parameterless Airflow data-collection DAG for every
supported ECCC forecast, deterministic GRIB2 analysis, or reviewed NetCDF
ensemble analysis:

| Product | DAG ID | Published fields |
|---|---|---|
| GDPS | `eccc_gdps_ingest` | temperature, humidity, wind speed/components/gust, pressure, cloud, rain, snow |
| HRDPS | `eccc_hrdps_ingest` | temperature, humidity, wind components/gust, pressure, cloud |
| RAQDPS | `eccc_raqdps_ingest` | PM2.5, PM10, O3, NO2, SO2 |
| RDPS | `eccc_rdps_ingest` | 2 m air temperature |
| HRDPA | `eccc_hrdpa_ingest` | preliminary/final 6 h and 24 h precipitation |
| RDPA | `eccc_rdpa_ingest` | preliminary/final 6 h and 24 h precipitation |
| HREPA | `eccc_hrepa_ingest` | 6 h control member, 25th percentile, 75th percentile |

## Running collection

The GDPS DAG runs every 15 minutes because its twice-daily forecast is published
as a long sequence of individual files. The other ECCC DAGs run at minute 15 of
every hour in UTC. Scheduled and manual runs have identical behavior and require
no configuration, parameters, run timestamp, or object list. In the Airflow UI,
select a DAG and choose **Trigger DAG**.

To trigger one product from the host:

```bash
./scripts/trigger_ingestion.sh hrdps
```

To trigger every data-collection DAG and wait for all results:

```bash
./scripts/run_all_data_collection_dags.sh
```

Both scripts return a nonzero status when a DAG fails or times out. The default
wait limit is two hours and can be changed with
`INGESTION_WAIT_TIMEOUT_SECONDS`.

The all-collections runner includes City Page forecasts and CWFIS CFFDRS in
addition to the seven model products, GFS and hotspots. After those 11
collectors succeed, it triggers and waits for fire-event reconciliation.

Forecast collection covers every configured lead time in the provider cycle:
HRDPS hours 0–48, RAQDPS 0–72, RDPS 0–84, and GDPS 0–84 hourly plus 87–240
every three hours. Every initialization cycle and all of its configured lead
times remain in the historical archive.

## Automatic discovery and idempotency

At the beginning of every run, the DAG:

1. calculates every candidate model run or analysis valid time in the product
   cadence and configured retry window;
2. asks PostgreSQL which field/time slots already have an available COG using
   the current conversion key;
3. checks that each registered COG and required GDAL sidecar still exists;
4. revives registered sources that have no available asset, including rows left
   by the retired latest-run deletion policy;
5. requests Datamart listings only for missing field/time slots;
6. merges matching files already delivered to the persistent AMQP inbox;
7. registers and processes only newly available or incomplete objects;
8. finalizes each run independently and leaves every visible run and its
   registered raw and processed files intact.

A completely processed model run causes no Datamart listing requests on later
checks. A source with a retained raw file but a missing or obsolete COG reuses
the raw bytes and reruns ETL. Database upserts, deterministic paths, checksums,
and atomic file publication make retries safe.

An actual HTTP 404/410 for a source older than the product's publication retry
window is retained as a failed historical source (`SourceUnavailableError`),
but is not blindly retried in every batch. The missing branch is skipped;
successful downloads still proceed to validation and processing. The catalogue
continues to report its missing coverage. Local retained raw files are reused
before attempting a download, and new provider/inbox discovery can enqueue the
source again. Recent 404s and all transient failures still retry normally.

Discovery is limited by product configuration and its retry window. GDPS uses
128 objects per 15-minute run; the other products default to 512 objects per
hourly run. Candidate cycles are visited newest first. Seventy-five percent of
each batch may be filled by recoverable sources and the remainder stays
available for new discovery, preventing a backlog from indefinitely delaying
fresh data. If the bound is reached, the next scheduled run resumes the
remaining slots. `max_active_runs=1` prevents overlapping runs of the same
product.

Sarracenia remains the low-latency delivery path. It writes completed GRIB2
objects beneath `weatherapp_data/weather/amqp/inbox`; the DAG prefers a matching
inbox file to an HTTPS download. Its subscription rejects unmatched messages,
and inbox discovery processes matching deliveries from every cycle without
deleting an older delivery merely because a newer cycle has arrived. The
inventory reconciliation path ensures a queue created after publication, a
subscriber outage, or a missed notification does not leave the catalogue
permanently incomplete.

## ETL task graph

```text
recover incomplete registrations + discover provider inventory + AMQP inbox
  -> register missing source identities
  -> download or stage source [dynamic map, eccc_downloads pool]
  -> validate GRIB/ecCodes or NetCDF/GDAL metadata [dynamic map]
  -> create and validate COG [dynamic map, cog_transforms pool]
  -> register asset and finalize run visibility
```

Only database IDs and small summaries travel through Airflow XCom. Raster bytes,
listing documents, checksums, and COG metadata remain in persistent storage and
PostgreSQL.

## Historical retention

The application is a historical forecast and analysis archive. Every visible
product run remains in the catalogue, and both its raw GRIB2 sources and
processed COGs are retained. Product configuration sets `retain_forever: true`;
the catalogue-backed age-retention query therefore excludes these payloads even
if the manual maintenance DAG is executed. Rows already marked
`pending_deletion` remain eligible only so an interrupted pre-archive deletion
can converge safely.

The web API exposes run history through a bounded cursor, and the map's
**Load older runs** control retrieves additional pages. Deduplication still
prevents a previously published field/lead slot from being downloaded or
converted again.

Downloads are restricted to HTTPS on `dd.weather.gc.ca`, stream through a
`.part` file, verify size and content length, calculate SHA-256, enforce the
configured free-space floor, and publish atomically. A completed AMQP inbox file
is removed only after its COG has been registered.

GRIB validation checks the binary envelope, message count, initialization or
analysis time, forecast lead, grid, dimensions, and point count. COG processing
selects the configured source band, performs the configured unit conversion,
creates a tiled ZSTD Cloud-Optimized GeoTIFF, validates CRS, bounds, dimensions,
nodata, statistics, and value constraints, then registers it as `available`.

For ECCC temperature GRIB2, GDAL exposes decoded values in Celsius even though
ecCodes describes the encoded unit as Kelvin. Those fields therefore use the
`identity` conversion. Conversion keys are stored in asset provenance so a
configuration change forces regeneration.

HREPA validation selects the reviewed NetCDF variable, checks the validity time,
units, CRS, 2438×1188 grid, and expected band count. The complete 25-member
NetCDF source is retained. Its control member is published as the map layer;
the two percentile files are published as independent 25th- and 75th-percentile
layers.

## Forecast and analysis time identity

Forecast products store model initialization, forecast hour, and valid time.
HRDPA and RDPA store accumulation intervals:

```text
product_run.run_time = analysis valid/end time
product_time.valid_time = interval_end
product_time.forecast_hour = NULL
product_time.interval_start = valid time minus accumulation hours
product_time.interval_end = valid time
product_time.time_kind = accumulation
```

Analysis output paths contain the accumulation duration and preliminary/final
revision, preventing collisions. The web catalogue exposes a run only after its
required display field has an available COG.

The 6-hour and 24-hour labels on deterministic analyses describe accumulation
windows, not a limit on forecast lead time. All configured preliminary/final
analysis variants are collected for every available valid time. HREPA uses the
same interval semantics and exposes its statistic in the variable label.

## Configuration and troubleshooting

Product cadence, discovery window, domains, expected dimensions, retention, and
visibility live in `config/models`. Source selectors, units, conversions,
processing, and display flags live in `config/variables`. The DAG factory
contains no product-specific filename rules.

Validate configuration and ingestion tests after a change:

```bash
uv run weather-ingest --config-root config validate-config
uv run pytest -q tests/ingestion airflow/tests
```

Inspect a run without downloading it when diagnosing provider contents:

```bash
uv run weather-ingest --config-root config inspect-source \
  --product hrdps \
  --run 2026-07-17T12:00:00Z \
  --summary-only
```

The inspection CLI is diagnostic only; normal collection never requires its
output to be copied into an Airflow trigger.

If a DAG reports `no_new_data`, its discovery log distinguishes a genuinely
complete catalogue from missing provider directories. Registered sources
without an available asset are always queued before that result is possible.
Check the mapped task states, the Sarracenia transfer counters, and the
catalogue ingestion-status endpoint. A successful run with mapped download
tasks means new or recovered objects passed through ETL; a successful run with
zero mapped objects means no recoverable or newly published object was
available during that check.
