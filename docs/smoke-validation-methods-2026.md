# Methods record: March–May 2026 CFFEPS–FLEXPART validation

**Experiment:** `gfas-v1.4.2-2026-03-19_2026-05-31`  
**Central candidate:** `march-may-2026-mcd64a1-central-v4`  
**Models:** CFFEPS 4.1 and FLEXPART 11.1  
**Analysis date:** 2026-07-24  
**Purpose:** publication-oriented record of the theory, experimental design,
data transformations, verification, and statistical operators actually used

## 1. Study question and evidential structure

The experiment tests a bottom-up wildfire-smoke chain in which satellite fire
detections establish event identity, satellite burned area establishes daily
area, CWFIS supplies fuel and fire-weather state, CFFEPS estimates fuel
consumption, phase-resolved emissions and plume rise, and FLEXPART transports
the resulting PM2.5, CO, and black-carbon mass.

The source relation can be summarized as

```text
emitted species mass
  = burned area
  × dry fuel consumed per unit area
  × phase- and fuel-specific emission factor.
```

CFFEPS resolves flaming, smouldering, and residual combustion and diagnoses a
plume top from fire energy and atmospheric structure. The adapter distributes
each species over a mass-conserving 12-layer vertical profile. FLEXPART then
represents resolved and turbulent transport, convection, gravitational
settling, wet deposition, and dry deposition with Lagrangian particles.

This decomposition requires separate source, vertical, surface, and numerical
tests. Agreement in one end-to-end quantity cannot establish that every
component is correct because errors in area, fuel consumption, emission
factors, injection, transport, or deposition can compensate.

The design follows the component-wise evaluation rationale used by
[Chen et al. (2019)](https://doi.org/10.5194/gmd-12-3283-2019),
[Ye et al. (2021)](https://doi.org/10.5194/acp-21-14427-2021), and
[Anderson et al. (2024)](https://doi.org/10.5194/gmd-17-7713-2024).
The PM2.5 pilot thresholds use the model-performance benchmarks reported by
[Moran et al. (2026)](https://doi.org/10.5194/gmd-19-4205-2026).

## 2. Preregistration and amendments

The v1 protocol was frozen before the 2026 event reconciliation and before
MCD64A1 pixel decoding. Subsequent amendments were issued after specific
input/interface failures but before output from the amended candidate:

1. [v1 protocol](smoke-validation-protocol-2026.md) fixed the data roles,
   event rules, model configuration, observation operators, metrics, and
   decision rule.
2. [v2](smoke-validation-protocol-2026-v2-amendment.md) changed the MCD64A1
   occurrence key from spatial cell to `(cell, burn date)` after v1 could not
   represent a later mapped reburn at the same coordinate.
3. [v3](smoke-validation-protocol-2026-v3-amendment.md) closed CFFEPS's
   finite-window mass accounting by including combustion-phase fuel still
   queued after hour 24.
4. [v4](smoke-validation-protocol-2026-v4-amendment.md) moved complete
   FFMC/DMC/DC availability checks ahead of candidate generation after one
   area-qualified event encountered official FFMC `NoData`.
5. [v5](smoke-validation-protocol-2026-v5-amendment.md) froze the precise
   AirNow/AQS eligibility, station identity, background, percentile, and
   pairing rules before surface pairs were produced.
6. [v6](smoke-validation-protocol-2026-v6-sensitivities.md) froze six
   one-factor sensitivity candidates before any sensitivity output existed.

These amendments are part of the audit record and must be disclosed in a
paper. Failed predecessor attempts were retained rather than overwritten.

## 3. Study interval and data roles

The source catalogue covers 2026-03-19 through 2026-05-31 UTC; input
meteorology and fire-weather collection begins 2026-03-18. The successful
central candidate contains eight non-contiguous source days: 2026-04-26,
2026-05-05, 2026-05-06, 2026-05-14, 2026-05-16, and 2026-05-23 through
2026-05-25.

| Source | Role |
|---|---|
| NRCan CWFIS VIIRS-I Fire M3 | Canadian event identity, position, and observed FBP fuel |
| Natural Earth Admin 0 v5.1.1 | Point-in-polygon Canadian selection |
| NASA MCD64A1 v061 | Independent burn date, uncertainty, QA, and daily burned area |
| NRCan CWFIS FFMC, DMC, DC | Dated CFFDRS state at each event |
| NOAA GFS 1-degree, 00 UTC cycles | CFFEPS atmospheric profiles and FLEXPART meteorology |
| CAMS GFAS v1.4.2 analysis | Independent-model emission-inventory diagnostic only |
| Sentinel-5P TROPOMI OFFL L2 AER_LH | Diagnostic aerosol vertical comparison |
| AirNow hourly observations | Provisional Canadian surface-PM2.5 comparison |
| US EPA AQS 88101/88502 | Provisional regulatory-source surface comparison |

GFAS, TROPOMI, AirNow, and AQS were not inputs to candidate emissions or
transport. Original filenames, retrieval records, file sizes, source URLs,
and SHA-256 checksums are in the acquisition and pair manifests described in
[the acquisition record](smoke-validation-input-acquisition-2026.md).

## 4. Event construction and independent burned area

CWFIS detections were restricted to Canada by point-in-polygon selection.
Exact duplicate identities were removed. Event reconciliation used
`fire-events-v1`: no more than 36 hours between detections, a 12 km base
distance plus a 1.5 km h-1 spread allowance, compatible first fuel-code
characters, and a frozen ambiguity rule.

The `mcd64a1-event-area-v2` operator treated
`(global sinusoidal row, global sinusoidal column, reported burn date)` as one
burn occurrence. A pixel required land, valid data, a date inside the reliable
mapping interval, and event support within the frozen temporal and spatial
rules. Seeds were detections within 1,500 m; connected growth used
eight-neighbour topology and MCD64A1 burn-date uncertainty plus one day of
event padding. Occurrences claimed by more than one event were excluded from
every claimant. Central and stricter high-confidence daily area curves were
retained.

Events were classified by final independently observed area as weak
`<100 ha`, moderate `100–1,000 ha`, or major `>1,000 ha`. The target was at
least three events in every stratum. All exclusions were made without viewing
candidate performance.

A retained event also required one unique modal supported fuel, a position
inside the transport domain, and finite official FFMC, DMC, and DC values on
every positive-area source day. Fire weather was sampled at the frozen nearest
grid cell and copied into the candidate input manifest.

## 5. CFFEPS source calculation

Each MCD64A1 daily increment was allocated linearly over the 23 active CFFEPS
phase intervals. The allocation was multiplied by `24/23` so that the
interval sum exactly conserved the complete daily area while leaving the
initialization hour free of an invented release.

For every event-day, the portable CFFEPS 4.1 driver used:

- the retained FBP fuel and its fixed mixture parameters;
- the source-day FFMC, DMC, and DC;
- a 40-level atmospheric profile constructed by nearest horizontal GFS
  sampling, linear interpolation between three-hour forecasts, and linear
  interpolation in log pressure vertically;
- a nominal 12:00 UTC detection-time convention; and
- versioned low, central, or high emission factors in
  g species kg-1 dry fuel.

The driver reports fuel released within the 24-hour window and combustion fuel
remaining in the flaming, smouldering, and residual queues. The hard accounting
check was

```text
released phase fuel + final queued phase fuel = cumulative consumed fuel
```

within 5% for every event-day. Only mass actually released inside the 24-hour
window entered FLEXPART. Queued mass was reported but was not shifted to an
earlier time.

The central vertical operator, `cffeps_top_beta_v1`, converted the diagnosed
plume top to normalized fractions in 12 AGL layers and conserved species mass.
This is an adapter profile because CFFEPS 4.1 supplies a plume top rather than
a complete resolved injection distribution.

## 6. FLEXPART transport

PM2.5, CO, and BC were run as separate, independent species-day members. Each
central member used 150,000 particles, a distinct deterministic random seed,
eight OpenMP threads, and a fixed WGS84 output box of
`[-141°, 41°, -52°, 84°]` at 1-degree spacing. Convection, settling, wet
deposition, and dry deposition were enabled.

Each member covered 24 hours and wrote hourly concentrations at nine output
heights, plus cumulative wet- and dry-deposition fields. Six independent
members were scheduled concurrently. Process concurrency changes wall time,
not scientific coupling among members.

## 7. Verification

The independent schema-v2 verifier required:

- 24 completed species-day members and completion markers;
- one checksummed NetCDF output per member;
- 24 hourly fields and nine heights;
- exact release-mass agreement with the normalized emission bundle;
- distinct member seeds and a single executable identity;
- finite, non-negative, non-zero concentration output; and
- finite, non-negative wet- and dry-deposition fields.

The separate CFFEPS audit checked all eight event-day accounting closures.
Area conservation, source bundle validation, input hashes, executable hashes,
options, release files, random seeds, and output hashes were retained.

## 8. Observation operators

### 8.1 GFAS source diagnostic

GFAS v1.4.2 `024` PM2.5, CO, and BC fluxes at 00 UTC were converted from
kg m-2 s-1 to kg grid-cell-1 day-1 with WGS84 geodesic cell area and 86,400 s.
CFFEPS mass was assigned to the same 0.1-degree cells and UTC source days.
The primary sample was the active union: a cell-day was retained if either
inventory was positive after numerical-zero screening. This prevents missing
candidate fires from being hidden. GFAS is another modelled inventory and was
never acceptance-capable.

### 8.2 TROPOMI aerosol height

Pixels required `qa_value >= 0.5`, a finite aerosol mid-height, a centre within
50 km of a source-day event, and a nearest FLEXPART interval end within 90
minutes. TROPOMI height above ground was calculated as its geoid-referenced
`aerosol_mid_height` minus its Copernicus DEM surface altitude.

FLEXPART height was a PM2.5 concentration × layer-thickness weighted mean of
layer midpoint AGL heights in the containing output cell. FLEXPART output
heights were interpreted as upper layer boundaries. TROPOMI is
extinction-weighted while the model statistic is mass-weighted; no aerosol
optical or humidity-growth operator was available. The comparison was
therefore diagnostic. Individual satellite pixels are clustered within
overpasses and fires and were not treated as independent events for inferential
claims.

### 8.3 Surface PM2.5

The model statistic was PM2.5 in the lowest FLEXPART layer (0–50 m AGL) in the
containing cell at the interval-end hour, converted from ng m-3 to µg m-3.
Pairs required model PM2.5 of at least 0.01 µg m-3.

For each monitor-hour, background was the same monitor and same UTC-hour median
over the preceding and following 14 days, excluding all eight source dates and
requiring at least seven values. Observed smoke enhancement was
`max(raw PM2.5 - background, 0)`. A frozen sensitivity used the 20th percentile
with NumPy's linear interpolation.

AirNow records required Canada, `PM25_Measured=1`, `UG/M3`, and an `AQSID`.
AQS records required parameter 88101 or 88502, unit
`Micrograms/cubic meter (LC)`, and an empty qualifier; state, county, site,
parameter, and POC defined a monitor. Current-year AirNow and AQS data were
explicitly provisional.

## 9. Metrics and frozen criteria

For paired model values \(M_i\) and observations \(O_i\):

```text
MB    = mean(M - O)
NMB   = sum(M - O) / sum(O)
MAE   = mean(abs(M - O))
NMAE  = sum(abs(M - O)) / sum(abs(O))
RMSE  = sqrt(mean((M - O)^2))
R     = Pearson correlation(M, O)
FAC2  = fraction satisfying 0.5 <= M/O <= 2, for O > 0
```

GFAS required at least 20 pairs, NMB from -0.75 to 2.0, R at least 0.30,
and FAC2 at least 0.25. TROPOMI required at least 20 pairs, mean bias from
-1,500 to 1,500 m, RMSE no greater than 2,500 m, and R at least 0.30.
Surface PM2.5 required at least 100 pairs, NMB within ±0.30, NMAE no greater
than 0.50, and R at least 0.40. Passing a diagnostic threshold would not make
that product acceptance-capable.

No confidence interval or significance test was preregistered. Metrics are
descriptive pilot statistics; spatial, temporal, event, and satellite-pixel
dependence prevents interpreting the raw pair count as an independent sample
size.

## 10. Sensitivity and attribution design

Six one-factor candidates inherited the complete v4 configuration by
deterministic deep merge:

- low and high emission-factor registry values;
- MCD64A1 high-confidence daily area;
- equal mass in 12 layers from the surface to the CFFEPS plume top;
- 300,000 rather than 150,000 particles per member; and
- one rather than eight OpenMP threads.

Common concentration, wet-deposition, and dry-deposition fields were compared
cell by cell. Summary measures were signed normalized sum difference,
normalized L1 difference, RMSE, maximum absolute difference, active-union
correlation, positivity, and finiteness. Central deposition was integrated
from the final cumulative field of each independent day-member using geodesic
cell area and the NetCDF `1e-12 kg m-2` storage factor.

The deposition calculation is attribution, not a causal enabled-versus-disabled
experiment. A no-deposition candidate requires a new preregistered amendment.

## 11. Reproducibility and publication boundaries

Large artifacts are retained under:

```text
/Volumes/BigMrStorage/weatherapp_data/weather/derived/smoke/validation/experiments/gfas-v1.4.2-2026-03-19_2026-05-31/
```

The human chronology is [the validation log](smoke-validation-log.md), the
numerical findings are in [the results record](smoke-validation-results-2026.md),
and the machine decision is generated by
`scripts/build_smoke_validation_assessment_2026.py`. Tables for a manuscript
should be regenerated from the checksummed JSON/CSV/NetCDF artifacts rather
than copied from an editable spreadsheet.

This experiment can support a statement that the frozen candidate is
computationally reproducible and that its pilot diagnostics have been
evaluated. It cannot support operational scientific validation, a
population-wide Canadian wildfire claim, or removal of the simulation-write
safety lock.

Prospective work to address every blocker is specified in
[the scientific acceptance research program](smoke-validation-research-program/README.md).

## 12. Prospective W3 MISR expansion after the pilot

The March–May 2026 experiment above remains immutable. It did not contain an
acceptance-capable MISR comparison. Subsequent performance-blind cohort
research queried the public MERLIN archive from 2017-01-01 through
2026-07-27 and downloaded every returned MINX plume file intersecting fixed
Canadian-interior screening regions.

The expanded acquisition contains 772 checksummed files, representing 388
band-independent plume families in 78 orbits. Height-blind metadata and
geometry QA selected 386 families. The unchanged provisional post-selection
rule—at least 10 wind-corrected retrievals at or above 250 m AGL—retained 109
observations. Eighty-eight also have complete Fire M3 state/fuel and
independent MCD64A1 burned area, across 37 orbits.

This removes observation availability as the immediate W3 bottleneck but does
not add a MISR performance result to the 2026 pilot. Physical-fire clustering,
independent review, central/reserve selection, historical meteorology, causal
CFFEPS histories, and formal FLEXPART comparisons remain pending. The
publication-ready methods, results language, and limitations are in the
[expanded MISR publication update](smoke-validation-research-program/w3-expanded-misr-publication-update-2026-07-27.md).
