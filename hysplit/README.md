# HYSPLIT local research archive

Snapshot assembled on 2026-07-20.

## Public NOAA code

The `code/` directory contains every HYSPLIT-named public repository found in
NOAA Air Resources Laboratory's GitHub organization at the snapshot date:

| Repository | Purpose | Commit |
|---|---|---|
| `utilhysplit` | Construct HYSPLIT inputs and process outputs | `1a428ee6af5303670ac4045aa00dacc8b1001c53` |
| `hysplitplot` | Python graphics | `5f91ceb498ebfcf2bc5409db06cf4e349d3623b0` |
| `hysplitdata` | Python data model and readers | `7a76e96a4911e91077b052251e1b5665b5306fc4` |
| `hysplit_data2arl` | Meteorological-data converters to ARL packed format | `5f66398aa35a4c0830729ea47d91dfb92fe9ec11` |
| `hysplit_gmm` | Gaussian mixture modeling utilities | `4af3981b9f910278817c25b7316f026d71a04d69` |
| `hysplit_asheval_notebooks` | Volcanic-ash evaluation notebooks | `213b57c38f6e7c6a01c53b8c3b9571db599ccbb0` |

Origin: <https://github.com/noaa-oar-arl>

These are public support, conversion, analysis, and evaluation projects. They
are not the complete Fortran HYSPLIT transport/dispersion core.

## Model executable and full source

NOAA gates the Mac/Windows model packages behind an email-and-use-agreement
form. Full Linux source additionally requires registration and discretionary
SVN access. No identity or agreement acceptance was fabricated during this
download.

See [`model/SOURCE_ACCESS.md`](model/SOURCE_ACCESS.md) for the exact research
access steps and where to place the resulting package or checkout.

## Research material

See [`docs/README.md`](docs/README.md) for manuals, papers, and reading order.

