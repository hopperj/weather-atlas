# W5 research notebook: thread/deposition numerical investigation

**Program:** `cffeps-flexpart-acceptance-program-v1`  
**Workstream:** W5  
**Status:** technical work complete; independent review pending  
**Started:** 2026-07-24  
**Investigating:** FLEXPART 11 one-thread PM2.5 wet-deposition non-finite output  

## Research integrity and evidence rules

This is an append-only investigation record. The original failed candidate is
immutable. Every replay is made in a new attempt directory. No diagnostic may
replace a non-finite output with zero or otherwise sanitize the final array.
Any code correction must address the first invalid state or operation and
receive a new source and executable identity.

For each attempt record:

- input, executable, options, release, meteorology, and output SHA-256 hashes;
- command, working directory, selected environment variables, CPU/OS, compiler,
  library, thread count, random seed, start/end time, exit code, and wall time;
- every non-finite value with variable, array indices, coordinates, time,
  neighbours, and corresponding values in the central eight-thread run;
- FLEXPART warnings and the first reported internal `NaN`, if any; and
- the exact script revision that created the evidence.

Secrets and unrelated environment variables are excluded.

## Frozen baseline

The immutable failing member is:

```text
/Volumes/BigMrStorage/weatherapp_data/weather/derived/smoke/validation/
  experiments/gfas-v1.4.2-2026-03-19_2026-05-31/
  candidates/sens-threads-v6/attempt-001/
  transport/2026-05-25/pm25
```

The comparison member is the same date and species in:

```text
/Volumes/BigMrStorage/weatherapp_data/weather/derived/smoke/validation/
  experiments/gfas-v1.4.2-2026-03-19_2026-05-31/
  candidates/march-may-2026-mcd64a1-central-v4/attempt-001/
  transport/2026-05-25/pm25
```

Facts established before the new replays:

- the failed candidate used one thread;
- its May 25 PM2.5 result has exactly two non-finite `WD_spec001`
  values at a grid corner in the last two output times;
- concentration remained finite and was close to the central result;
- the complete-output verifier correctly rejected the candidate;
- the candidate recorded FLEXPART executable SHA-256
  `172910544d0acf9d9f9dcef8621d9070beefb786d93ee138b94905cd672e9dac`;
- the member recorded random seed `20261915`; and
- its `COMMAND` enables convection, subgrid terrain, turbulence, flux output,
  NetCDF output, and cloud-boundary-layer handling, with
  `MAXTHREADGRID=1`.

The original `run.log` also reports internal `nan_synctime`/`nan_tl`
diagnostics near the end of the simulation. Their causal relationship to the
two invalid wet-deposition cells is a hypothesis, not yet a result.

## Prospective hypotheses

H1. The same cells fail in exact one-thread replays, indicating a deterministic
numerical or state path.

H2. The invalid cells move between identical replays, indicating uninitialized
state or ordering sensitivity.

H3. The failure changes with thread count while inputs and seed remain fixed,
implicating OpenMP data sharing, accumulator reduction, or a path selected by
`MAXTHREADGRID`.

H4. The failure is independent of thread count and is triggered by a boundary
index, meteorological value, or wet-scavenging calculation near the final
output times.

These hypotheses are not mutually exclusive. The evidence will decide which
diagnostic reductions are justified.

## Reproduction matrix

The first frozen matrix is:

| Phase | Threads | Replicates | Other scientific inputs |
|---|---:|---:|---|
| Exact replay | 1 | 3 | unchanged |
| Thread matrix | 1, 2, 4, 8 | at least 1 each | unchanged |

The three one-thread replicates take precedence. The thread matrix follows
without altering meteorology, releases, particle budget, seed, physics, grid,
or executable. Runtime/affinity settings are evidence, not scientific inputs.

## Chronological log

### 2026-07-24 — investigation opened

- Confirmed the immutable failing and central member directories.
- Confirmed the runner launches the resolved executable directly from the
  member directory with `OMP_NUM_THREADS`, `OMP_PLACES=cores`,
  `OMP_PROC_BIND=true`, the frozen random seed, unlimited stack up to the
  platform hard limit, and a file-size limit.
- Confirmed all meteorology and option material needed for an isolated replay
  remains in or is linked from the failed member directory.
- Began a machine-readable baseline extractor and replay harness. They will
  write only below a new `numerical-investigation` directory.

No root cause has been assigned.

### 2026-07-24 — frozen baseline captured

Machine-readable baseline:

```text
/Volumes/BigMrStorage/weatherapp_data/weather/derived/smoke/validation/
  experiments/gfas-v1.4.2-2026-03-19_2026-05-31/
  numerical-investigation/thread-deposition-2026/baseline-evidence.json
SHA-256:
d5c705e22cbb311432ce69d41d06c48ef90833f67e02ff33e74d846348c03b62
```

The baseline establishes:

- `WD_spec001[0,0,22,0,0]` is `NaN` at
  `2026-05-25T23:00:00`, latitude `41.5`, longitude `-140.5`;
- `WD_spec001[0,0,23,0,0]` is `NaN` at
  `2026-05-26T00:00:00`, at the same cell;
- the three in-domain neighbours available at that southwest corner are zero
  at both times;
- the corresponding eight-thread central values are zero;
- `spec001_mr` and `DD_spec001` are entirely finite and non-negative; and
- the output variables do not declare a NetCDF `_FillValue` that could explain
  these values as an intentional missing-data mask.

The one-thread log first reports a nonzero internal counter at simulation
second 77,700. The central eight-thread log also contains nonzero
`nan_synctime`/`nan_tl` counters, first at second 78,300, despite writing
entirely finite scientific fields. Therefore the counters identify an internal
condition worth tracing but are not, by themselves, sufficient evidence of
the wet-deposition output defect.

### 2026-07-24 — exact one-thread reproduction complete

Three new one-thread attempts used the unchanged executable SHA-256
`172910544d0acf9d9f9dcef8621d9070beefb786d93ee138b94905cd672e9dac`,
random seed `20261915`, options, releases, meteorology, domain, and particle
budget.

| Replicate | Wall time (s) | `WD_spec001` non-finite values | Invalid indices |
|---:|---:|---:|---|
| 1 | 43.214 | 2 | `[0,0,22,0,0]`, `[0,0,23,0,0]` |
| 2 | 43.474 | 2 | `[0,0,22,0,0]`, `[0,0,23,0,0]` |
| 3 | 43.125 | 2 | `[0,0,22,0,0]`, `[0,0,23,0,0]` |

Every science-variable finite sum, negative count, non-finite count, invalid
index, coordinate, time, and value matched across the three attempts. The
NetCDF file hashes differ because FLEXPART writes run-specific global metadata;
file-byte identity is therefore not used as a substitute for field identity.

Reproduction matrix:

```text
/Volumes/BigMrStorage/weatherapp_data/weather/derived/smoke/validation/
  experiments/gfas-v1.4.2-2026-03-19_2026-05-31/
  numerical-investigation/thread-deposition-2026/reproduction-matrix.json
SHA-256:
cc5fdfe816c1e17a4e7a37f3e0c9992de9325285ef3f96a78e626e1ad706a1d4
```

Interpretation: H1 is supported. The output defect is deterministic for this
frozen one-thread member. H2 is not supported by these repetitions. This does
not, by itself, establish whether the cause is thread selection, a boundary
accumulator, a random-stream-dependent particle path, or a deposition/output
path.

### 2026-07-24 — 1/2/4/8 thread matrix complete

The same executable, seed, meteorology, release, physics, particle budget,
output grid, and duration were run with only `MAXTHREADGRID` and the matching
OpenMP thread setting changed. The one-thread row summarizes the three exact
replicates above; the other rows are first replicates.

| Threads | Replicates | Wall time (s) | Wet-deposition non-finite count | `DD` finite sum | `WD` finite sum | Concentration finite sum |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 3 | 43.125–43.474 | 2 in every run | 776.1197021807 | 399730.3102266390 | 69886.8419432273 |
| 2 | 1 | 29.326 | 0 | 770.2556686996 | 399628.4881304485 | 69752.9418637165 |
| 4 | 1 | 21.965 | 0 | 762.2506688021 | 399736.2675015751 | 69740.4858514689 |
| 8 | 1 | 19.810 | 0 | 735.4909961759 | 399840.1641036930 | 69513.4275868082 |

All finite values in the table were also non-negative. The differing finite
sums are recorded rather than treated as failures because FLEXPART's
thread-partitioned stochastic calculation need not produce byte-identical
particle histories across thread counts. That explanation remains to be
verified against the random-number implementation before defining the
post-correction equivalence tolerance.

The first nonzero internal `nan_synctime`/`nan_tl` counter appeared at
simulation second 77,700, 79,800, 78,300, and 79,500 for 1, 2, 4, and 8
threads, respectively. Thus:

- H3 is supported in the limited observational sense that the final
  wet-deposition defect is selected by the one-thread execution;
- the internal counter is not sufficient to cause a non-finite output;
- the evidence does not yet distinguish a one-thread accumulator defect from
  a stochastic trajectory that only the one-thread stream encounters; and
- H4 is not supported as a thread-count-independent final-output failure.

No production source or executable was changed for this matrix.

### 2026-07-24 — deposition-path source trace

The source trace compared the working FLEXPART tree with the preserved 11.1
release archive. The release archive has SHA-256
`f01758e7bfc3861b6f0b923666b0f4547fa8ca687921ddc6fb234c79e92564c3`.

The OpenMP wet-deposition kernel in `wetdepo_mod.f90` accumulates into the
general concentration scratch array `gridunc_omp` at vertical index 1. After
the particle loop, that slice is reduced into `wetgridunc` and immediately
zeroed. The nested output follows the analogous `griduncn_omp` path.
`outgrid_mod.f90` nevertheless allocates and initializes distinct
`wetgridunc_omp` arrays which this wet-deposition path does not use.

This pattern is also present in the unmodified FLEXPART 11.1 release; it was
not introduced by the local performance work. Concentration calculation also
reduces and clears the same general scratch array at the end of its own call,
and dry deposition uses the same reuse strategy while remaining finite in the
frozen failure. Consequently, the unused dedicated wet scratch array is a
high-priority diagnostic hypothesis, not a confirmed defect.

The next controlled experiment will use an isolated debug build to route only
the OpenMP wet-deposition accumulators through the already allocated dedicated
wet scratch arrays. The production tree and executable remain immutable. A
one-thread result that becomes finite would support scratch-path involvement;
an unchanged failure would reject that hypothesis. Either result will be
recorded with source patch, build command, compiler identity, executable hash,
and complete output scan.

### 2026-07-24 — dedicated wet-scratch diagnostic rejects hypothesis

The isolated diagnostic was built successfully with GNU Fortran 16.1.0 on
arm64 macOS. Its only source change routed OpenMP wet deposition through
`wetgridunc_omp`/`wetgriduncn_omp`. It did not modify the production tree.

```text
Diagnostic executable SHA-256:
9b9ef69954721a0f3ba73223126b13b71918bfd8e53a007ae783458a4a2e47c8

Build manifest SHA-256:
19956c69fdeb55de515a01e0bdb30ec68c4c9f74459f959431c743251c05c07e

Exact one-thread diagnostic replay manifest SHA-256:
97cd7a94ccbd875e24f8c94af120868bc22b1fb372ae422e1ffda5e1d076c011
```

The diagnostic reproduced the exact two `WD_spec001` NaNs at the exact same
cells and times. Dry deposition, finite wet deposition, and concentration sums
were identical to all three production one-thread replays. The first internal
counter remained at simulation second 77,700.

Therefore the unused dedicated wet scratch arrays are not causal for this
failure. This negative result rejects the first accumulator-isolation
hypothesis and prevents an unsupported source change from being promoted as a
fix. The next diagnostic will stop at the first non-finite value before the
wet-deposition grid update and capture its particle, species, time, position,
mass, interpolation weights, and wet-scavenging state.

### 2026-07-24 — direct contamination path and upstream CBL failure traced

Three read-only-in-effect diagnostic builds added traces without clamping,
skipping, terminating, or replacing any affected value. All completed with the
same two invalid wet-deposition cells and identical finite science sums as the
frozen one-thread signature.

The trace identifies particle 8,534:

- at second 81,300, the CBL candidate velocity and drift become `NaN`;
- the existing CBL recovery path is entered, but `reinit_particle` returns a
  `NaN` replacement velocity even though the incoming position and velocity
  are finite;
- at second 81,600, the particle's vertical position is `NaN`;
- at second 81,900, all three coordinates are `NaN`, while its deposited
  increment is exactly zero; and
- the wet-grid transform maps `int(NaN)` to `(0,0)` on this build, creates
  `NaN` weights, and evaluates `0 * NaN`, contaminating only the southwest
  cell.

The v3 evidence is:

```text
Diagnostic executable SHA-256:
04e5e76677e214ab36f612982a1e47bb07cbc5d12b008df2348948dd3a7ee693

Build manifest SHA-256:
7ce7e5b71b735678ce6f124edbe325a6ef8efd2df905c2198dfe67fb6207e7ff

Replay manifest SHA-256:
a6cae7b9407bbce09e9936db6aead9283060d9325ea7aeb6b883dc285179217e
```

Source inspection supplies a specific upstream candidate. At the failed
recovery, `-h/ol` is approximately 5, the CBL transition's zero point, and
`skew` can become exactly zero in single precision. The main `cbl` routine has
a zero-skew branch. `reinit_particle` lacks that branch and evaluates a
distribution expression whose denominator contains `fluarw**2=0`, causing
`0/0`. It also does not use the signed cube-root helper used by the main
routine.

This is now a testable root-cause candidate, not yet an accepted correction.
The next isolated build will mirror the main routine's signed cube-root and
zero-skew handling inside `reinit_particle`. The causal criterion is a wholly
finite exact one-thread replay with no grid-kernel suppression; full acceptance
still requires reviewed source and the complete frozen regression matrix.

### 2026-07-24 — zero-skew causal intervention succeeds

The isolated build modified only `reinit_particle`; wet deposition and output
code remained unchanged. It used the signed cube-root helper and explicit
zero-skew limiting branch already present in the main `cbl` routine.

```text
Intervention executable SHA-256:
bd6e141230b2545c59a0552051c5282ee27c8c5765ed37382d5351e6f956630a

Build manifest SHA-256:
bf3a8a3e4d92a53906f1b78669d67583d5617c31f37cdabd71ff516f2d91b81f

Post-intervention 1/2/4/8 matrix SHA-256:
750c4796e83444ee61ae8e6784f412e071b318ddbc0efe27efcf44efda0f0c70
```

All three one-thread repetitions are fully finite and non-negative and have
identical science signatures. The 2-, 4-, and 8-thread repetitions are also
fully finite and non-negative. CBL instability counters remain active, which
is expected: the correction makes reinitialization defined at zero skew; it
does not suppress detection of unstable candidate velocities.

Five compact regression cases covering skewed CBL, single- and four-thread
all-physics, and aerosol/gas deposition all completed. Four were field-exact
against the preserved 11.1 baseline. The stochastic four-thread case changed
particle fields but retained exact inputs and output inventory, no non-finite
values, and exact totals. The five selected invariant checks passed.

This identifies the root cause and verifies a causal correction in isolation.
W5 remains in progress because the correction has not been reviewed or applied
to production, a focused zero-skew unit regression does not yet exist, only
five of the 22 compact cases have run, and the post-production mass-consistency
and frozen-member gates remain.

## Planned machine-readable artifacts

```text
numerical-investigation/thread-deposition-2026/
  baseline-evidence.json                         # created
  reproduction-matrix.json                       # complete 1/2/4/8 matrix
  attempts/
  root-cause-analysis.md                         # source trace in progress
```

Each JSON artifact will be self-describing and include its creation command.

## Interpretation policy

A replay that finishes without non-finite values does not clear the defect.
The original failure remains valid, and repetition/environment analysis
continues. A replay that reproduces the defect narrows the cause but is not a
fix. W5 remains blocked until the first invalid operation is explained, a
reviewed correction and regression test exist, and the frozen post-fix thread
matrix is entirely finite, non-negative, complete, and mass-consistent.

### 2026-07-26 — production correction and focused regression

The causal correction was applied to production
`flexpart/src/cbl_mod.f90`. `reinit_particle` now uses the signed cube-root
helper already used by the main CBL routine and explicitly implements the
symmetric zero-skew limit. No wet-grid clamp, skip, replacement, or final-array
sanitization was added.

The production identities are:

```text
cbl_mod.f90 SHA-256:
11e8d37cd8d819b4a7d09a30a855c9d24b575ba8413f2e5c1daa819245526ad9

FLEXPART SHA-256:
49569d43ed33ec5fa15843ecbb946aa966853d0ffd07fd7a6d1d20448b9a8ed0

FLEXPART_ETA SHA-256:
8852db3f43b686ce10234a2665bede7be335b1202db75740a98be6ad6fbac6ae
```

A focused Fortran regression at `flexpart/tests/cbl_zero_skew` verifies both
directions of the defect: it passes the corrected source and produces a
non-finite recovery velocity when compiled against the preserved pre-fix
source. This protects the first invalid operation rather than its later
wet-deposition symptom.

### 2026-07-26 — complete compact and frozen-member regression

All 22 compact FLEXPART regression cases completed. Seventeen deterministic
fields were exact against the preserved baseline. Five stochastic cases
changed particle fields as expected after the recovery correction, but all
five passed the prospectively selected inventory, structure, finiteness,
non-negativity, release, and conservation invariants.

```text
22-case suite manifest SHA-256:
71aab348b0a46ec14c3dcb8830b855b690e91b51d47b62c0b5d6645e4912f16e

Comparison SHA-256:
c31503573cf15bdac14939668728652349e277bacd95f411285db1613ec7c1e5c

Invariant verification SHA-256:
6e4772f9e5f06eda2b94b954c3a7b436fed16d0e77d0107c3219ace9f40fe2bb
```

The originally failing member then passed a corrected 1/2/4/8-thread matrix.
The complete frozen set of 24 members was run at one and eight threads, for 48
new attempts. Every attempt passed all hard checks:

- every numeric NetCDF value is finite;
- all science concentration and deposition values are non-negative;
- the output inventory and NetCDF structure are exact;
- release mass, particle count, seed, and successful termination are exact;
- particle accounting closes; and
- cumulative deposition does not exceed released mass.

```text
48-attempt run manifest SHA-256:
ac0c7a822283e71e5ee07fdba53d22fd51e623fed9bfe6a465217b27674d43ac

Complete-output verification SHA-256:
6333f91b36913943d4cdbfa72baae20ecde4f1a9c4a0ac905654fe87383e8c69

W5 technical completion manifest SHA-256:
c1a47c2b9bddd4b2f8d7b14a200b0784d83ed1235ad431ed4b3911484719c05b
```

Seven of 24 one-versus-eight-thread pairs exceed a proposed 2% normalized-L1
concentration diagnostic. That number was inferred from pilot behaviour and
was not frozen by independent review, so it is reported as an advisory
diagnostic rather than retroactively promoted to a pass/fail criterion. The
worst concentration normalized-L1 difference is 2.471%. A reviewer must decide
whether to adopt, revise, or reject a formal engineering tolerance.

The CFFEPS regression also passed 10 golden cases and six FBP sensitivities.
The Python suite passed 223 tests; 19 PostgreSQL integration tests were skipped
because `WEATHER_TEST_DATABASE_URL` was not configured.

### W5 technical decision

The production numerical defect is reproduced, causally explained, corrected
at the first invalid operation, guarded by a focused regression, and cleared
by the complete compact and frozen-member matrices. W5 is therefore
`technical_complete_awaiting_independent_review`.

Scientific governance is not self-certifying. Formal closure still requires
an independent numerical code review and an emissions-science review
confirming that the change is a defined physical/numerical limit rather than
output sanitization. No production-write setting was changed.
