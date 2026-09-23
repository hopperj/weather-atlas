# FLEXPART 11.1 optimization report

Recorded on 2026-07-20 on an Apple M1 Ultra with 20 CPU cores and 64 GB of
memory.

## Implemented changes

- Reused convection particle and grid-column workspaces instead of allocating
  and deallocating them at every convection synchronization.
- Reused per-thread dry-deposition scratch storage instead of allocating it
  inside each OpenMP particle loop.
- Bundled interpolation and turbulence scalars into one OpenMP thread-local
  state object per module. On macOS, GCC implements `THREADPRIVATE` through
  emulated TLS; this reduces many TLS address lookups in each hot routine to
  one without changing arithmetic order.
- Consolidated each thread's random-number state into a contiguous, padded
  record. The random algorithms, seeds, and per-thread sequences are unchanged,
  while mutable state no longer shares cache lines between workers.
- Added an opt-in `FLEXPART_RANDOM_SEED` environment contract. Runs that omit it
  retain the original per-thread seeds; the smoke runner supplies a recorded,
  deterministic per-species seed so a scenario's seed is no longer metadata-only.
- Added repeatable, interleaved CPU-scaling benchmarks and invariant validation
  for stochastic cases.

The existing code already compacted live particle indices before the hot loop
and already used dynamic OpenMP scheduling and per-thread output accumulators.
Those mechanisms were retained rather than duplicated.

## Scientific regression result

- All 22 cases completed successfully.
- The same 17 cases that were reproducible in the original code remain bitwise
  exact in every scientific array and legacy binary output.
- The remaining five cases are the same five that varied between two runs of
  the unchanged original: `06`, `09`, `15`, `20`, and `22`.
- All 22 invariant checks pass: stable inputs are identical, output inventories
  are identical, every scientific array in `totals.nc` is exact, and no new
  NaN or infinity was introduced.
- The exact all-physics single-thread case remains bitwise identical.

The complete regression suite fell from 124.49 seconds to 83.47 seconds, a
33.0% reduction (1.49x overall).

## Million-particle benchmark

The benchmark uses one million particles, three species, turbulence,
mesoscale turbulence, convection, subgrid terrain, wet and dry deposition,
settling, age spectra, flux output, nested output, and per-thread grid
reductions. Each point is the median of three one-hour runs.

| Threads | Original median | Final median | Speedup | Time reduction |
| ---: | ---: | ---: | ---: | ---: |
| 1 | 28.710 s | 16.094 s | 1.78x | 43.9% |
| 2 | 20.571 s | 10.319 s | 1.99x | 49.8% |
| 4 | 12.970 s | 6.988 s | 1.86x | 46.1% |
| 8 | 8.383 s | 5.324 s | 1.57x | 36.5% |
| 16 | 6.868 s | 4.886 s | 1.41x | 28.9% |

The final benchmark interleaved the archived original and delivered optimized
executables at every thread count to limit run-order and thermal bias. All 30
runs passed. The executable SHA-256 values were
`4ceaf2654798ed59f6e66bab8a15bafff566b2a9919de4e052923329f8432153`
for the original and
`3258367f060d194e8105deb11ccef92fa0286644bc7d7a5aa0b3ae754463b50b`
for the optimized meter-coordinate build.

## Scope boundary

The following were not marked complete:

- A per-particle counter-based RNG would deliberately change stochastic
  trajectories and restart state. It needs an explicit compatibility mode and
  statistical acceptance tests over longer meteorology than the bundled
  three-hour sample.
- Particle structure-of-arrays conversion, spatial bucketing, and tiled global
  accumulators are cross-cutting data-layout changes, not safe local
  optimizations. They need production-size grids and multi-day meteorology to
  establish a useful memory and locality benchmark.
- Asynchronous meteorological I/O needs an additional wind-field buffer and an
  audited thread-safe ecCodes/NetCDF read path.
- This source snapshot contains MPI conditionals but no `mpi_mod.f90`, and this
  host has no MPI Fortran compiler or launcher.
- This host has no CUDA, OpenMP target-offload, or Fortran GPU toolchain.
  Its integrated Apple GPU is exposed through Metal, which this Fortran build
  does not target.

Implementing or claiming the distributed and accelerator paths without their
missing source layer, toolchains, production inputs, and hardware validation
would not produce a research-grade result.

## Artifacts

- Original source snapshot:
  `baselines/flexpart-11.1-original/source_before_optimization.tar.gz`
- Final source snapshot: `candidates/final-current/source_after_optimization.tar.gz`
- Final regression artifacts: `candidates/final-current/`
- Exact/tolerant comparison: `candidates/final-current-comparison.json`
- Invariant report: `candidates/final-current-invariants.json`
- Final interleaved benchmark: `benchmarks/final-current/`
