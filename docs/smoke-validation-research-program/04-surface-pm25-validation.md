# W4 research plan: final surface PM2.5 validation

**Blocker:** AirNow was provisional and produced 14 failing pairs; AQS
produced no pairs; no final NAPS result exists  
**Dependency:** W1 surface cohort and W5 frozen model release  
**Estimated active effort:** 2–4 person-weeks  
**Output:** final hourly NAPS smoke-enhancement evaluation

## Research question

Does FLEXPART primary wildfire PM2.5 reproduce independently observed surface
smoke enhancement at Canadian monitoring stations for a representative,
held-out event cohort?

The model does not contain the complete anthropogenic, biogenic, secondary,
and natural aerosol background. The primary comparison is therefore smoke
enhancement, not raw total PM2.5.

## Observation source

Use final or quality-assured hourly National Air Pollution Surveillance
(NAPS) continuous PM2.5 data. ECCC states that continuous particulate
measurements are reported hourly and exposes both pregenerated files and a
query tool in the
[official NAPS open-data record](https://open.canada.ca/data/en/dataset/1b36a356-defd-4813-acea-47bc3abd859b).

Freeze:

- sampling year and archive revision/retrieval date;
- station metadata revision and coordinate history;
- parameter code, instrument/method, unit, and validation flags;
- exact raw files and hashes; and
- confirmation from metadata or NAPS documentation that the chosen archive is
  suitable for final research use.

AirNow may remain a near-real-time secondary diagnostic. It cannot be pooled
with final NAPS values in the primary score.

## Sample design

The frozen formal minimum is 100 valid station-hours. Prospectively target:

- at least 200 candidate station-hours before QA attrition;
- at least 10 stations;
- at least 5 event-days;
- more than one region; and
- no single station or event contributing more than half the pairs.

The additional diversity targets protect against pseudoreplication but do not
replace the formal 100-pair gate. Construct a multi-year surface cohort if one
window cannot support enough observations.

Event selection may consider whether a station lies within the fixed transport
domain and whether final hourly data exist. It may not inspect observed smoke
enhancement or model agreement.

## Station and record eligibility

Freeze the primary rules before extraction:

- finite hourly PM2.5 in µg m-3;
- valid NAPS quality status;
- stable station coordinate for the observation time;
- no disallowed maintenance, calibration, or exceptional-event flag;
- model output covering the station and interval-end hour;
- enough background observations under the frozen rule; and
- model primary PM2.5 at least 0.01 µg m-3, retaining the existing threshold.

Preserve method/instrument identity rather than averaging parallel instruments
after inspecting values. If multiple valid instruments exist, define the
primary monitor-selection rule prospectively and retain the alternatives as a
sensitivity.

## Smoke-background operator

The existing primary background is the same station and same UTC hour median
over ±14 days, with at least seven finite observations. The 20th percentile
using NumPy-linear interpolation remains a frozen sensitivity.

For the new protocol, improve the exclusion ledger without using model output:

1. exclude every candidate source date;
2. exclude hours/days affected by other satellite-detected fires or an
   independently defined smoke-plume product at the station;
3. exclude known local non-wildfire exceptional episodes when supported by
   an external record; and
4. store every excluded background timestamp and reason.

The other-fire screen must be frozen before surface metrics. It should use a
fixed satellite hotspot/plume radius and time relation, or a versioned smoke
polygon product. Do not manually remove high observations because they look
like smoke.

Observed enhancement is:

```text
max(hourly observed PM2.5 - same-hour background, 0)
```

Report the fraction floored at zero and the raw minus background distribution.

## Model observation operator

Primary:

- lowest FLEXPART layer, 0–50 m AGL;
- ng m-3 converted to µg m-3;
- grid cell containing the station;
- model interval-end UTC hour;
- primary wildfire PM2.5 only.

Prospectively freeze these secondary sensitivities:

- bilinear horizontal interpolation;
- first 100 m mass-weighted concentration if output supports it;
- ±1 hour temporal matching;
- median versus 20th-percentile background; and
- inclusion/exclusion of wet and dry deposition from W6.

The containing-cell, exact-hour, median-background result remains primary.

## Metrics and acceptance gates

Formal primary gates:

- pair count at least 100;
- normalized mean bias from -0.30 to 0.30;
- normalized mean absolute error no greater than 0.50; and
- Pearson correlation at least 0.40.

Also report MB, MAE, RMSE, FAC2, mean modelled/observed enhancement, zero-floor
count, station/event counts, and paired distributions.

Estimate uncertainty with a two-level or multiway bootstrap:

- resample fire events;
- resample stations within events; and
- retain hours as a block rather than independent draws.

Report leave-one-event-out and leave-one-station-out influence. These analyses
diagnose robustness and do not change the frozen point-estimate pass/fail rule.

## Attribution analyses

If the central result fails, diagnose without tuning the holdout:

- error by event, station, distance, lead time, and hour since release;
- observed-versus-model plume arrival time;
- surface error versus vertical injection result;
- source-mass bracket and deposition sensitivities;
- background-method sensitivity;
- presence of other fires; and
- meteorological wind-direction/speed error where independent data exist.

Do not rescale emissions to NAPS on the acceptance cohort. Any calibration uses
a separate training cohort and a new held-out assessment.

## Implementation plan

Generalize the existing AirNow/AQS code into a shared final-observation
contract:

```text
python/weather_ingest/naps_pm25.py
python/weather_ingest/surface_smoke_background.py
scripts/download_naps_hourly.py
scripts/build_naps_pm25_pairs.py
scripts/evaluate_surface_pm25.py
tests/ingestion/test_naps_pm25.py
tests/ingestion/test_surface_smoke_background.py
```

Reuse metric definitions from `smoke_evaluation.py`. Retain
`surface_pm25_intercomparison.py` for AirNow/AQS compatibility or refactor it
behind the common contract with regression tests proving identical 2026
results.

The pair builder must emit explicit rejection counts for:

- outside domain;
- missing model hour;
- below model threshold;
- missing/invalid observation;
- insufficient background;
- other-fire/background exclusion;
- unstable station metadata; and
- duplicate/conflicting monitor-hour.

## Required artifacts

```text
evaluation/naps/
  raw-manifest.json
  station-metadata.json
  station-history.json
  background-exclusion-ledger.parquet
  median-background-pairs.csv
  p20-background-pairs.csv
  rejection-ledger.json
  central-evaluation.json
  sensitivity-evaluations/
  clustered-uncertainty.json
  influence-analysis.json
  figures/
```

## Definition of done

- The primary archive is final/quality-assured and checksummed.
- At least 100 valid station-hours survive the frozen operator.
- All four central NAPS gates pass.
- Results span enough events/stations to support the declared scope.
- Clustered uncertainty and influence are reported.
- Median and 20th-percentile backgrounds are both evaluated.
- No NAPS value was used to tune the candidate or select a retained event
  based on performance.
- The air-quality reviewer signs the data, operator, metrics, and
  interpretation.

## Main risks and mitigations

| Risk | Mitigation |
|---|---|
| Final NAPS archive lacks the desired year | Choose an earlier finalized multi-year cohort during W1 |
| Too few station-hours | Increase events/years before output; never weaken the 100-pair gate |
| Background contaminated by other fires | Freeze an independent satellite fire/smoke exclusion ledger |
| One station dominates | Use diversity targets, clustered intervals, and influence analysis |
| Model plume misses a station by one grid cell | Report frozen bilinear sensitivity, but retain containing-cell primary |
| Secondary aerosol causes observed excess | State that the model is primary PM2.5; diagnose rather than silently scale |

## Execution checklist

- [ ] Confirm final NAPS archive revision and station metadata.
- [ ] Build the surface cohort without inspecting model performance.
- [ ] Freeze station, unit, QC, background, and other-fire rules.
- [ ] Target at least 200 pre-QA station-hours.
- [ ] Freeze raw files and hashes.
- [ ] Generate central and p20 pair tables with rejection counts.
- [ ] Evaluate frozen metrics and clustered uncertainty.
- [ ] Run influence and attribution analyses.
- [ ] Obtain air-quality reviewer sign-off.
