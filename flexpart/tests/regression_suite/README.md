# FLEXPART scientific regression suite

This suite records the exact inputs and complete outputs of the unmodified local
FLEXPART 11.1 executables before performance-oriented changes are made.

The completed baseline results and reproducibility findings are summarized in
[`BASELINE_REPORT.md`](BASELINE_REPORT.md).

The 22 cases use the bundled three-hour, 0.2-degree ECMWF sample over the
Netherlands. They cover:

- meter and eta vertical-coordinate executables;
- forward and backward transport;
- Gaussian, mesoscale, and skewed CBL turbulence;
- convection and subgrid terrain effects;
- aerosol settling plus wet and dry deposition;
- gas wet and dry deposition;
- multiple species and release geometries;
- concentration, mixing-ratio, plume, receptor, flux, particle, nested-grid,
  binary, and NetCDF output;
- age spectra, quasi-Lagrangian mode, radioactive decay, OH chemistry;
- restart write/read;
- one-, two-, four-, and eight-thread execution.

The compact meteorology cannot validate nested meteorological input, emissions,
domain-filling production behavior, multi-day chemistry, or large global-grid
I/O. Those require additional meteorological and ancillary datasets.

For the OH-chemistry case, the runner records cropped August and September OH
fields over the compact meteorological domain. FLEXPART allocates reagent arrays
at the meteorological-grid dimensions, so passing the bundled 360 by 180 global
OH field directly to this 11 by 17 limited-area run would overrun those arrays.
The case uses the monthly-mean field (`PHOURLY=0`) because the available
00:00–01:00 UTC meteorology is nighttime over the Netherlands; hourly
photolysis modulation would intentionally reduce OH loss to zero.

## Install the comparison dependency

```bash
cd flexpart/tests/regression_suite
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

## Create a candidate run

The original baseline is under `baselines/flexpart-11.1-original`. After changing
the code and rebuilding both executables:

```bash
.venv/bin/python run_suite.py \
  --output candidates/after-change-001 \
  --executable-root ../../src
```

Every case directory contains:

- `inputs/`: the exact option files used;
- `pathnames`: the exact input/output/meteorology paths;
- `outputs/`: all model-produced files;
- `run.log`: complete standard output and error;
- `manifest.json`: executable, input, output, and scientific-array hashes plus
  runtime and OpenMP settings.

The top-level `suite_manifest.json` additionally records source hashes,
meteorological input hashes, the platform, and the toolchain.

## Compare with the original

```bash
.venv/bin/python compare_suite.py \
  baselines/flexpart-11.1-original \
  candidates/after-change-001
```

NetCDF container SHA-256 values are recorded but not used as the only test,
because the files contain a volatile creation-history attribute. The comparator
checks every dimension, missing-value mask, and variable value. It reports:

- `EXACT`: every scientific value is identical;
- `TOLERANT`: numeric differences remain within `rtol=1e-6`, `atol=1e-12`;
- `CHANGED`: a structural, categorical, binary, or above-tolerance change.

The tolerances can be overridden with `--rtol` and `--atol`. Stochastic
multi-threaded cases may not remain bitwise identical if particle scheduling or
random-number assignment changes; any such difference must be reviewed using
mass conservation and distribution-level scientific criteria rather than being
accepted automatically.

For those stochastic cases, validate that the candidate used identical inputs,
produced the same output inventory, introduced no non-finite values, and
preserved every scientific array in `totals.nc`:

```bash
.venv/bin/python validate_invariants.py \
  baselines/flexpart-11.1-original \
  candidates/after-change-001
```

## Benchmark CPU scaling

`benchmark_suite.py` derives a compute-heavy case from the regression suite's
all-physics stress case, increases its particle population, and interleaves
variants to reduce cache, temperature, and run-order bias:

```bash
.venv/bin/python benchmark_suite.py \
  --variant original=/tmp/flexpart-original/src \
  --variant optimized=../../src \
  --particles 1000000 \
  --threads 1 2 4 8 16 \
  --repeats 3 \
  --output benchmarks/original-vs-optimized
```

The benchmark's wall clock excludes case preparation and output
fingerprinting. Its manifest records every individual run, executable hash,
median/minimum/maximum timing, and scaling from the first requested thread
count.
