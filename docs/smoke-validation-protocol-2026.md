# March–May 2026 CFFEPS–FLEXPART validation protocol

**Protocol ID:** `cffeps-flexpart-external-validation-2026-07-24-v1`  
**Status:** frozen before 2026 event reconciliation or MCD64A1 pixel decoding  
**Frozen:** 2026-07-24 12:41:53 UTC (09:41:53 ADT)  
**Machine-readable gates:** [`../config/smoke/validation_2026.yaml`](../config/smoke/validation_2026.yaml)  
**Candidate configuration:** [`../config/smoke/validation_candidate_2026.yaml`](../config/smoke/validation_candidate_2026.yaml)

## Purpose and separation from the 2025 experiment

This is a separately versioned validation of the CWFIS–CFFEPS 4.1–FLEXPART
11.1 smoke chain for 2026-03-19 through 2026-05-31 UTC. It does not amend,
replace, or pool results from the frozen November 2025 experiment. The
meteorological and fire-state input interval begins on 2026-03-18.

The central candidate must be generated without using GFAS, TROPOMI, AirNow,
or AQS values. Those products are opened only after event identity, burned
area, fuel, fire weather, candidate configuration, and observation operators
are frozen.

## Frozen input roles

- NOAA GFS 1-degree 00 UTC cycles provide transport meteorology.
- NRCan CWFIS VIIRS-I Fire M3 points define candidate event identity and
  observed fuel. The source does not publish files for 2026-03-25 through
  2026-03-30; no detections are imputed.
- NRCan CWFIS FFMC, DMC, and DC provide dated fire-weather state.
- NASA MCD64A1 v061 Burn Date, Burn Date Uncertainty, and QA pixels provide
  independent daily burned area.
- CAMS GFAS v1.4.2 is an inventory/plume diagnostic and never seeds the
  candidate.
- TROPOMI OFFL L2 AER_LH is a diagnostic vertical observation.
- AirNow and the current 2026 AQS archives are provisional surface tests.

All files are identified by the acquisition manifests documented in
[`smoke-validation-input-acquisition-2026.md`](smoke-validation-input-acquisition-2026.md).

## Country and event selection

Daily Fire M3 files have coordinates but no country field. Canadian detections
are selected by point-in-polygon against the `ADMIN_A3=CAN` geometry in Natural
Earth Admin 0 Countries 1:10m version 5.1.1. The zip archive, extracted Canada
geometry, source URL, size, and SHA-256 are frozen with the event ledger.
Natural Earth uses de-facto boundaries; that cartographic convention is a
declared limitation.

Only VIIRS-I detections with a supported FBP fuel enter reconciliation.
Exact duplicate identities are removed. Events use unchanged `fire-events-v1`
rules: no more than 36 hours between detections, 12 km base distance,
1.5 km h-1 spread allowance, compatible first fuel-code character, and the
frozen ambiguity rule. Every included and excluded row receives a reason.

## Burned-area observation operator

The unchanged `mcd64a1-event-area-v1` operator and configuration SHA-256
`aefc9a786761fd4e4cb3fdaa252788844d2af3b3ae0ea65ba2938632d3bf89b9`
are reused. This choice was made before opening 2026 Burn Date values.

The operator requires land, valid data, a burn date inside the reliable
mapping interval, and at least one high-confidence pixel. A 1,500 m detection
seed, burn-date uncertainty, one-day event padding, and eight-connected scar
growth are used. Pixels claimed by more than one event are excluded from every
claimant. Central and high-confidence area curves are retained. Events are
stratified as weak `<100 ha`, moderate `100–1,000 ha`, and major `>1,000 ha`;
the target is at least three events in each stratum.

## Candidate source and transport

All area-qualified events with one unique modal supported fuel are included.
No event may be removed after inspecting performance. Each MCD64A1 daily area
increment is allocated linearly across active CFFEPS intervals, normalized to
conserve the complete daily total. Central versioned emission factors produce
PM2.5, CO, and black-carbon mass in 12 injection layers.

CWFIS state is sampled from the nearest valid grid cell on the source date.
The sole missing CFFDRS day, 2026-05-10, is reconstructed only if required by
an eligible source increment: each FFMC/DMC/DC value is the arithmetic midpoint
of the same-location values from May 9 and May 11. The reconstruction is
flagged in every affected event-day manifest. This is an interpolation
sensitivity and not an observed analysis; affected results must also be
reported separately.

FLEXPART runs PM2.5, CO, and BC as isolated 24-hour members on the WGS84 box
`[-141, 41, -52, 84]` at 1-degree spacing. Each species-day uses 150,000
particles, distinct deterministic seeds, eight OpenMP threads, convection,
settling, wet deposition, and dry deposition. Outputs are hourly. All source
events lie inside the fixed box; it is not tightened after viewing results.

## Frozen observation operators

### GFAS

The primary diagnostic uses the v1.4.2 24-hour rolling-average `024` PM2.5,
CO, and BC fields at 00 UTC. Flux is converted from kg m-2 s-1 to cell-day
kilograms using WGS84 cell area and 86,400 seconds. CFFEPS is aggregated to
the same cell-day. The active union is retained so absent candidate fires are
not hidden. The existing diagnostic thresholds are unchanged and cannot count
toward acceptance.

### TROPOMI aerosol height

Pixels require `qa_value >= 0.5`, finite `aerosol_mid_height`, a centre within
50 km of an eligible event, an overpass on a source day, and a model output
within 90 minutes. The observed value is metres above local ground. The model
value is PM2.5 mass-weighted mean height in the containing FLEXPART cell.

TROPOMI describes an extinction-weighted average height of an assumed uniform
layer, whereas FLEXPART supplies mass concentration. No aerosol optical model
or humidity growth is available. Therefore this is a declared diagnostic,
not an acceptance-capable substitute for lidar or MISR plume profiles.

### Surface PM2.5

The model value is FLEXPART PM2.5 at the 50 m output level, converted from
ng m-3 to µg m-3, at the containing grid cell and interval-end hour. The
observed value is non-negative smoke enhancement: raw hourly PM2.5 minus the
same-station, same-UTC-hour median from the ±14-day window after excluding all
candidate source days. The 20th percentile is a frozen sensitivity.
Missing values remain missing; negative observed enhancements are set to zero.
Pairs require model smoke of at least 0.01 µg m-3.

AirNow is near-real-time and preliminary. AQS is regulatory-source data, but
the current-year bulk files may still be revised. Both tests are reported as
provisional and cannot independently unlock production until a final archive
revision is frozen and reviewed.

## Metrics and gates

Metrics retain their definitions from the parent protocol: mean bias, NMB,
MAE, NMAE, RMSE, Pearson correlation, and FAC2. Undefined normalized
denominators fail rather than being reported as zero. The exact pilot gates
are in `validation_2026.yaml`; passing a diagnostic gate does not make it
acceptance-capable.

## Sensitivity and decision rule

At minimum, publication claims require the central result, low/high emission
factors, high-confidence area, alternate injection, particle-count stability,
thread-count stability, median/20th-percentile surface backgrounds, and
deposition attribution. The event set is unchanged across sensitivities.

Scientific acceptance additionally requires the weak/moderate/major population
design, a resolved GFAS gross-discrepancy check, an acceptance-capable vertical
profile observation, final surface observations, four scheduled-cycle runs,
and independent emissions and air-quality review. Failure or insufficient
sample size is a result and never permission to tune thresholds or exclude a
poor-performing event.

## Reproducibility record

Every command, warning, failure, input/output checksum, executable identity,
environment, random seed, thread count, event exclusion, reconstructed input,
pairing decision, metric, and limitation is stored below:

```text
/Volumes/BigMrStorage/weatherapp_data/weather/derived/smoke/validation/experiments/gfas-v1.4.2-2026-03-19_2026-05-31/
```

The human-readable chronology remains
[`smoke-validation-log.md`](smoke-validation-log.md). Results intended for a
paper must be generated from immutable manifests and scripts, not manually
edited tables.
