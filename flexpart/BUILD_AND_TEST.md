# FLEXPART build and smoke-test record

Date: 2026-07-20  
Machine: Apple M1 Max, arm64, macOS  
Source tree: FLEXPART 11.1 release source (runtime banner: `Version 11.0 (2023-07-11)`)

## Result

Both model variants compiled as native arm64 executables and completed a one-hour,
two-thread smoke simulation:

| Executable | Coordinate system | Result | Model runtime |
| --- | --- | --- | ---: |
| `src/FLEXPART` | meter | passed | 1.439 s |
| `src/FLEXPART_ETA` | eta | passed | 1.484 s |

Each run:

- detected ECMWF meteorology on an 11 by 17 grid with 138 hybrid levels;
- released 1,000 AIRTRACER particles at 5.0 E, 50.5 N and 50 m AGL;
- integrated from 2021-09-05 00:00 to 01:00 UTC;
- finished with 1,000 live particles and no terminated particles;
- printed `CONGRATULATIONS: YOU HAVE SUCCESSFULLY COMPLETED A FLEXPART MODEL RUN!`;
- wrote a CF-1.6 NetCDF concentration field with dimensions
  `time=1, longitude=10, latitude=16, height=4`;
- produced non-zero AIRTRACER concentrations (including 27.81426 and
  3.973465 ng m-3).

This is an end-to-end execution and I/O smoke test, not a scientific validation
or comparison against a reference solution. Turbulence, convection, and
deposition are intentionally disabled in the compact test configuration.

## Toolchain

The build used:

```text
gcc / gfortran 16.1.0
ecCodes 2.48.0
NetCDF-C 4.10.1
NetCDF-Fortran 4.6.3
HDF5 2.1.1
OpenMP via libgomp
```

`netcdf-fortran` was added with Homebrew because the machine initially had only
the NetCDF C library.

## macOS arm64 build support

`src/makefile_gfortran` now accepts `arch=macos-arm64`. This branch:

- uses `-mcpu=apple-m1` instead of the x86-only `-march=native`;
- omits the x86-only `-mcmodel=large`;
- uses Apple's supported linker spelling, `-Wl,-rpath,<path>`.

The build commands were:

```bash
export CPATH="$(brew --prefix eccodes)/include:$(brew --prefix netcdf-fortran)/include:$(brew --prefix netcdf)/include:$(brew --prefix hdf5)/include"
export LIBRARY_PATH="$(brew --prefix eccodes)/lib:$(brew --prefix netcdf-fortran)/lib:$(brew --prefix netcdf)/lib:$(brew --prefix hdf5)/lib"

make -C src -f makefile_gfortran cleanall arch=macos-arm64
make -C src -j4 -f makefile_gfortran eta=no arch=macos-arm64 FC=gfortran
make -C src -j4 -f makefile_gfortran arch=macos-arm64 FC=gfortran
```

The resulting executable checksums are:

```text
7a69668e3c3a89f8416fcbc48d1576e39ed1b87b22a3a49cdcba5f41a4d9cf68  src/FLEXPART
efb03ba031244e0df1a7bde5b4fae2afdd94ce75b5762a54c49760eff07edfcc  src/FLEXPART_ETA
```

## Test data and commands

The upstream Vienna EC2009 test-data server was unreachable from this machine.
The smoke test therefore uses the compact deterministic ECMWF files published
in the public
[`tcarion/flexpart_data`](https://github.com/tcarion/flexpart_data/tree/main/tests/input/deterministic)
repository. They cover the Netherlands at 0.2-degree resolution:

```text
ba3ea3561b96577e97037398944debdb869b07137761f39169fb8d2b4639f790  ENH21090500
6653d5150a3d19dca3189297db9c6a699e7e9427a1f8b16aafbbd3a53bb659cc  ENH21090501
3fe94984cd5704aa620e3fd0cb678d30eec4d2963d8b08c93e57604a5f7d9433  ENH21090502
```

To repeat both tests:

```bash
cd tests/smoke_standard
ulimit -s unlimited 2>/dev/null || true
OMP_NUM_THREADS=2 ../../src/FLEXPART pathnames

cd ../smoke_eta
ulimit -s unlimited 2>/dev/null || true
OMP_NUM_THREADS=2 ../../src/FLEXPART_ETA pathnames
```

Outputs are under `tests/smoke_standard/output` and `tests/smoke_eta/output`.
The warnings about a missing satellite file and missing `RECEPTORS` file are
non-fatal because neither feature is used by this test case.
