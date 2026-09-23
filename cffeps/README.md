# CFFEPS 4.1 research integration

This directory preserves the official CFFEPS 4.1 source and provides a small
portable driver for the weather application. The upstream standalone program
requires Environment and Climate Change Canada's GEM/FST `librmn` and vGrid
libraries. The portable driver calls the unmodified CFFEPS calculation modules
but accepts already-sampled atmospheric profiles, making NOAA GFS input
possible without changing the scientific kernel.

## Provenance

- Release: CFFEPS v4.1
- Source: <https://github.com/jackenvcan/cffeps/releases/tag/v4.1>
- DOI: <https://doi.org/10.5281/zenodo.15305591>
- Archive: `upstream/cffeps-4.1.tar.gz`
- Archive SHA-256: `8aac1918bb4c8897c1e07166939d96d1a3470ddf43dca7d66200e96eed7a503a`
- License: LGPL-2.1-or-later; see `LICENSE`

The extracted `upstream/cffeps-4.1` tree is intentionally unchanged. Local
integration code lives outside it. The portable input format and deviations
from the original FST-driven executable are documented in `docs/PORTABLE_DRIVER.md`.

## Build and smoke test

```bash
make -C cffeps -f Makefile.portable clean all
make -C cffeps -f Makefile.portable smoke
```

The production container build is:

```bash
docker build -f cffeps/containers/Dockerfile -t weatherapp-cffeps:4.1 cffeps
```

This integration is research software. It is not an official ECCC forecast
product and must not be used as an emergency-management forecast.
