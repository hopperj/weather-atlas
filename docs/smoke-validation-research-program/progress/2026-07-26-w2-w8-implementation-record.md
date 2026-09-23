# W2–W8 implementation and Phase 0 readiness record

**Program:** `cffeps-flexpart-acceptance-program-v1`  
**Protocol:** `cffeps-flexpart-successor-holdout-2026-v1`  
**Central candidate:** `w1-2023-successor-central-v1`  
**Work started:** 2026-07-26 America/Halifax  
**Artifact freeze completed:** 2026-07-27 UTC  
**Scientific status:** not accepted; holdout execution remains blocked  
**Production status:** `SIMULATION_WRITES_ENABLED` remains false

## 1. Scope and scientific firewall

This work implemented the executable portions of the remaining W2, W3, W4,
W6, W7, and W8 plan and built a machine-checkable Phase 0 package. It did not
run the held-out CFFEPS/FLEXPART candidates because two prospective
prerequisites remain false:

1. none of the 16 W3 overpasses yet has a complete, frozen fire-state and
   meteorological input assignment; and
2. the two required independent human reviewers have not approved prospective
   execution.

No GFAS emission magnitude, MISR plume height, NAPS concentration, or candidate
model output was used to select the retained source cohort or tune an
operator. The final cohort freeze records:

- `candidate_output_accessed = false`;
- `model_performance_used = false`;
- `observed_or_reference_magnitudes_used_for_selection = false`; and
- `holdout_output_opened = false`.

The failed and superseded regression attempts described below were preserved.
They are engineering tests on the public FLEXPART compact sample, not holdout
validation results.

## 2. Implemented software

### 2.1 Common contracts and statistics

The implementation now has common immutable observation and pair contracts,
rejection records, checksums, event-block bootstrap, event/station multiway
bootstrap, and input/output identity checks. The relevant modules are:

- `python/weather_ingest/smoke_validation_contracts.py`;
- `python/weather_ingest/gfas_intercomparison.py`;
- `python/weather_ingest/vertical_plume_observations.py`; and
- `python/weather_ingest/surface_pm25_intercomparison.py`.

The vertical evaluator uses the fire-overpass as the resampling block. It
reports the primary mass-weighted AGL comparison and the preregistered
95%-column-mass upper-height diagnostic. The surface evaluator resamples both
event and station dependence rather than treating station-hours as
independent.

### 2.2 W2 source reconciliation

`gfas_event_support.py` and the related builder/evaluator implement:

- exact independent event-cell-day masks;
- a one-cell Chebyshev dilation sensitivity;
- ambiguity exclusion;
- active-union, event-day, and event-total comparisons;
- PM2.5, CO, and BC statistics; and
- mass-closure/component-attribution records.

The support builder accepts frozen event and independent burned-area records,
not candidate output. The frozen mask contains:

- 77 dates;
- 15 retained/reserve events;
- 193 exact event-cell-day records;
- 1,476 dilated records;
- 0 ambiguous exact records; and
- 0 ambiguous dilated records.

The compact NetCDF mask is 36,267 bytes and has SHA-256
`66d75d32b8131ff369cb5148422059e74b7e30fb08636ee86bcbc8445b3a8e5b`.

### 2.3 W3 vertical observations

The MISR MINX and CALIOP adapters, source-neutral overpass record, FLEXPART
polygon/time/height operator, rejection ledger, and evaluation statistics are
implemented. The observation operator remains blind to model height until the
observation ledger is frozen.

The readiness audit is intentionally blocking:

- prospective overpasses: 16;
- ready overpasses: 0;
- formal minimum: 10;
- input-invalid exclusions applied: 0; and
- status: `blocked`.

The 16 records are pending explicit fire assignment, independent area,
fuel/CFFDRS state, and sufficient transport meteorology. This is missing input,
not a failed plume-height result; model height output has not been opened.

### 2.4 W4 surface PM2.5

The NAPS archive reader, station-method freeze, coordinate history, background
operator, pair builder, rejection ledger, central/p20 evaluation, influence
analysis, and event/station bootstrap are implemented.

The frozen final NAPS inventory contains:

- 231 stations;
- 1,853,610 valid full-year station-hours;
- 724,810 invalid or missing hours;
- units of `ug m-3`; and
- hour-ending local-standard-time values converted to UTC.

The primary method is selected per station using a performance-blind rule.
The background-exclusion schema is frozen, but its event-specific contents
remain a template. Independent review must approve the exclusions before
observed enhancements are calculated.

### 2.5 W6 sensitivity matrix

The matrix builder deep-merges every member from the central configuration,
records changed configuration paths, rejects undeclared differences, and
parses every generated member through the production candidate schema.

The frozen 16-member matrix contains:

- central;
- emission-factor low/high;
- independent burned-area low/high;
- independently observed early/late area timing;
- uniform vertical injection;
- 300,000-particle convergence;
- one-, two-, and four-thread checks in addition to the central thread case;
- wet+dry, no-wet, no-dry, and no-deposition cases with gravitational settling
  fixed on; and
- p20 surface-background sensitivity.

#### Independent burned-area construction

The area bounds are not arbitrary percentage multipliers. Each event uses the
lowest, central, and highest positive total from independent MCD64A1,
VNP64A1, and provider products while retaining the internally coherent daily
timing of the selected product. A provider perimeter that covers more than
one event is allocated by the events' MCD64A1 event-total weights so its area
is not double-counted.

For the nine retained events the cohort totals are:

| Bound | Area (ha) |
|---|---:|
| Low | 2,339.779538930206 |
| Central | 4,743.956679849317 |
| High | 2,622,099.80234 |

The very large high bound is preserved rather than clipped. It originates in
an independent provider perimeter and therefore exposes a real definition/
attribution disagreement. It must be assessed for scientific defensibility
by the independent reviewers; a favourable central result may not be made
less sensitive by silently replacing it.

### 2.6 W7 review controls

The review package now requires two distinct roles:

- `emissions_plume_science`; and
- `air_quality_model_evaluation`.

Each signoff must include a reviewer-controlled identifier, name,
affiliation, expertise, conflict disclosure, access limitations, publication/
attribution policy, decision, rationale, exact artifact hashes, timestamp, and
signature method. The software validates signoffs but cannot create one or
self-approve.

The empty-signoff pre-execution gate was executed as a negative test. It
correctly reported:

- required roles present: false;
- all decisions favourable: false;
- open blocking issues: zero; and
- passed: false.

### 2.7 W8 operational controls

The scheduled-cycle assessor now derives status from immutable run manifests,
timestamps, output verification, namespace records, and the reviewed release
hash. It rejects:

- duplicate logical dates or cycle IDs;
- non-consecutive counted dates;
- mixed reviewed releases;
- failed input/output verification;
- missed enqueue/terminal windows;
- manual substitution or result editing;
- insufficient real-fire cycles; and
- enabled production writes.

This implements the rehearsal/four-cycle machinery. It does not manufacture
elapsed scheduled cycles. W8 still requires one real uncounted rehearsal and
four later consecutive passing windows, at least two with transported fires.

## 3. W1 GFAS retrieval completed during Phase 0

The ADS downloader read `ADS_PERSONAL_ACCESS_TOKEN` only from the process
environment and did not print or record it. It requested GFAS v1.2 daily
analysis for the 77 frozen source dates in 29 batches.

The completed archive contains:

- dataset: `cams-global-fire-emissions-gfas`;
- product version: GFAS v1.2 daily analysis;
- grid: global regular latitude/longitude, 0.1 degrees;
- format: GRIB1;
- 29 files;
- 17,463,674,844 bytes;
- 693 GRIB messages; and
- 77 distinct requested dates.

Every date has all nine required fields:

`apb`, `apt`, `bcfire`, `cofire`, `crfire`, `frpfire`, `injh`, `offire`, and
`pm2p5fire`.

The downloader checked parameter/date uniqueness, grid identity, finite
values, non-negative emissions, units, byte counts, and SHA-256 hashes.
The final manifest SHA-256 is
`636505f251ca654b0293ded2f74ce96b0af6db497859907b60980a8c88f3168a`.

The finalized W1 cohort contains 9 retained and 6 reserve events. Independent
area, fuel, CFFDRS, GFS meteorology, and GFAS completeness all pass. The
cohort-freeze SHA-256 is
`10ebe3c736f93f4a256d1b9bd536b82e2396b2f1b852bd0108a3db727a939f98`.
Its status is `technical_complete_pending_independent_review`, not scientific
approval.

## 4. FLEXPART deposition implementation and investigation

### 4.1 Required architecture

The W6 deposition factorial must disable wet and dry removal independently
while retaining aerosol density and diameter so gravitational settling remains
active. Disabling aerosol deposition through the species definition also
disables settling and is therefore not a valid no-deposition sensitivity.

Two default-true COMMAND options were added:

- `DRYDEP_ENABLED`; and
- `WETDEP_ENABLED`.

FLEXPART first reads and initializes the complete species physics. It then
masks the per-species wet and dry deposition arrays from those command
options. The settling state is not changed. The Python candidate schema
rejects `settling: false`.

### 4.2 Failed regression attempts

The first implementation stored the flags in the broad shared `com_mod`.
Although the suite executed, the changed layout perturbed the parallel case
and produced negative nested dry-deposition fields:

- `DD_spec002 = -0.0004344109`; and
- `DD_spec003 = -0.0264881`.

That attempt was rejected and retained under
`deposition-switch-regression/`.

The flags were moved to the narrow options-reader module. A second 22-case
suite again executed, but the four-thread nested case still contained two
negative cells per dry-deposition species:

- `DD_spec002 = -0.0011929725296795368`; and
- `DD_spec003 = -0.09370654076337814`.

That attempt was also rejected and retained under
`deposition-switch-regression-r2/`.

### 4.3 Root cause and correction

The remaining values were not caused by the new switch logic. The dry
deposition kernels used Fortran `INT` to locate a grid cell. `INT` truncates
toward zero, so a particle just outside a lower grid boundary could be
assigned to cell zero with a negative fractional coordinate. Its uniform
kernel then had a negative weight. FLEXPART's nested wet-deposition kernel
already documented this exact defect and used `FLOOR`.

The correction applies the same containing-cell convention to:

- the mother dry-deposition kernel;
- the nested dry-deposition kernel; and
- the mother wet-deposition kernel.

This is an input-coordinate correction at deposition accumulation time. It is
not output clipping, replacement, absolute-value conversion, or
post-processing.

### 4.4 Final compact regression

Both the meter and eta executables were rebuilt from clean object trees. The
final suite is `deposition-switch-regression-r4/`:

- execution: 22/22 cases passed;
- numeric NetCDF fields checked: 976;
- non-finite values: 0;
- negative concentration/deposition fields: 0;
- aerosol deposition/settling default case: all scientific outputs exact;
- gas wet/dry default case: all scientific outputs exact;
- required aerosol, gas, and parallel-stress invariants: passed; and
- restart output inventory and `totals.nc` arrays: exact.

All cases have a changed `COMMAND.namelist` because the two default-true fields
are now recorded. Boundary-active cases have the intended deposition change.
Stochastic multi-thread cases differ fieldwise, as expected when scheduling
changes, but preserve their frozen invariants. The generic invariant tool
reports 21/22 because the restart input includes the new COMMAND fields; the
technical-evidence builder accepts only this bounded exception after proving
the output inventory and totals arrays exact.

Final hashes:

| Artifact | SHA-256 |
|---|---|
| Suite manifest | `65a15cbca6a76e31a1c95368b15b256bf6c2533cbf68e3aa0a56dc84f32e0fec` |
| Field comparison | `b0113c4f150bb04d3c15e678e8a96c8da44cb5eb020ed2223379f796545b9100` |
| Invariant report | `b9a4659f3b1233ee50fcc13c96ceedf9e041856f16d69dfb2b1323beadcf97fa` |
| Technical evidence | `ee9746a4d0bf784641be534daa9f605114df56d3a2fe36f893188a066e61a0aa` |
| Meter executable | `c9cf9c84f412030c6f32477bb1f0fa506e8c876843661326e6bc6785cf6af8bc` |
| Eta executable | `b1040c17b9df1fd22e7f02e875c2d84d7fe3e973a4e542cffbaf8c49a223a4b2` |

The extension status is
`technical_complete_awaiting_independent_review`.

## 5. Frozen Phase 0 artifacts

The corrected release includes the CFFEPS executable, both FLEXPART
executables, configuration files, source files, runner/verifier files, prior
W5 evidence, and the deposition-extension evidence. Production writes are
explicitly false.

| Artifact | SHA-256 | State |
|---|---|---|
| Corrected model release r2 | `1693c3e6a0af4ba9a8291268cdf616583e69010b0571f6f8f42fd48a7cc9eba0` | frozen pending independent review |
| Successor protocol r3 | `d9655d00b56760c145e2e3b33a199cd00319cdae80a6badc2ccbac4cbcc72898` | frozen; holdout unopened |
| W6 matrix r2 | `1ffd3f5e9c3a4bad6fce6424b1a280010fa63c2e0a3fd9de3ca18424e860a426` | 16 members frozen |
| Review package | recorded in its own manifest to avoid a self-referential hash | rebuilt after this record; awaiting two reviewers |
| Phase 0 preflight r3 | `55c30fc3e8ca70f727e6d6865f4c75f10c9298b06ceabfe443b9eb86ec320b02` | blocked |

The Phase 0 machine checks are:

| Check | Result |
|---|---|
| Cohorts frozen | true |
| Model release frozen | true |
| Operators and thresholds frozen | true |
| Sensitivity matrix frozen | true |
| Holdout opened before freeze | false |
| Vertical inputs complete | false |
| Reviewer approval to execute | false |
| All required inputs complete | false |
| Holdout execution authorized | false |

This is the correct fail-closed result.

## 6. Verification performed

The focused Python suite for W2–W8 completed with 34 passed tests and three
NumPy deprecation warnings in a synthetic vertical fixture. The repository-wide
suite completed with 266 passed and 19 PostgreSQL integration tests skipped
because `WEATHER_TEST_DATABASE_URL` was not configured. Its 11 warnings were
deprecation/georeferencing warnings, not test failures. Ruff passed for all
changed Python files. The CFFEPS verifier passed 10 golden cases and 6 FBP
sensitivity cases, the focused CBL zero-skew test passed, and the FLEXPART
compact suite completed 22/22 cases.

Representative reproducible commands were:

```bash
uv run --frozen python scripts/finalize_w1_source_gfas_ledger.py \
  --source-candidate-ledger <cohort>/source-candidate-ledger.json \
  --gfas-manifest <raw-gfas>/manifest.json \
  --historical-gfs-ledger <cohort>/historical-gfs-ledger.json \
  --vertical-ledger <cohort>/vertical-ledger.json \
  --surface-ledger <cohort>/surface-ledger.json \
  --output-directory <cohort>

uv run --frozen python flexpart/tests/regression_suite/run_suite.py \
  --output <readiness>/deposition-switch-regression-r4 \
  --executable-root flexpart/src

uv run --frozen python scripts/build_flexpart_deposition_switch_manifest.py \
  --w5-manifest <w5>/w5-technical-completion-manifest.json \
  --suite-root <readiness>/deposition-switch-regression-r4 \
  --comparison <readiness>/deposition-switch-regression-comparison-r4.json \
  --invariants <readiness>/deposition-switch-regression-invariants-r4.json \
  --matrix-manifest <readiness>/w6-matrix-r2/matrix-manifest.json \
  --event-area-report <readiness>/w6-area/w6-event-area-report.json \
  --executable flexpart/src/FLEXPART \
  --output <readiness>/deposition-switch-technical-evidence-r4.json

uv run --frozen python scripts/build_smoke_phase0_preflight.py \
  --cohort-freeze <cohort>/cohort-freeze.json \
  --model-release <readiness>/model-release-freeze-r2.json \
  --protocol-freeze <readiness>/protocol-freeze-r3.json \
  --sensitivity-matrix-freeze <readiness>/w6-matrix-r2/matrix-manifest.json \
  --reviewer-approval <review-package>/pre-execution-review-gate.json \
  --vertical-input-readiness <readiness>/vertical-input-readiness.json \
  --output <readiness>/phase0-preflight-r3.json
```

Angle-bracket paths above are abbreviations only. The immutable JSON
manifests record the absolute paths, commands, sizes, and hashes used in this
execution.

## 7. Work that remains before formal experiments

### Blocking Phase 0 work

1. Complete the input-only W3 assignment ledger for the 16 overpasses:
   source fire, independent area, fuel, CFFDRS state, and sufficient
   meteorology. Preregister whether 16 is the complete candidate pool and
   apply only input-valid reserve/exclusion rules.
2. Have an independent analyst review and freeze the W4 background-exclusion
   ledger without viewing NAPS concentrations or model performance.
3. Obtain artifact-specific pre-execution signoffs from both required W7
   reviewer roles and resolve any blocking issues they raise.
4. If those steps alter an input, operator, source file, or configuration,
   issue new protocol/release/review-package hashes and rerun Phase 0.

### Formal scientific experiments after Phase 0 passes

1. Execute the central W2 GFAS comparison once and evaluate PM2.5, CO, and BC.
2. Execute W3 only if at least 10 independently valid fire-overpasses remain.
3. Execute the central W4 final-NAPS comparison once.
4. Execute and verify all 16 W6 candidates, retaining every failure and
   evaluating qualitative reversals.
5. Obtain W7 methods/results review and create a reviewed release.
6. Run one real W8 rehearsal, freeze the operational timing policy, then
   observe four real consecutive scheduled cycles with at least two fire
   cycles.
7. Build the final assessment and request a separate human governance
   decision. Scientific acceptance does not itself enable production writes.

## 8. Publication notes and limitations

- The W2 support mask and W6 area bounds are independent of GFAS emission
  values and candidate output; this separation should be explicit in methods.
- W3 currently documents data absence/readiness, not vertical performance.
- W4 background exclusions require an independently frozen scientific
  decision; the template is not evidence that exclusions were completed.
- The provider-perimeter high-area case is intentionally extreme. Report its
  provenance and influence rather than suppressing it.
- The deposition boundary defect and both rejected attempts should be
  reported as part of the numerical methods and software-verification history.
- The compact regression establishes engineering behavior on the bundled
  sample; it is not atmospheric validation of smoke concentration, plume
  height, or source strength.
- No publication should state that the system is scientifically accepted
  until W2, W3, W4, W6, W7, and W8 have all completed under their frozen
  criteria.
