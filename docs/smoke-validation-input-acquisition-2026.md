# 2026 smoke-validation input acquisition

## Purpose and frozen interval

This acquisition supports a separately versioned 2026 validation of the
CFFEPS-to-FLEXPART smoke system. It does not modify or backfill the frozen
November 2025 GFAS v1.2 experiment.

The experiment interval is 2026-03-19 through 2026-05-31 UTC, with
2026-03-18 included as a one-day meteorological, fuel-moisture, and fire-input
spin-up. The interval starts with the first consistently available GFAS v1.4.2
portal day and ends at the latest month for which the required monthly burned
area product was catalogued when this collection began on 2026-07-23.

The acquisition design separates three roles:

1. **Model inputs** drive CFFEPS and FLEXPART: GFS meteorology, CWFIS fire
   detections, and CFFDRS fuel-moisture state.
2. **Independent observations** evaluate results: regulatory PM2.5, burned
   area, and satellite aerosol-layer or lidar products.
3. **Intercomparisons** diagnose source behaviour but do not seed the
   candidate: GFAS emission and plume diagnostics.

GFAS values must not be used to calculate the candidate emissions or injection
profile in a GFAS intercomparison. TROPOMI, EarthCARE, AirNow, and EPA AQS
observations must not be assimilated into the run they evaluate.

## Storage and provenance

The immutable data root is:

```text
/Volumes/BigMrStorage/weatherapp_data/weather
```

Large inputs are stored below `raw/<provider>/<product>/...`. Processed CWFIS
GeoJSON and per-day manifests are stored below `processed/nrcan/cwfis`. Range
manifests are stored beside their raw products and below:

```text
derived/smoke/validation/input-archives/
```

Every completed downloader records source URLs or portal paths, byte sizes,
SHA-256 checksums, temporal coverage, and source-reported gaps. Login names,
passwords, cookies, and tokens are never written to data manifests.

## Acquired inputs

### NOAA GFS meteorology

- Interval: 2026-03-18 through 2026-05-31, daily 00 UTC cycles.
- Forecast hours: 0, 3, 6, 9, 12, 15, 18, 21, and 24.
- Grid/product: NOAA public GFS 1.0-degree pressure-level GRIB2 archive.
- Result: 75 cycles, 675 files, 30,326,855,250 bytes.
- Status: complete.

Each cycle has its own immutable manifest. This is the transport meteorology
frozen for this experiment; later GFS cycles are not substituted.

### NRCan CWFIS CFFDRS state

- Fields: FFMC, DMC, and DC.
- Interval requested: 2026-03-18 through 2026-05-31.
- Result: 74 complete daily field sets.
- Source gap: 2026-05-10. The CWFIS WCS returns HTTP 500 for that date while
  adjacent dates return valid GeoTIFFs.
- Status: complete except for one provider gap.

The missing day remains explicit. It may be reconstructed only by a
preregistered CFFDRS state-continuation method; it must not be silently copied
from an adjacent day.

### NRCan CWFIS Fire M3 detections

- Sensor selected during normalization: VIIRS-I, nominal 375 m.
- Interval requested: 2026-03-18 through 2026-05-31.
- Result: 69 daily files containing 96,017 normalized VIIRS features.
- Source gaps: 2026-03-25 through 2026-03-30 inclusive.
- Status: all source-available dates complete.

Raw mixed-sensor CSV files are retained. The processed GeoJSON deterministically
selects and deduplicates VIIRS-I detections while preserving observation time,
coordinates, fire-weather fields, fuel, fire behaviour fields, and estimated
area.

### AirNow regulatory PM2.5

- Product: hourly `HourlyAQObs`.
- Interval: 2026-03-18 through 2026-05-31.
- Result: 1,800 hourly files, 1,801,131,026 bytes, and 355,374 Canadian rows
  flagged as measured PM2.5 with a non-empty concentration.
- Status: complete.

These are preliminary/near-real-time records. They are suitable for the
provisional 2026 analysis and event selection. Publication-quality final
statistics must either use final agency data or quantify changes after replacing
the preliminary observations.

### US EPA AQS PM2.5

- `hourly_88101_2026.zip`: FRM/FEM PM2.5 mass.
- `hourly_88502_2026.zip`: acceptable PM2.5 AQI/speciation mass.
- `aqs_sites.zip`: station metadata.
- Result: three valid ZIP archives, 20,124,857 bytes.
- Status: complete for the current 2026 archive revision.

AQS provides downwind US receptors and a stable independent archive. The 2026
files can be revised by EPA and must be re-frozen before a final paper.

### CAMS GFAS v1.4.2

- Product type: analysis, surface fields.
- Hourly (`001`) fields: `pm2p5fire`, `cofire`, `bcfire`, `apt`, `apb`,
  `injh`, `frpfire`, `crfire`, and `offire`.
- 24-hour rolling-average (`024`) fields: `pm2p5fire`, `cofire`, `bcfire`,
  and `crfire`.
- Interval: 2026-03-19 through 2026-05-31.
- Completeness marker: the portal's per-hour `001` manifest and per-day `024`
  manifest.
- Result: 16,280 GRIB files, 1,850 provider manifests, and 8,774,355,000
  selected-data bytes.
- Status: complete.

Provider manifest sizes are checked before checksums are computed. GFAS remains
an inventory/plume diagnostic and may not seed the candidate source calculation.
The immutable range manifest is:

```text
/Volumes/BigMrStorage/weatherapp_data/weather/derived/smoke/validation/input-archives/gfas-v1.4.2-2026-03-19_2026-05-31/manifest.json
```

### Sentinel-5P TROPOMI aerosol layer height

- Product: OFFL Level-2 `L2__AER_LH`.
- Catalogue selection: product footprint intersects the frozen Canadian
  validation box `[-141, 41, -52, 84]`, and acquisition overlaps
  2026-03-19 through 2026-05-31.
- Catalogue result: 977 unique products, 98,351,152,435 bytes (91.6 GiB).
- Source: the public `meeo-s5p` AWS mirror, with CDSE catalogue identifiers and
  acquisition times retained.
- Status: complete. All 977 products match the catalogue byte sizes and passed
  HDF5/NetCDF4 signature validation; their SHA-256 checksums are frozen in the
  range manifest.

TROPOMI aerosol layer height is an independent column layer-height diagnostic,
not a direct plume-top measurement. Quality flags, cloud filtering, vertical
sensitivity, and the event/overpass collocation operator must be frozen before
matched pairs are extracted.

### NASA MCD64A1 v061 burned area

NASA CMR returned 69 MCD64A1 granules intersecting the Canadian validation box
for March through May 2026. All 69 HDF4 granules were retrieved with a
user-provided Earthdata token, totalling 258,259,753 bytes. Their HDF4
signatures, sizes, and SHA-256 checksums are frozen in:

```text
/Volumes/BigMrStorage/weatherapp_data/weather/raw/nasa/lpdaac/mcd64a1/v061/2026-manifest.json
```

The acquisition can be reproduced with `NASA_EARTHDATA_TOKEN` or
`EARTHDATA_TOKEN` stored in `.env`:

```bash
.venv/bin/python scripts/download_mcd64a1_2026.py \
  --catalogue /Volumes/BigMrStorage/weatherapp_data/weather/raw/catalogues/smoke_validation_2026/mcd64a1-v061-2026-03-19_2026-05-31.json \
  --data-root /Volumes/BigMrStorage/weatherapp_data/weather
```

The token is sent only in the HTTPS authorization header and is not recorded in
the resulting manifest. LP DAAC returns an authorized signed URL on its
CloudFront delivery distribution. The downloader does not forward the bearer
token to that delivery host.

MCD64A1 is the independent burned-area observation used to establish event area
and the weak/moderate/major strata. CWFIS estimated area and GFAS fire-area
fields are not interchangeable with this acceptance input.

## Optional catalogued input still requiring authorization

### EarthCARE ATLID

The public ESA catalogue returned:

- 1,408 `ATL_FM__2A` feature-mask products; and
- 1,408 `ATL_EBD_2A` extinction/backscatter/depolarization products.

The exact STAC responses are archived. The HDF5 assets require ESA EO Sign-In
authorization, which is not present in the project environment. TROPOMI is
being collected as the currently accessible satellite layer-height diagnostic;
EarthCARE should be added for event-matched tracks if authorization is supplied.

### MPLNET

MPLNET MPLCAN site metadata were archived for March, April, and May 2026. The
public service returned no 2026 aerosol-profile downloads for the Canadian
collection at acquisition time. This is recorded as an availability result,
not as a zero-aerosol observation.

## Reproduction commands

Public observations and catalogues:

```bash
.venv/bin/python scripts/download_smoke_validation_observations_2026.py \
  --start 2026-03-19 \
  --end 2026-05-31 \
  --spinup-days 1 \
  --workers 12 \
  --component all \
  --data-root /Volumes/BigMrStorage/weatherapp_data/weather
```

GFAS v1.4.2:

```bash
.venv/bin/python scripts/download_gfas_v142.py \
  --start 2026-03-19 \
  --end 2026-05-31 \
  --phase all \
  --data-root /Volumes/BigMrStorage/weatherapp_data/weather
```

The GFAS command reads only
`ECMWF_DATA_PORTAL_USERNAME` and `ECMWF_DATA_PORTAL_PASSWORD` from `.env` when
they are not already present in the process environment. Values are not echoed.
The optional `--portal-ip` fallback preserves `aux.ecmwf.int` as both the HTTP
Host and TLS SNI name, so certificate validation remains enabled if the local
DNS resolver is temporarily unavailable.

## Collection verification

The completed collection passed the deterministic size-and-manifest audit on
2026-07-23. Its machine-readable result is:

```text
/Volumes/BigMrStorage/weatherapp_data/weather/derived/smoke/validation/input-archives/observations-2026-2026-03-19_2026-05-31/verification.json
```

The audit status is
`complete_with_provider_gaps_and_optional_authorization_gap`. GFS, AirNow, AQS,
GFAS, TROPOMI, MCD64A1, and all frozen catalogue artifacts are complete. CWFIS
is complete for every source-available date, with the explicit gaps listed
above. EarthCARE remains an optional authorization-gated addition; its exact
catalogue selection is frozen locally.

## Acceptance implications

Downloading these files does not itself pass scientific acceptance. Before a
candidate can be accepted:

1. the downloaded MCD64A1 granules must be transformed with the frozen
   event-area operator;
2. the CFFDRS 2026-05-10 gap must be excluded or handled by a preregistered,
   physically defensible state-continuation rule;
3. event-matched TROPOMI and, if available, EarthCARE observation operators and
   quality screens must be frozen before inspecting model skill;
4. smoke-enhancement backgrounds and cross-border station matching must be
   frozen for AirNow/AQS;
5. current-year preliminary observations must be replaced or version-locked
   before publication; and
6. the central and sensitivity FLEXPART runs must use identical frozen inputs
   and archived configurations.

No acceptance lock should be removed merely because the network transfers
completed.
