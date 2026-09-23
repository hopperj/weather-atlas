# Interactive FLEXPART app enablement — 2026-07-27

## Scope and scientific-use boundary

The web application now accepts bounded interactive CFFEPS/FLEXPART runs when
`SIMULATION_WRITES_ENABLED=true`. These are research products, not operational
forecasts. While `config/smoke/emission_factors.yaml` remains
`scientific_status: validation_only` and its independent review is pending:

- validation runs remain allowed;
- interactive runs are allowed and carry the warning
  `Research-only run: emission factors are pending independent scientific review`;
- operational runs remain rejected.

This change enables use of the application without representing the unfinished
scientific review as complete.

## Application flow

1. The builder queries fire events for the simulation interval plus a 24-hour
   causal source lookback.
2. Only events with a CFFEPS-supported Fire M3 fuel are offered. Automatic mode
   additionally requires a frozen CWFIS FFMC/DMC/DC state.
3. Admission verifies a checksum-complete GFS cycle, domain/release/particle
   limits, queue capacity, and storage limits.
4. The Airflow worker runs CFFEPS, compiles releases, runs FLEXPART, converts
   outputs to Cloud-Optimized GeoTIFFs, and publishes them to the
   `flexpart_smoke` catalogue.
5. **View results on map** switches to the smoke product and pins the timeline
   to the completed run's exact `requestedAt` catalogue key. This avoids
   silently mixing frames from a different run. Choosing **Now**, **Past 7
   days**, or a custom date range exits the pin and restores best-available
   valid-time selection.

## Verification runs

### Deployment mismatch found

Run `67105417-4940-48fc-b87b-3fd0fe12fb6d` failed during CFFEPS processing with
`CFFEPS portable output lacks finite-window phase queues`. The running Airflow
image contained a 2026-07-22 CFFEPS executable, while the current adapter and
source require the three pending phase-queue columns introduced during the mass
accounting work.

The Linux model stage was rebuilt from the current `cffeps` and `flexpart/src`
trees. Both CFFEPS and FLEXPART executables in the local Airflow image were
replaced with those outputs before repeating the test.

### Successful end-to-end run

Run `5b6c712e-73b9-4d34-a350-77603be2453d` used:

- one CWFIS-backed C2 fire event;
- GFS cycle `2026-07-22T12:00:00Z`;
- `2026-07-22T12:00:00Z` through `2026-07-22T15:00:00Z`;
- domain `[-127.0, 65.9, -126.0, 66.9]` at 1° spacing;
- PM2.5 only;
- 10,000 particles;
- random seed `20260728`.

It completed in 17.02 seconds with zero reported mass-balance residual and:

- 48 release records;
- 20.3240451832 kg primary PM2.5;
- 15 published display assets;
- three resolvable surface-PM2.5 frames at 13:00, 14:00, and 15:00 UTC;
- a successfully served WebP tile from the resolved first frame.

The run completed as `complete_with_warnings`, carrying both the pending-review
warning and the existing “not an official forecast” warning.

### Current-data UI verification

The first browser-submitted current-data attempt,
`67f82feb-38a6-4acd-94e5-295b2aa53ba5`, exposed an admission-control gap: a
10,000-particle request could pass preflight even though the resolved CFFEPS
profile required more FLEXPART release groups than that budget could support.
Admission now uses a conservative upper bound of 36 release groups per
event-hour (three CFFEPS phases across as many as 12 vertical layers), requires
at least 50 particles per release, and multiplies the result by the number of
separately transported species. The API publishes these limits and the builder
raises and displays the scenario-specific minimum before submission.

Run `7041737e-cb34-4467-ba95-2a049e6331c1` then completed successfully through
the web application's smoke-run builder using:

- two CWFIS-backed, CFFEPS-supported fire events;
- GFS cycle `2026-07-27T12:00:00Z`;
- `2026-07-27T12:00:00Z` through `2026-07-28T12:00:00Z`;
- domain `[-121.3, 61.5, -120.2, 62.6]` at 0.5° spacing;
- PM2.5 only;
- 100,000 particles.

The run generated 1,644 release records and 120 published assets, reported zero
mass-balance residual, and completed with the two required research-use
warnings. Selecting **View results on map** was then checked in the running
browser. It selected `wildfire_pm25_surface`, pinned the catalogue to the run's
request time, and displayed exactly 24 hourly frames from 13:00 UTC on July 27
through 12:00 UTC on July 28. The browser reported no console errors.

## Input freshness repair

Scheduled GFS ingestion had stopped after Docker Desktop reported approximately
23.6 GiB free inside the container, despite the host-mounted weather volume
having approximately 3.1 TiB free. The default 50 GiB downloader reserve
therefore produced a false storage rejection. This local deployment now sets
`GFS_MINIMUM_FREE_BYTES=10737418240` (10 GiB). The per-object and per-run byte
limits remain unchanged.

The fire-event reconciliation DAG was also unpaused so newly collected Fire M3
and CWFIS state can enter the smoke builder.

## Automated checks

- Backend smoke API and pipeline tests: 19 passed.
- Frontend builder, API client, and exact-run timeline tests: 9 passed.
- Python Ruff checks: passed.
- Frontend ESLint and production TypeScript/Vite build: passed.
- Airflow DAG import errors after deployment: none.
