# CFFEPS → FLEXPART smoke pipeline implementation report

**Implemented:** 2026-07-22  
**Status:** Validation-only workflow running; public writes and scheduled operational forecasts remain feature-gated

## Outcome

The application now has an end-to-end, reproducible wildfire-smoke path:

```text
CWFIS VIIRS detections + dated CWFIS FFMC/DMC/DC grids
  → deterministic fire-event snapshot
  → hourly GFS atmospheric profiles
  → CFFEPS 4.1 emissions and plume rise
  → isolated PM2.5, CO, and BC FLEXPART 11.1 runs
  → validated NetCDF and derived COGs
  → PostgreSQL catalogue and signed tiles
  → ordinary map selection, timeline, animation, and run builder
```

The UI labels the particulate product **Primary wildfire PM2.5**. This is not
a chemical air-quality forecast and does not include secondary aerosol formation.

## Implemented components

| Layer | Implementation |
|---|---|
| Fire events | Order-independent union-find reconciliation, stable content-derived event IDs, versioned thresholds, source hashes, and ambiguity/exclusion warnings |
| Scenario contract | Immutable canonical JSON, 24-hour/domain/event/particle bounds, automatic per-fire CWFIS state or explicit manual override, native growth and single-fire cumulative area curves, low/central/high uncertainty |
| CFFEPS | Traceable official 4.1 source, portable Fortran driver with explicit mixedwood/dead-fir/grass parameters, phase-resolved PM2.5/CO/BC adapter, 12-layer normalized injection profile, NetCDF emissions bundle |
| Meteorology | Complete archived GFS-cycle verification and ecCodes extraction of hourly 40-level profiles |
| FLEXPART | Run-local safe options, one transport member per species, bounded releases/particles/runtime/storage, settling guard, mass round-trip checks, OpenMP execution |
| Outputs | Surface concentration, atmospheric column, wet deposition, dry deposition, and mass-weighted injection-height COGs |
| Persistence | Immutable scenarios/revisions, database job state machine, model builds, resolved inputs, artifact hashes, catalogue linkage, cancellation, quarantine |
| Scheduling | Daily CFFDRS archive and fire reconciliation; five-minute one-slot validation-aware worker; daily validation canary; four-cycle operational enqueue after GFS, gated by independent review and `SMOKE_OPERATIONAL_ENABLED` |
| API/UI | Bounded read/write endpoints, current GFS capabilities, fire selection, multi-step run builder, persisted status, catalogue-native smoke visualization and caveat |
| Operations | Read-only archive inspection and scientific NetCDF comparison commands |
| Admission | Checksum-verified GFS and CFFDRS coverage, frozen-event/domain checks, grid/release/particle bounds, disk reserve, 512 GiB smoke namespace quota, serialized bounded queue, and worker-side revalidation |
| Retention | Interactive/operational retention classes plus SQL guards that exclude every referenced simulation input and artifact |
| Observability | Persisted phase/input-age/mass/storage metrics, Prometheus gauges, structured run-phase logs, and smoke Grafana panels |

## Validation evidence

### Real persisted run

Run `92d0eead-6228-4dac-b379-aed5c54b4391` is the first post-enablement
validation canary. It used the archived 2026-07-22 12Z GFS cycle and two Atlantic
Canadian fire events whose CFFDRS state was sampled from the checksummed
2026-07-20 NRCan grids. The exact grid manifest, cell row/column, FFMC, DMC, DC,
fuel crosswalk, and FBP percentages are frozen in the run archive.

| Metric | Result |
|---|---:|
| Fire events | 2 |
| Emission/release rows | 3,312 |
| Particles | 300,000 |
| CFFEPS time | 11.495 s |
| FLEXPART transport time | 73.049 s |
| Total worker time | 90.103 s |
| Published COGs | 168 |
| Scientific archive | 429,757,589 bytes |
| Mass-balance residual | 0 kg |

The run completed `complete_with_warnings`; its sole warning is the required
research/not-an-official-forecast caveat.

### Earlier persisted run

Run `220d9bad-781a-4883-addc-0bc63c496f68` completed through database
publication using the archived 2026-07-22 06Z GFS cycle:

| Metric | Result |
|---|---:|
| Fire events | 1 |
| CFFEPS/FLEXPART release records | 828 |
| Particles | 249,999 |
| FLEXPART members | PM2.5, CO, BC (isolated) |
| Transport wall time | 42.856 s |
| Published COGs | 168 |
| Recorded artifacts | 177 |
| PM2.5 released | 0.1705049564 kg |
| CO released | 1.0405817194 kg |
| BC released | 0.0062685646 kg |

The inspection command re-read the archive and verified the GFS manifest, fire
snapshot, all three FLEXPART NetCDF outputs, and all 168 display assets with no
checksum failures. A same-run scientific comparison reported exact PM2.5, CO,
and BC arrays.

### Post-hardening reproducibility and timing

Two additional runs used the final container build, identical immutable inputs,
and the wired per-species seed contract:

| Metric | Run `971d104f…` | Run `0dbe35b2…` |
|---|---:|---:|
| Transport wall time | 58.088 s | 45.033 s |
| Total worker time | 76.459 s | 60.727 s |
| Releases / particles | 828 / 249,999 | 828 / 249,999 |
| COGs | 168 | 168 |
| Scientific archive | 425,602,696 bytes | 425,585,420 bytes |
| Mass-balance residual | 0 kg | 0 kg |

Both archive inspections passed with no checksum failures. Their GFS, fire
snapshot, scenario, CFFEPS executable, and FLEXPART executable provenance are
identical. Emissions, release geometry, release mass, and particle allocation
are exact. PM2.5, CO, and BC grid fields pass the nonnegative, finite, inventory,
and aggregate-total invariant comparison.

Eight-thread fields are intentionally reported as `INVARIANT`, not bitwise
`EXACT`: FLEXPART's dynamic OpenMP particle scheduling can assign otherwise
fixed per-thread random streams in a different order. The run contract now
wires the scenario seed into `FLEXPART_RANDOM_SEED` using stable, recorded
per-species seeds; it does not claim counter-based, scheduling-independent RNG.
The first acceptance run used an older executable build, so cross-build results
also pass invariants but correctly report unequal executable provenance.

### CFFEPS regression

[`cffeps/tests/golden_cases.json`](../cffeps/tests/golden_cases.json) records ten
exact portable-driver cases covering conifer, deciduous, mixedwood, grass, and
slash fuels from low/moist to high/dry conditions. The verification run passed
all ten cases and checks output checksums, plume top, final area, and phase fuel
totals. Six additional sensitivity cases verify that M2 conifer percentage, M4
dead-fir percentage, and O1 curing percentage each change model output.

Run it with:

```bash
uv run python cffeps/tests/verify_golden.py
```

### FLEXPART regression

The unchanged 22-case suite remains the transport acceptance baseline. Candidate
artifacts for the final seed-contract implementation are stored outside the
repository under:

```text
/Volumes/BigMrStorage/weatherapp_validation/flexpart-seed-contract-20260722-1505
```

All 22 executions passed after the final random-seed contract change. Seventeen
cases were bitwise exact against the
pre-optimization baseline. The five stochastic/parallel cases differed at the
particle-array level as expected from OpenMP random-number scheduling; all 22
passed the suite's output-inventory, finite-value, and scientific-total
invariant validator.

The suite and comparator cover meter/eta coordinates, forward/backward
transport, turbulence and convection schemes, wet/dry deposition, settling,
chemistry, receptors, fluxes, restart, NetCDF/binary output, and one to eight
OpenMP threads.

### Deployment and UI

- The application suite passes 193 Python tests and 28 frontend tests; 19
  database integration tests are skipped only because the disposable
  `WEATHER_TEST_DATABASE_URL` is not configured. The live database migration,
  permission, queue-SQL, and readiness checks pass separately.
- The Airflow image builds both model executables successfully on ARM64.
- Runtime dynamic-library resolution and the simulation-worker import pass in
  the final image.
- All Airflow DAGs, including the CFFDRS and validation-canary DAGs, reserialize
  with no import errors.
- Database migrations 0019–0025 are applied and checksum-verified locally.
- The published smoke product resolves through the API to signed WebP tiles.
- The API exposes bounded smoke capabilities and Prometheus queue, status,
  workload, phase-duration, mass, input-age, residual, byte, and disk gauges;
  Grafana panels consume those series.
- Browser verification found the PM2.5 product, 17 current frames, buffered
  animation, timestamp overlay, two local fire events, the GFS-bounded builder,
  the scientific caveat, and the disabled submission gate with no console errors.

## Operator commands

```bash
# Reconcile the latest CWFIS snapshots.
./scripts/trigger_fire_event_reconciliation.sh

# Enqueue the configured operational scenario (only when its feature flag is enabled).
./scripts/trigger_operational_smoke.sh

# Verify every archived checksum and summarize one run.
WEATHER_DATA_ROOT=/path/to/weather \
  ./scripts/inspect_smoke_run.sh <run-id>

# Compare scientific NetCDF arrays and provenance for two runs.
WEATHER_DATA_ROOT=/path/to/weather \
  ./scripts/compare_smoke_run.sh <candidate-run-id> <reference-run-id>
```

The operational schedule is `05:45`, `11:45`, `17:45`, and `23:45` UTC, after
the four scheduled GFS collections. The interactive worker checks the queue every
five minutes and uses the one-slot `flexpart_runs` Airflow pool.

Interactive admission defaults to a 24-hour horizon, 50,000 output cells,
1,000,000 particles, 20,000 releases per species, five queued runs, a 20 GiB
free-space reserve, and a 20 GiB per-member output limit. Scenario/revision
writes verify the complete local GFS archive and frozen fire selection before
insertion; run submission repeats the check so removed or stale inputs cannot
enter the queue.

## Intentional acceptance gates

The implementation does not turn a successful software test into an official
forecast. These flags remain false:

```text
SIMULATION_WRITES_ENABLED=false
SMOKE_OPERATIONAL_ENABLED=false
SMOKE_VALIDATION_RUNS_ENABLED=true
```

The code now supplies the evaluation harness and versioned criteria for GFAS
inventory, MISR plume-height, and NAPS PM2.5 matched pairs. It also records the
emissions registry as `validation_only/pending_independent_review`; worker and
enqueue guards reject every non-validation run while that state remains. Before
enabling public or operational writes, acquire and freeze the external datasets,
construct reviewed matched pairs for weak/moderate/major Canadian episodes, pass
the preregistered criteria, obtain the two independent registry reviews, and
observe at least four scheduled validation runs completing inside their cycle
window. These external evidence and sign-off items cannot be self-certified by
the implementation.

The following modes fail explicitly instead of being approximated silently:

- ensemble publication (submit low, central, and high revisions separately);
- fixed-source tests without an explicit mass-rate contract;
- observed-perimeter growth until a versioned perimeter source is integrated;
- custom area curves with anything other than one explicit event; and
- domains selecting more than 200 supported fire events.
