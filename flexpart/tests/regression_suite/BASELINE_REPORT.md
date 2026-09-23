# FLEXPART 11.1 pre-optimization baseline

Recorded on 2026-07-20 using the unmodified local meter- and eta-coordinate
executables on Apple M1 Max/macOS.

## Outcome

- 22 of 22 baseline cases completed successfully.
- The model produced 243 output files.
- The recorded baseline occupies approximately 96 MB.
- Total model wall time across the suite was 124.49 seconds.
- A second clean execution also completed 22 of 22 cases.
- 17 cases reproduced every scientific array and binary output exactly.
- 5 cases showed existing run-to-run variability despite unchanged code.

The authoritative artifacts are under
`baselines/flexpart-11.1-original/`. Each case contains its exact option
files, pathname file, output files, complete log, executable hash, input
hashes, output hashes, and per-variable NetCDF fingerprints and statistics.

## Coverage

The cases cover meter and eta coordinates, forward and backward transport,
Gaussian and CBL turbulence, mesoscale turbulence, convection, subgrid
terrain, aerosol settling, wet and dry deposition, gas scavenging, nested
output, receptors, fluxes, particle output, age spectra, multiple releases
and species, mass concentration, mixing ratio, plume trajectories,
quasi-Lagrangian mode, radioactive decay, OH chemistry, restart write/read,
legacy binary output, and one through eight OpenMP threads.

The all-physics single-thread case (`05`) is bitwise reproducible. Its gridded
output has non-zero aerosol and gas wet/dry deposition, three non-zero species
concentration fields, nested output, flux output, receptor output, and particle
properties.

The decay case releases 1 kg with a 1,800-second half-life. After the
3,600-second simulation, recorded live-particle mass is 0.25000016 kg, matching
two half-lives.

The OH chemistry case records:

- live-particle mass: 0.97041464 kg;
- wet-deposited mass: 0.02822064 kg;
- inferred OH chemical loss: 0.00136472 kg.

## Existing nondeterminism

The unchanged-code duplicate differed in:

- `06_all_physics_four_threads`;
- `09_age_flux_multirelease` (two threads);
- `15_quasilagrangian_particles` (one thread);
- `20_binary_full_physics`;
- `22_parallel_stress` (eight threads).

This is baseline behavior, not a result of future optimization. The OpenMP
cases are consistent with thread-associated random-number streams and dynamic
particle scheduling. The quasi-Lagrangian and binary cases demonstrate that
thread count alone is not the only source of variability. The complete
variable-level differences are recorded in
`baselines/flexpart-11.1-original/reproducibility_report.json`.

Future changes should be required to match the other 17 cases exactly.
Differences in the five unstable cases must be reviewed using mass
conservation and distribution-level metrics; they should not be accepted
merely because those cases were already nondeterministic.

## Constraints discovered while constructing the suite

- Path entries longer than approximately 120 characters are truncated by the
  model, so the runner uses short relative paths.
- Receptor calculation has a hard-coded 4,000-particle kernel limit; receptor
  cases use spatially distributed releases to remain within it.
- Limited-area chemistry arrays are allocated at meteorological-grid
  dimensions. The global 360 by 180 OH climatology therefore has to be cropped
  to the 11 by 17 sample domain before it can be read safely.
- The three-hour meteorological sample cannot validate nested meteorological
  input, emissions, realistic domain-filling operation, multi-day chemistry,
  or global-grid I/O.

## Reuse

After rebuilding changed executables:

```bash
cd flexpart/tests/regression_suite
.venv/bin/python run_suite.py \
  --output candidates/after-change-001 \
  --executable-root ../../src

.venv/bin/python compare_suite.py \
  baselines/flexpart-11.1-original \
  candidates/after-change-001
```

The comparator ignores only volatile NetCDF creation-history attributes. It
compares dimensions, variable types, masks, character data, and every numeric
value, while also reporting optional floating-point tolerance results.
