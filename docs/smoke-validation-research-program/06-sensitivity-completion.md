# W6 research plan: complete the scientific sensitivity matrix

**Blocker:** the high-confidence area case had identical source mass, a
no-deposition causal run was absent, and the one-thread candidate failed  
**Dependency:** W1 representative cohort and W5 fixed model release  
**Estimated active effort:** 1–3 person-weeks plus compute  
**Output:** frozen, verified, scientifically informative sensitivity ensemble

## Research question

Are the central scientific conclusions robust to plausible uncertainty in
burned area/timing, emission factors, vertical injection, particle sampling,
thread scheduling, and wet/dry deposition?

Sensitivity runs quantify uncertainty and attribution. They cannot replace a
failing central result or be selected after inspection to maximize a score.

## Design principles

- Change exactly one declared scientific or numerical factor per candidate,
  except the explicitly designed deposition factorial.
- Inherit all other values from the checksummed central configuration by
  deterministic deep merge.
- Keep event identity fixed across the central and its sensitivities.
- Freeze candidate IDs, config hashes, seeds, particle budgets, comparison
  fields, and interpretation rules before output.
- Require the schema-v2 complete-output verifier for every candidate.
- Report failed/incomplete candidates; do not average only successful runs.

## Required matrix

### 1. Emission-factor uncertainty

Retain the existing low, central, and high versioned registry values for
PM2.5, CO, and BC. Confirm:

- low < central < high for every applicable fuel/phase/species;
- units are g species kg-1 dry fuel;
- literature/source citation and uncertainty rationale exist;
- registry review status is signed; and
- total emitted mass is ordered for every species.

If registry values change after independent review, issue a new registry
version and rerun all three cases.

### 2. Burned-area magnitude and timing

The pilot high-confidence curve was identical to central for retained events,
so it did not bound area uncertainty. Build a prospective event-specific
uncertainty ensemble from independent sources:

- MCD64A1 QA-accepted burn occurrences and burn-date uncertainty;
- VNP64A1 Version 2 burned area;
- versioned agency/NBAC perimeters where available; and
- mapping-window/reliable-observation uncertainty.

Recommended construction:

- **central:** the frozen primary MCD64A1 occurrence operator;
- **low:** intersection or lower credible realization defined from
  high-confidence cross-product support;
- **high:** union or upper credible realization defined from QA-accepted
  cross-product/perimeter support;
- **early/late timing:** shift within reported burn-date uncertainty without
  changing total event area.

The precise intersection/union and conflict rules require emissions-reviewer
approval before values are aggregated. Do not invent a percentage multiplier
only to force a visible difference.

If independent products agree exactly for an event, report a zero-width bound.
The cohort-level matrix is informative only if enough event mass has a
non-zero independent range.

### 3. Vertical injection

Retain:

- central `cffeps_top_beta_v1`; and
- uniform mass from surface to CFFEPS plume top.

Add one physically motivated alternative only if it is defined independently
of the holdout result—for example, a reviewed shape based on published
plume-rise practice. Every profile must conserve identical species mass and
respect the same CFFEPS plume-top diagnostic unless the candidate explicitly
tests plume-top uncertainty.

Evaluate vertical observations and surface PM2.5 for every injection case.
The pilot showed injection was the largest mass-invariant field sensitivity,
so this is a principal scientific uncertainty.

### 4. Particle convergence

Use at least:

- 150,000 particles per species-day;
- 300,000 particles per species-day; and
- optionally 600,000 for a subset if 150k-to-300k convergence is inadequate.

Keep seeds and releases aligned. Evaluate concentration and deposition fields,
observation metrics, active-cell coverage, and runtime. Define convergence
prospectively; do not rely on bitwise equality.

### 5. Thread scheduling

After W5, run the frozen one- and eight-thread central matrix, plus two/four
threads for the former failing member. Every complete field must be finite.
Use the pilot-informed but prospectively signed numerical tolerances from W5.

### 6. Wet/dry deposition factorial

Run four mass-identical candidates:

| Candidate | Wet deposition | Dry deposition |
|---|---:|---:|
| central | on | on |
| no-wet | off | on |
| no-dry | on | off |
| no-deposition | off | off |

Keep settling separate and unchanged unless a distinct settling sensitivity is
preregistered. Verify the species configuration: aerosol and gas deposition
parameters must be scientifically appropriate and documented.

This factorial answers:

- how much mass is removed by each pathway;
- how surface concentration and plume extent respond;
- whether wet/dry effects interact; and
- whether observed surface/vertical bias is sensitive to removal.

Do not call the central cumulative deposition fraction a causal effect.

### 7. Surface background

Retain median background as central and the 20th percentile as sensitivity,
using identical final NAPS records and exclusion samples. Add no alternative
after inspecting performance.

## Outputs and comparisons

For every candidate and common species/day/time/height/grid cell report:

- total field sum;
- signed normalized sum difference;
- normalized L1 difference;
- RMSE and maximum absolute difference;
- active-union Pearson correlation;
- positive, negative, masked, and non-finite counts;
- wet/dry final cumulative mass; and
- wall time, particles, releases, and source mass.

For every external evaluation report:

- central and sensitivity metric values;
- pass/fail status under unchanged thresholds;
- sign of bias;
- event/station influence;
- and whether the qualitative conclusion changed.

Define a qualitative reversal as any of:

- central fail becoming sensitivity pass or vice versa;
- NMB changing sign with meaningful magnitude;
- event/fuel ranking reversing;
- vertical bias direction reversing; or
- source conclusion changing from gross low/high bias to no gross bias.

Every reversal requires a physical explanation and independent review. It
cannot be used to substitute the favourable sensitivity for central.

## Implementation plan

Existing components:

- `python/weather_ingest/smoke_validation_candidate.py`
- `python/weather_ingest/cffeps.py`
- `scripts/run_smoke_validation_candidate.py`
- `scripts/verify_smoke_validation_candidate.py`
- `scripts/compare_smoke_validation_candidates.py`

Add:

```text
python/weather_ingest/burned_area_uncertainty.py
scripts/build_burned_area_sensitivity_curves.py
scripts/build_smoke_sensitivity_matrix.py
scripts/evaluate_smoke_sensitivity_matrix.py
tests/ingestion/test_burned_area_uncertainty.py
tests/ingestion/test_smoke_sensitivity_matrix.py
```

The matrix builder should validate that each one-factor config differs from
central only in its declared paths. It should reject a candidate with an
unregistered difference.

## Required artifacts

```text
sensitivities/
  matrix.yaml
  matrix-freeze.json
  configs/
  area-uncertainty/
  candidates/
  whole-output-verification/
  field-comparison.json
  observation-metric-comparison.json
  qualitative-reversal-assessment.json
  deposition-factorial.json
  review-signoff.json
```

## Definition of done

- Low/central/high emission mass is correctly ordered.
- Burned-area bounds are independently sourced and nontrivial at the cohort
  level, or their zero-width limitation is explicitly accepted by reviewers.
- Central and at least one alternative injection profile are evaluated.
- Particle convergence is demonstrated under a frozen criterion.
- All thread cases pass W5 whole-output criteria.
- All four wet/dry deposition combinations complete with identical source
  mass.
- Median and p20 final-NAPS backgrounds are evaluated.
- Every candidate passes complete-output verification.
- No qualitative reversal remains unexplained.
- The complete matrix and interpretation are independently signed.

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| Area products disagree structurally | Freeze transparent intersection/union rules and report per-event ranges |
| Sensitivity count becomes computationally large | Use one-factor design plus deposition factorial; preserve central cohort |
| A sensitivity appears to “fix” validation | Report it as sensitivity; calibrate separately and revalidate on a new holdout |
| Species deposition settings are questionable | Obtain air-quality review before runs; version species config |
| A candidate has invalid output | Treat as failed; do not omit it from the matrix |

## Execution checklist

- [ ] Obtain independent review of factor and area uncertainty sources.
- [ ] Freeze matrix and candidate config hashes.
- [ ] Validate one-factor differences mechanically.
- [ ] Run source and transport candidates.
- [ ] Run schema-v2 whole-output verifier on every candidate.
- [ ] Generate common-grid field comparisons.
- [ ] Evaluate GFAS, vertical, and NAPS metrics for relevant cases.
- [ ] Complete wet/dry deposition factorial attribution.
- [ ] Identify and review qualitative reversals.
- [ ] Sign the sensitivity evidence package.
