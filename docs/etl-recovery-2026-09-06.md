# ETL restart audit and recovery

Performed on 2026-09-06 Atlantic time (2026-09-07 UTC) following the Docker
restart. Scope: the 12 configured operational collection/ETL workflows, not
ad-hoc research downloads, scientific experiments, or deletion/retention jobs.

## Inventory and observed results

All 12 DAGs were already unpaused. All 48 configured ECCC weather fields have
both download and processing enabled. No Airflow import errors were present.
The scheduler, API server, DAG processor and triggerer passed health checks.
The Sarracenia subscriber was connected; HTTPS inventory reconciliation was
actively supplying the restart backlog. Its connection alone is not evidence
that a new AMQP message was delivered during this audit.

| Pipeline | Schedule (UTC) | Result during audit |
| --- | --- | --- |
| ECCC City Page forecasts | Every 15 minutes | Recovered automatically; fresh snapshot with 641 regions, none stale |
| ECCC GDPS | Every 15 minutes | Active bounded model-data batch |
| ECCC HRDPS | Hourly, minute 15 | Active batch; hundreds of source downloads completed |
| ECCC RDPS | Hourly, minute 15 | Active batch; hundreds of source downloads completed |
| ECCC RAQDPS | Hourly, minute 15 | Recovery window corrected; fresh manual batch discovered 365 sources |
| ECCC HRDPA | Hourly, minute 15 | Historical missing-source loop repaired; subsequent batch active |
| ECCC RDPA | Hourly, minute 15 | Historical missing-source loop repaired; subsequent batch active |
| ECCC HREPA | Hourly, minute 15 | Historical missing-source loop repaired; retained raw NetCDF files remain recoverable |
| NOAA GFS | 05:15, 11:15, 17:15, 23:15 | Completed September 6 12Z and 18Z cycles: 18 GRIB2 files, 810,725,479 bytes |
| CWFIS hotspots | Daily 07:15 | Completed; latest snapshot September 6, 287 detections at audit time |
| CWFIS CFFDRS | Daily 07:35 | Completed FFMC/DMC/DC grids for September 4–6 |
| Fire-event reconciliation | Daily 08:00 | Rerun after both upstream collections finished; 210 events, 1,624 detections |

The event snapshot retains explicit CFFDRS coverage gaps: 17 events enriched,
193 missing. Collection success does not establish fire-weather coverage for
every event or scientific acceptance of a smoke simulation.

## Fault 1: repeated downloads of unavailable historical sources

After startup, recovery selected incomplete registrations from July. ECCC
returned HTTP 404 for these immutable archive URLs. Retrying them both within
the active batch and during later recovery passes wasted download slots.

The fix classifies a source as `SourceUnavailableError` **only** if an actual
HTTP 404 or 410 is received and the source reference time is older than the
product's publication retry window. Existing local files are checked first.
Recent missing publications, HTTP 401/403/429/5xx, network failures, storage
errors, and validation errors keep their normal failure/retry semantics.

The source remains in PostgreSQL with `status=failed` and its error reason.
It is excluded from blind automatic recovery. A new inventory/AMQP discovery
can explicitly enqueue it again. There is no source-row deletion, fabricated
asset, or change to stored values. A manually restored historical source can
be retried through an explicit recovery operation.

Airflow skips only the unavailable source's processing branch. Validation uses
`none_failed` so other successful downloads in a mixed batch can proceed.
Finalization retains failed-source counts and partial/failed product coverage.
A green DAG therefore means the bounded reconciliation finished, **not** that
every historical source exists or that every model field is available.

Observed historical gaps: HRDPA 36, RDPA 36, HREPA 40 (112 source records).
After deployment, 76 remaining retry/failed task instances were selected by
exact DAG run, task ID and map index, previewed using Airflow's clear API, and
rescheduled once. Other affected instances had already picked up the fix on
their normal retry. Successful and running downloads were not cleared, and no
task was manually marked successful. All 112 absences acquired the explicit
source-error classification.

## Fault 2: RAQDPS publication-window gap

At approximately 02Z, RAQDPS's previous 12Z initialization was older than its
12-hour discovery window, while the new 00Z cycle was not yet available.
Discovery returned no objects even though the previous cycle was still served
by the provider (confirmed from its dated 12Z listing).

The RAQDPS retry window is now 24 hours. Cadence, field selection, batch bounds,
concurrency and retention are unchanged. A regression test verifies recovery
of the previous 12Z cycle when the current cycle's listings return 404.
Manual run ID: `etl_recovery_20260907T0219Z` (an identifier, not a start-time
measurement).

## Dependent processing and operations tooling

Fire-event reconciliation was run again after fresh hotspot and CFFDRS
collections completed, using run ID
`etl_recovery_after_inputs_20260907T0219Z`. This avoids relying on the restart's
initial event job, which overlapped its upstream collectors.

`scripts/run_all_data_collection_dags.sh` now includes City Page forecasts and
CFFDRS, previously omitted. It waits for all 11 source collectors to succeed
before triggering and waiting for fire-event reconciliation. It does not
launch scientific validation, operational smoke forecasts or cleanup jobs.

## Deployment and verification limits

The Airflow image was rebuilt with the source-failure classifier and recovery
SQL, then its scheduler was stopped with a 45-second grace period. The four
long-running Airflow services were recreated from the updated image. DAG and
configuration changes use the existing read-only bind mounts. The web app
stayed available. Database tables and migration history were not changed.

Verification: 238 ingestion/SQL-contract/operations tests passed. The seven
ECCC DAGs imported in the running Airflow environment and their validation
trigger rules were checked. Runtime SQL was checked for the new recovery
exclusion. Production database inspection confirmed the 112 explicit source
gaps and no failed/retrying tasks in the then-active runs.

The large model-data batches were still queued/running during this audit, with
only four tasks executing simultaneously as configured. **This is not a claim
that full model-cycle coverage, every COG, or the entire 72-hour forecast table
has finished populating.** Progress and catalogue completeness must be checked
separately from scheduler health. No scientific acceptance gate was altered;
`flexpart_smoke_operational` remains paused.

Final progress checkpoint: HRDPS had completed 496 downloads and 207 validation
tasks; RDPS had completed 512 downloads and 208 validation tasks; GDPS had
completed 49 downloads and was actively downloading. Other model batches were
scheduled behind them under the shared worker limits. At that checkpoint no
new model COG had yet been published since restart; the fresh City Page
snapshot is a separate product. No failed/retrying tasks were present in the
active runs, and the forecast HTTP endpoint and Airflow health checks passed.
