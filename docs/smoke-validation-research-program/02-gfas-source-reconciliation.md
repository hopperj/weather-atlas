# W2 research plan: reconcile the GFAS source discrepancy

**Blocker:** PM2.5, CO, and BC showed 96–99% negative bias against the
domain-wide GFAS active union  
**Dependency:** W1 representative source cohort and W5 frozen model release  
**Estimated active effort:** 1–3 person-weeks  
**Output:** coverage-attributed and like-for-like source intercomparison

## Research questions

1. How much of the pilot discrepancy was caused by unequal fire coverage?
2. For the same independently identified fires and dates, do CFFEPS and GFAS
   agree in source magnitude, spatial allocation, timing, and species ratios?
3. If a residual discrepancy remains, is it attributable to burned area, fuel
   consumption, emission factors, satellite-observation fraction, or temporal
   truncation?

GFAS is a modelled inventory, not truth. This workstream resolves an
unexplained gross discrepancy; it does not make GFAS an acceptance-capable
observation.

## Hypotheses

- **H1 coverage:** most domain-wide negative bias results from GFAS fires that
  were absent from the five-event pilot candidate.
- **H2 matched events:** event-matched CFFEPS/GFAS differences are materially
  smaller than the original domain-active-union differences.
- **H3 component attribution:** remaining differences can be decomposed into
  independently measured area, consumed dry matter, emission-factor, species,
  timing, and GFAS observed-fraction terms.

These hypotheses must be recorded before opening the new matched result.

## Required GFAS product

Use one GFAS version throughout a central cohort. Current GFAS v1.4.2 is
documented by CAMS as a global 0.1-degree GRIB1 analysis using MODIS and VIIRS
FRP, with hourly and 24-hour rolling-average emissions. Its PM2.5, CO, and BC
short names are `pm2p5fire`, `cofire`, and `bcfire`. It also supplies
combustion rate, FRP, observed-area fraction, and injection-height diagnostics.
See the
[official GFAS v1.4.2 documentation](https://confluence.ecmwf.int/spaces/CKB/pages/601301528/CAMS+global+biomass+burning+emissions+based+on+fire+radiative+power+GFAS+data+documentation).

Do not combine v1.2, v1.4.1, and v1.4.2 values in one central statistic. If a
historical cohort predates a consistent v1.4.2 reprocessing, use a separately
versioned GFAS cohort and report version effects as a sensitivity.

## Three comparison levels

### Level A — original domain active union

Retain the existing operator unchanged:

- fixed domain chosen before values are opened;
- every positive CFFEPS or GFAS cell-day retained;
- kg m-2 s-1 converted with WGS84 cell area and 86,400 s;
- PM2.5, CO, and BC evaluated separately.

This is the population-coverage audit and must not be replaced by the matched
analysis.

### Level B — preregistered like-for-like event support

Before opening GFAS emissions, construct an event support mask solely from:

- frozen event identities;
- MCD64A1/VNP64A1 burn occurrences and uncertainty;
- the candidate event's active dates; and
- a fixed geolocation allowance justified from product resolution.

Rasterize that support to the 0.1-degree GFAS grid. Assign an event-cell-day
only when it meets the frozen spatial and temporal relation. Ambiguous cells
claimed by multiple events are either excluded from all events or allocated
by a rule frozen before values are read.

Extract both inventories over the identical event-cell-day mask. Do not tune a
buffer until metrics improve. Run at least these variants:

- exact intersecting cells as primary;
- one prespecified resolution/geolocation dilation as sensitivity; and
- event-day totals, which reduce sensitivity to within-fire spatial
  displacement.

### Level C — full eligible-population closure

For the W1 source cohort, report:

```text
GFAS domain mass
  = mass inside independently supported event masks
  + mass outside those masks
  + ambiguous/unassigned mass.
```

Report the analogous CFFEPS closure. The three components must reproduce the
domain total within numerical tolerance. This quantifies rather than merely
asserts the coverage explanation.

## Component attribution

For every event-day and species, retain:

- independent burned area;
- CFFEPS cumulative consumed dry fuel;
- fuel released inside and pending after the model window;
- CFFEPS species emission factor and emitted mass;
- GFAS combustion-rate mass;
- GFAS species mass;
- GFAS observed-area fraction and FRP where available;
- positive-cell count and spatial centroid; and
- UTC timing and rolling-average definition.

Evaluate:

1. area-normalized mass, kg species ha-1;
2. species mass per kg consumed dry matter;
3. CFFEPS-to-GFAS PM2.5/CO and BC/CO ratios;
4. event-day and event-total mass ratios;
5. centroid distance and active-cell overlap; and
6. sensitivity to CFFEPS pending phase mass beyond hour 24.

GFAS FRP, combustion rate, or injection height must not be used to calculate
the candidate being compared.

## Metrics and statistical unit

Retain the frozen grid-cell-day metrics:

- minimum 20 pairs;
- `-0.75 <= NMB <= 2.0`;
- Pearson `R >= 0.30`; and
- `FAC2 >= 0.25`.

Also report event-day and event-total NMB, MAE, geometric mean ratio, median
log ratio, and rank correlation. Use event-block bootstrap intervals so a
single large fire does not masquerade as a large independent sample.

The pair CSV must mark `domain`, `event_mask`, `dilated_mask`, and
`event_total` roles explicitly. Do not pool these roles into one primary
score.

## Implementation plan

Extend rather than replace:

- `scripts/build_gfas_validation_bundle.py`
- `scripts/build_gfas_pairs.py`
- `python/weather_ingest/gfas_intercomparison.py`

Add:

```text
python/weather_ingest/gfas_event_support.py
scripts/build_gfas_event_support.py
scripts/evaluate_gfas_source_attribution.py
tests/ingestion/test_gfas_event_support.py
```

The support builder must not accept a candidate-output path. It should consume
only frozen event/area ledgers and a grid definition. The evaluator then joins
the immutable support mask to candidate and GFAS values.

## Decision rule

The gross discrepancy is considered resolved only if one of these
preregistered outcomes occurs:

1. the full representative eligible-population domain comparison passes every
   unchanged GFAS criterion; or
2. the like-for-like event comparison passes every unchanged criterion, the
   domain failure is closed quantitatively by GFAS mass outside supported
   event masks, and both independent reviewers agree that no substantial
   unexplained matched-event discrepancy remains.

If the matched comparison still fails, do not tune the holdout. Diagnose on a
separate training cohort:

- area operator/perimeter differences;
- fuel-consumption formulation;
- fuel-specific emission factors;
- daily timing and CFFEPS phase tails; and
- GFAS cloud/observation limitations.

Freeze any revised source model, then evaluate it once on a new holdout.

## Required artifacts

```text
evaluation/gfas/
  source-bundle.grib
  source-bundle.manifest.json
  event-support-mask.nc
  event-support-manifest.json
  pairs/domain-active-union/
  pairs/event-support/
  pairs/event-support-dilated/
  event-day-totals.csv
  event-totals.csv
  coverage-closure.json
  component-attribution.parquet
  evaluation.json
  figures/
```

## Definition of done

- The original domain-active-union result is retained.
- The support mask was frozen without reading GFAS emissions or model output.
- Coverage components close to domain totals.
- Matched and domain results are separately reported for all three species.
- At least 20 primary pairs exist.
- The discrepancy satisfies one of the two resolution rules above.
- Both reviewers sign the coverage and source-attribution interpretation.
- No GFAS variable entered candidate generation.

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| GFAS version changes within the cohort | Freeze one version or split cohorts; never pool silently |
| A fixed mask misses displaced GFAS cells | Retain event totals and one prespecified dilation sensitivity |
| Large fires dominate grid statistics | Report event-block uncertainty and event-level results |
| Residual mismatch tempts calibration on holdout | Move all calibration to a separate training cohort |
| Clouds reduce FRP observations | Report GFAS observed fraction and flag low-observation event-days |

## Execution checklist

- [ ] Freeze GFAS version, fields, time convention, and source files.
- [ ] Freeze event masks before emissions are read.
- [ ] Reproduce the original domain-active-union operator.
- [ ] Build exact and prespecified-dilation event support.
- [ ] Generate coverage closure and component table.
- [ ] Evaluate PM2.5, CO, and BC at grid, event-day, and event scales.
- [ ] Block-bootstrap by event.
- [ ] Obtain independent source-attribution review.
- [ ] Record resolved or unresolved status without changing thresholds.
