# CFFEPS–FLEXPART external scientific validation protocol

**Protocol ID:** `cffeps-flexpart-external-validation-2026-07-22-v1`  
**Status:** frozen before inspection of candidate November 2025 output  
**Frozen:** 2026-07-23 02:12:27 UTC (2026-07-22 23:12:27 ADT)  
**Machine-readable gates:** [`../config/smoke/validation.yaml`](../config/smoke/validation.yaml)  
**Superseded engineering gates:** [`../config/smoke/validation-v1.yaml`](../config/smoke/validation-v1.yaml)

## 1. Purpose and claims

This protocol tests a research smoke-modelling chain consisting of CWFIS fire
observations and fire-weather state, NOAA GFS meteorology, CFFEPS 4.1 emissions
and plume rise, and FLEXPART 11.1 transport. It is designed to answer four
separate questions:

1. Are the source emissions plausible in magnitude, timing, species partition,
   and spatial allocation relative to an established independent inventory?
2. Does the transported aerosol vertical distribution agree with satellite
   plume-height observations at overpass time?
3. Does transported primary wildfire PM2.5 reproduce observed smoke
   enhancements at Canadian surface stations?
4. Are the conclusions robust to important source, injection, and transport
   uncertainties?

Passing software regression, mass conservation, or a GFAS comparison alone is
not external scientific validation. GFAS is another modelled fire inventory,
not ground truth. The operational feature flags remain disabled until all
acceptance-capable tests, independent review, and scheduled-run gates pass.

## 2. Scientific basis

CFFEPS uses a bottom-up relationship in which emissions are driven by burned
area, available fuel, combustion completeness/fuel consumption, combustion
phase, and species emission factors. In compact notation,

```text
species mass = burned area × dry fuel consumed per area × emission factor
```

The phase-resolved implementation calculates this separately for flaming,
smouldering, and residual combustion. CFFEPS also estimates plume-top height
from fire energy and atmospheric stability. The application converts the plume
top to a normalized 12-layer release distribution and conserves species mass
when generating FLEXPART releases. FLEXPART then represents turbulent and
resolved transport, convection, settling, wet deposition, and dry deposition
with Lagrangian particles.

This decomposition motivates component-wise tests. A correct downwind PM2.5
value can result from compensating errors in fire area, fuel consumption,
injection, transport, or deposition. Conversely, a source model can be sound
while a transport error produces a poor station comparison. Results will
therefore be reported by component before any end-to-end conclusion.

The protocol follows precedents established by:

- [Chen et al. (2019)](https://doi.org/10.5194/gmd-12-3283-2019), who evaluated
  FireWork–CFFEPS against North American surface air-quality networks;
- [Ye et al. (2021)](https://doi.org/10.5194/acp-21-14427-2021), who compared
  12 smoke forecast systems across emissions, column aerosol, surface PM2.5,
  and vertical plume structure;
- [Anderson et al. (2024)](https://doi.org/10.5194/gmd-17-7713-2024), who
  intercompared GFFEPS with GFAS, GFED, and FINN and showed that inventory
  differences are expected rather than proof that one inventory is truth;
- [Moran et al. (2026)](https://doi.org/10.5194/gmd-19-4205-2026), whose
  FireWork comparison reports the commonly used PM2.5 acceptability benchmarks
  NMB within ±0.30, NMAE no greater than 0.50, and correlation at least 0.40;
- [Voshtani et al. (2025)](https://doi.org/10.5194/acp-25-15527-2025), who
  constrained North American fire CO with TROPOMI and TCCON and demonstrated
  why satellite CO provides information independent of a prior inventory.

## 3. Model and software identity

The candidate must record hashes of every executable and source archive, not
only a human-readable version:

| Component | Versioned source | Required identity |
|---|---|---|
| CFFEPS | official v4.1 archive plus the portable-driver patch set | source archive, patch-set, executable, configuration, and profile hashes |
| FLEXPART | Debian mirror of the upstream `flexpart_11.1.orig.tar.gz` release | source archive, local patch-set, executable, options, meteorology, and release hashes |
| Python adapter | working-tree source files | per-file SHA-256 and Python/dependency versions |
| Evaluation | this protocol and threshold YAML | protocol and threshold SHA-256 |

The upstream FLEXPART 11.1 archive still prints an internal `Version 11.0
(2023-07-11)` runtime banner. This known upstream metadata discrepancy must be
reported; the archive checksum is the authoritative release identity.

## 4. Frozen November 2025 experiment

The first experiment window is 2025-11-10 through 2025-12-01 inclusive. The
meteorological spin-up begins 2025-11-09. Its current input archive contains:

| Input | Coverage | Frozen evidence |
|---|---|---|
| NOAA GFS 1-degree analyses/forecasts | 23 daily 00 UTC cycles; 207 GRIB2 files | 9,171,057,552 bytes plus per-cycle manifests |
| CWFIS FFMC/DMC/DC | 2025-11-09 through 2025-12-01 | 69 GeoTIFFs; 2,170,597,791 bytes |
| CWFIS annual hotspots | 2025-11-09 through 2025-12-01 selection | 44,812 detections; selection SHA-256 `3b78e1446bfe95f601c59c2bc4e42b6d93179964ed77832494c33adbd2aa9418` |
| CAMS GFAS | v1.2 daily analysis, 2025-11-10 through 2025-12-01 | 396 GRIB1 messages; SHA-256 `f243c964a016f95f86932ce8ba00b66dc79c0ed6cabd95bb2be8ad37eb49821b` |

The authoritative archive manifest is outside the source tree at
`/Volumes/BigMrStorage/weatherapp_data/weather/derived/smoke/validation/input-archives/gfas-v1.2-2025-11-10_2025-12-01/manifest.json`.

The annual CWFIS hotspot archive does **not** contain `estarea`. The CWFIS 2025
final buffered-hotspot perimeter archive contains no event whose `LASTDATE` is
later than 2025-11-07. Consequently, no event in the experiment interval is yet eligible for a
scientific emissions comparison under this protocol. The experiment may be
used for adapter rehearsal, but an acceptance result requires independently
derived daily burned area. Preferred sources are MCD64A1 v6.1 burn-date pixels
or a versioned agency perimeter progression. Detection count, GFAS FRP, and
GFAS emissions are prohibited area substitutes for the primary comparison.

NASA CMR lists 46 MCD64A1 v6.1 granules intersecting Canada for November and
December 2025. Their LP DAAC objects require NASA Earthdata authorization. The
anonymous Planetary Computer mirror currently has no items after July 2025, so
it cannot substitute for the protected archive for this experiment.

## 5. Event eligibility and stratification

An event is eligible only if all of the following are available:

- a stable fire-event identity and location;
- an independent cumulative or daily burned-area time series with source QA;
- valid fuel type and required FBP mixture parameters;
- FFMC, DMC, and DC sampled from dated source grids or explicitly reviewed
  station calculations;
- a complete meteorological profile over the release and transport interval;
- at least one applicable independent comparison source; and
- no unresolved industrial-source, duplicate-event, or time-zone ambiguity.

Events will be selected from inputs without viewing candidate performance and
stratified by final burned area: weak `<100 ha`, moderate `100–1,000 ha`, and
major `>1,000 ha`. The target minimum is three events in each stratum, spanning
at least two Canadian ecozones and two fuel families. If a dataset cannot meet
that design, the shortfall is reported and no population-wide claim is made.

All attempted events remain in the ledger. Exclusions require a machine-readable
reason; a poor-performing event is never removed because of its result.

## 6. Observation operators and matched pairs

### 6.1 GFAS inventory intercomparison

For PM2.5, CO, and BC separately, convert GFAS daily mean flux from
`kg m-2 s-1` to kilograms per 0.1-degree grid-cell day using geodesic cell area
and 86,400 seconds. Aggregate CFFEPS emissions to the same UTC day and grid.
The primary pair unit is an active-union grid-cell day: retain a cell-day when
either inventory is positive after numerical-zero screening. Also report
domain-day totals so spatial displacement cannot cancel mass bias.

The WGS84 evaluation bounding box is selected from the experiment design before
pair extraction, stored in the pair manifest, and must contain every selected
CFFEPS source. All supported fire events inside that domain and interval are
included; the box may not be tightened after viewing model or GFAS values.

GFAS FRP, emission flux, and injection height must not enter the candidate's
source calculation. GFAS plume variables (`injh`, `apt`, and `apb`) are
secondary diagnostics only. A GFAS gate can pass its preregistered criteria but
`counts_toward_acceptance` remains false.

### 6.2 MISR plume height

Match each quality-screened MISR plume polygon to an eligible event and overpass
time. Convert observed and model heights to metres above ground level with a
common terrain reference. The primary model quantity is derived from the
FLEXPART aerosol mass profile intersecting the observed plume footprint at
overpass time. Report both a mass-weighted mean height and a robust plume-top
operator, defined before extraction as the altitude below which 95% of column
mass resides. Raw CFFEPS plume top is reported separately to isolate source
injection from subsequent transport.

### 6.3 NAPS PM2.5 smoke enhancement

Sample FLEXPART primary wildfire PM2.5 at each NAPS station and UTC hour using
the model cell containing the station and the model interval end-time. NAPS
observes total ambient PM2.5, while this candidate omits anthropogenic and
biogenic background and secondary aerosol. Therefore, the observed comparison
quantity is smoke enhancement rather than raw total PM2.5.

For each station-event pair, estimate a local diurnal background from non-smoke
days within ±14 days, using the median for the same UTC hour after excluding
hours affected by the candidate event and other satellite-detected fires.
Observed enhancement is `max(observed total - background, 0)`. A sensitivity
case uses the 20th percentile background. Missing observations remain missing,
never zero. Report raw-total comparisons only as explicitly biased diagnostics.

## 7. Metrics

For paired observations `O_i` and model values `M_i`:

```text
MB    = mean(M_i - O_i)
NMB   = sum(M_i - O_i) / sum(O_i)
MAE   = mean(abs(M_i - O_i))
NMAE  = sum(abs(M_i - O_i)) / sum(abs(O_i))
RMSE  = sqrt(mean((M_i - O_i)^2))
R     = Pearson correlation(M, O)
FAC2  = fraction with 0.5 <= M_i / O_i <= 2, for O_i > 0
```

Normalized metrics are undefined when their denominator is zero and fail a
criterion rather than being silently reported as zero. Pair count and the
positive-observation count used by FAC2 are always reported.

The frozen v2 gates are:

| Assessment | Role | Minimum sample | Criteria |
|---|---|---:|---|
| GFAS grid-cell days | diagnostic only | 20 | `-0.75 <= NMB <= 2.0`, `R >= 0.30`, `FAC2 >= 0.25` |
| MISR heights | independent acceptance | 10 | `abs(MB) <= 1,000 m`, `RMSE <= 2,000 m`, `R >= 0.40` |
| NAPS smoke enhancement | independent acceptance | 100 station-hours | `abs(NMB) <= 0.30`, `NMAE <= 0.50`, `R >= 0.40` |

The NAPS limits are literature benchmarks for total PM2.5 model evaluation,
transferred here as a preregistered first gate after constructing a like-for-like
smoke enhancement. The MISR limits are study-specific pilot gates, not claimed
community standards; their rationale and sensitivity must be reported.

## 8. Uncertainty and sensitivity design

The central run is evaluated first using the frozen thresholds. Without changing
event inclusion, repeat at minimum:

- low and high species emission factors from the versioned registry;
- low and high defensible burned-area realizations from source uncertainty;
- alternative vertical injection profiles that conserve identical mass;
- at least two particle counts to quantify Monte Carlo stability;
- one- and multi-thread runs to quantify scheduling-dependent stochastic noise;
- NAPS median and 20th-percentile background definitions; and
- with and without wet/dry deposition for attribution, not as candidate tuning.

Sensitivity runs cannot replace the central result. Parameter choices may not
be selected after inspection to maximize score. Any later calibration uses a
separate training period and must be tested on held-out events.

## 9. Reproducibility and record keeping

Every run or attempted run must preserve:

- source URLs, retrieval timestamps, licences, original filenames, byte sizes,
  and SHA-256 values;
- spatial/temporal coverage, variable names, units, QA flags, and transformations;
- event-selection query and all inclusion/exclusion reasons;
- CFFEPS namelists, atmospheric profiles, emissions, vertical fractions, logs,
  and executable hash;
- FLEXPART options, releases, species files, meteorology manifest, environment,
  seeds, thread count, logs, and complete scientific outputs;
- pair-builder version, observation-operator settings, pair CSV, pair manifest,
  thresholds, report, and checksums; and
- exact commands, wall times, warnings, failures, and deviations from protocol.

The living chronology is [`smoke-validation-log.md`](smoke-validation-log.md).
Machine-readable experiment outputs belong under
`derived/smoke/validation/experiments/<experiment-id>/`; large raw data remain
outside the repository. Publication tables and figures must be reproducible from
those immutable artifacts, never from manually edited spreadsheets.

## 10. Decision rule and amendment policy

Scientific acceptance requires all of the following:

1. software regression and mass-conservation gates remain green;
2. at least one eligible weak, moderate, and major event is represented, with
   the full target design or its limitation explicitly stated;
3. MISR and NAPS acceptance-capable central tests meet all frozen criteria;
4. GFAS diagnostics show no unexplained gross source discrepancy;
5. sensitivity results do not reverse the qualitative conclusion without a
   documented explanation;
6. a wildfire-emissions scientist and an air-quality scientist review and sign
   the registry and methods; and
7. at least four scheduled validation runs finish inside their cycle window.

Failure of a gate is a result, not permission to change the threshold. Protocol
changes require a new protocol ID, a new threshold version, a dated amendment
describing why the change was made, and clear separation of results generated
before and after the amendment. Exploratory analyses are welcome but must be
labelled exploratory and cannot be retroactively called preregistered.
