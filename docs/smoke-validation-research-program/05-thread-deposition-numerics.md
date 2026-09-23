# W5 research plan: thread-dependent wet-deposition non-finite values

**Blocker:** the one-thread sensitivity produced two non-finite cumulative
wet-deposition values  
**Priority:** first technical workstream  
**Estimated active effort:** 1–3 person-weeks  
**Output:** root-cause report, reviewed fix, and complete-output regression

## Problem statement

Candidate `march-may-2026-mcd64a1-threads-1-v6` completed all model processes,
and its concentration output was finite and close to the eight-thread central
run. However, the PM2.5 member initialized on 2026-05-25 contained two
non-finite `WD_spec001` values at a grid corner in the final two output times.
The schema-v2 verifier failed the candidate.

The failing output is retained at:

```text
/Volumes/BigMrStorage/weatherapp_data/weather/derived/smoke/validation/experiments/gfas-v1.4.2-2026-03-19_2026-05-31/candidates/sens-threads-v6/attempt-001/transport/2026-05-25/pm25/output/grid_conc_20260525000000.nc
```

Its verifier report SHA-256 is
`a9012ba0521a24485c175218fe7d331451944888fdd8af080d3f4532bebb7067`.

## Research questions

1. Is the failure deterministic under the exact one-thread input, executable,
   compiler, seed, and environment?
2. Is the non-finite value created inside FLEXPART physics, OpenMP reduction,
   boundary/grid accumulation, NetCDF output, or postprocessing?
3. Does it indicate uninitialized memory, an out-of-bounds access, a divide by
   zero, overflow, or a scheduling-dependent race?
4. Can the defect be fixed without changing scientifically valid mass,
   concentration, or deposition behaviour?

## Preserve the evidence

Before any rerun:

- verify every existing input/output checksum;
- copy no file over the original attempt;
- extract the exact indices, coordinates, times, raw IEEE representation,
  neighbouring values, fill-value metadata, and cumulative history of both
  invalid cells;
- freeze executable, source archive, local patch set, compiler version,
  compile flags, libraries, OS, CPU, OpenMP environment, and NetCDF versions;
  and
- write `numerical-investigation/baseline-evidence.json`.

The original failure remains the baseline even if it cannot be reproduced.

## Reproduction matrix

### Phase 1: exact replay

Run the exact May 25 PM2.5 member at one thread at least three times with the
same seed and immutable input, each in a new attempt directory. Hash all
outputs.

Outcomes:

- identical invalid cells imply a deterministic numerical/code path;
- moving invalid cells imply uninitialized state or nondeterministic ordering;
- no recurrence implies environment sensitivity and requires environment
  capture and expanded repetition.

### Phase 2: thread matrix

Run the same member with:

```text
OMP_NUM_THREADS = 1, 2, 4, 8
```

Keep particle count, seed, meteorology, releases, physics, compiler, and output
options identical. Repeat each configuration enough times to distinguish
deterministic from intermittent behaviour.

### Phase 3: controlled scope reduction

Create minimal diagnostic cases by changing one engineering factor at a time:

- wet deposition on/off;
- dry deposition on/off;
- convection on/off;
- output grid extent and the suspect corner;
- PM2.5 versus BC aerosol species;
- last output hours removed;
- particle count reduced while preserving the failing meteorology; and
- suspect meteorological precipitation/cloud fields replaced only in a
  labelled synthetic unit reproducer.

These diagnostic cases are not scientific validation candidates.

## Instrumented builds

Build separate debug executables; never modify the release executable in
place. For GNU Fortran, investigate with appropriate combinations of:

```text
-O0 -g
-fcheck=all
-fbacktrace
-ffpe-trap=invalid,zero,overflow
-finit-real=snan
-finit-integer=<sentinel>
-Wall -Wextra -Wconversion-extra
```

Use compiler-supported address/undefined-behaviour sanitizers where compatible.
Run with OpenMP runtime diagnostics. If the failure appears only with multiple
threads in another case, add a race-detection build/tool appropriate to the
platform.

Instrument the wet-deposition path around:

- scavenging coefficients and denominators;
- precipitation/cloud-water inputs;
- particle mass before/after removal;
- grid-cell index calculation at domain boundaries;
- deposition accumulator initialization and reduction;
- cumulative-to-output array transfer; and
- NetCDF missing/fill-value handling.

Abort at the first non-finite intermediate and record particle, cell, time,
species, meteorology, and call stack. Do not merely replace non-finite output
with zero.

## Code audit

Trace `WD_spec001` from particle-level removal to final NetCDF write. Review:

- allocation dimensions and lower/upper bounds;
- longitude wrapping and north/east edge indexing;
- halo cells and off-by-one conditions;
- arrays initialized differently inside/outside OpenMP regions;
- `SAVE`, `THREADPRIVATE`, `PRIVATE`, `FIRSTPRIVATE`, and reduction clauses;
- real precision and implicit conversions;
- division by precipitation, density, layer thickness, or residence time;
- cumulative arrays reused across output times; and
- error/fill-value propagation from meteorological input.

Record every inspected symbol and file/line in the root-cause notebook.

## Fix criteria

The fix must:

- address the first invalid operation or state, not sanitize the final array;
- preserve mass conservation and scientific configuration;
- include a focused regression reproducer;
- pass all 10 CFFEPS golden and 6 FBP sensitivity cases;
- pass the complete Python suite and schema-v2 output verifier;
- pass independent code review; and
- receive a new FLEXPART patch/executable identity.

If the defect is upstream FLEXPART, prepare a minimal reproducer and patch
description suitable for upstream reporting.

## Verification after the fix

Freeze a prospective matrix before running the fixed validation:

- all 24 members at 1 and 8 threads;
- the failing member additionally at 2 and 4 threads;
- unchanged seeds and release mass;
- complete concentration, wet-deposition, and dry-deposition verification; and
- repeated exact one-thread runs.

Hard requirements:

- every scientific field finite and non-negative;
- no masked/fill value inside a valid output domain;
- exact release mass and complete model termination;
- consistent output dimensions/times; and
- all final cumulative deposition no greater than released mass after unit and
  domain accounting, subject to documented numerical tolerance.

Field-equivalence thresholds must be frozen with reviewer input. The previous
pilot showed about 1.19% normalized L1 concentration difference between one
and eight threads. That observed value may inform, but cannot be presented as
an unbiased preregistered tolerance. A proposed future engineering bound is
normalized L1 no greater than 2% and active-union `R >= 0.999`, accompanied by
mass-integral limits; label these pilot-informed if adopted.

## Automated regression

Add two levels:

1. **Small deterministic test:** the minimal reproducer fails on any
   non-finite concentration/deposition value.
2. **Scientific member test:** the exact May 25 PM2.5 case, or a legally
   redistributable reduced fixture, runs at one thread and validates its full
   NetCDF fields.

Extend `scripts/verify_smoke_validation_candidate.py` only if needed; it
already checks every concentration and deposition field. Never weaken that
check to make the candidate pass.

Suggested artifacts:

```text
numerical-investigation/
  baseline-evidence.json
  reproduction-matrix.yaml
  attempts/
  debug-build-manifests/
  first-invalid-operation.json
  root-cause-analysis.md
  patch.diff
  code-review.md
  post-fix-thread-matrix.json
```

## Definition of done

- The original invalid values and environment are fully characterized.
- The failure is reproduced or its environment dependence is demonstrated.
- The first invalid operation/root cause is documented.
- A reviewed fix exists with a new source/executable hash.
- Regression tests fail without the fix and pass with it.
- All frozen one-, two-, four-, and eight-thread post-fix cases contain only
  finite, non-negative complete fields.
- Source/release mass and scientific options remain invariant.
- The emissions and numerical reviewers accept that the fix is not an
  output-sanitization workaround.

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| Failure cannot be reproduced | Freeze full environment; repeat; compare libraries/CPU/compiler; retain unresolved status |
| Debug flags alter timing/path | Use multiple instrumented builds and targeted logging in the release build |
| Fix changes scientific fields substantially | Treat it as a new model version and rerun every central/sensitivity candidate |
| Invalid value comes from meteorology | Trace and validate meteorological fields; fix ingestion/handling, not output |
| Temptation to coerce NaN to zero | Prohibit final-array sanitation as an acceptance fix |

## Execution checklist

- [ ] Freeze baseline evidence and environment.
- [ ] Extract exact invalid indices/times/neighbours.
- [ ] Run three exact one-thread replays.
- [ ] Run 1/2/4/8 thread matrix.
- [ ] Build instrumented executables.
- [ ] Find and document the first invalid operation.
- [ ] Implement minimal reviewed fix.
- [ ] Add regression fixture and whole-output checks.
- [ ] Run post-fix full thread matrix.
- [ ] Issue new model-build and candidate IDs.
