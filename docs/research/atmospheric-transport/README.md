# FLEXPART, HYSPLIT, and open-source atmospheric transport models

Research snapshot: 2026-07-20.

## What “all” means here

No public bibliography can guarantee every paper that has ever used either
model. Model names appear in methods, supplements, theses, reports, datasets,
and papers whose titles do not name the software. This archive therefore uses
three layers:

1. official documentation, repositories, version histories, and publication
   lists;
2. a curated set of model-description, method, validation, and major extension
   papers;
3. reproducible OpenAlex full-text searches, with compact title-match files and
   broad full-text-mention files.

The broad index contains 17,629 deduplicated works: 4,309 FLEXPART search
results and 14,017 HYSPLIT search results. Of these, 292 and 404 respectively
name the model in the title (or use a defining expansion of its name).
Full-text results are intentionally inclusive and will contain incidental
mentions and occasional false positives.

## Bottom line

- **FLEXPART 11.1 is still the strongest general-purpose open-source default**
  for forward/backward Lagrangian transport, source–receptor sensitivities,
  boundary-layer turbulence, convection, deposition, decay, and simple
  chemistry from local to global scales.
- **HYSPLIT 5.4 is extremely capable and operationally mature, but is not
  open-source software in the usual sense.** NOAA distributes executables and
  documentation publicly; the full Linux source requires registration, is
  supplied at NOAA’s discretion, and is limited to non-commercial use.
- There is **no single newer open-source model that supersedes both**. MPTRAC is
  the clearest modern HPC/GPU Lagrangian complement; SILAM is more capable for
  chemistry and data assimilation; QES-Plume and GRAMM/GRAL are stronger for
  microscale urban/complex-terrain dispersion; FALL3D is specialized for
  volcanic ash and related aerosols; AgPaDS is a new high-particle-count,
  domain-specific GPU model.

## FLEXPART documentation

### Current core

- [Project home](https://www.flexpart.eu/)
- [FLEXPART 11 documentation](https://flexpart.img.univie.ac.at/docs/) —
  installation, compilation, configuration, linear chemistry, execution,
  outputs, particle transport, particle-property evolution, examples,
  containers, and troubleshooting.
- [Source repository](https://gitlab.phaidra.org/flexpart/flexpart) — GPL-3.0.
- [Release roadmap](https://www.flexpart.eu/roadmaps.html) — all core releases
  and important changes. The latest listed release is 11.1 (2025-08-11).
- [Version 11 containers](https://flexpart.img.univie.ac.at/docs/containers.html)
- [User support and training](https://www.flexpart.eu/usersupport.html)
- [Pre- and post-processing tools](https://www.flexpart.eu/processing.html)
- [flex_extract documentation](https://flexpart.img.univie.ac.at/flexextract/)
  for retrieving and preparing ECMWF meteorology.

### Earlier manuals and model family

The [FLEXPART 11 documentation home](https://flexpart.img.univie.ac.at/docs/)
links the version-specific documentation for FLEXPART 10.4, 9, 8, 6.2, 3.1,
and 1. The [release roadmap](https://www.flexpart.eu/roadmaps.html) also
documents FLEXTRA and FLEXPART-WRF releases.

The [FLEXPART family page](https://www.flexpart.eu/family.html) collects
meteorological-driver and Earth-system variants:

- FLEXPART-WRF
- FLEXPART-AROME
- FLEXPART-COSMO
- FLEXPART-HIRLAM / Enviro-HIRLAM
- FLEXPART-NorESM/CAM
- FLEXTRA, the trajectory-model predecessor

Related tools include flex_extract, FLEXDUST, FLEXINVERT, and community
post-processing packages listed on the processing page.

## FLEXPART core and extension papers

The compact curated list is also available as
[`core_model_papers.csv`](core_model_papers.csv).

### Core model and methods

- Stohl, Hittenberger, and Wotawa (1998),
  [validation against large-scale tracer experiments](https://doi.org/10.1016/S1352-2310(98)00184-8).
- Seibert and Frank (2004),
  [source–receptor matrices in backward mode](https://doi.org/10.5194/acp-4-51-2004).
- Stohl et al. (2005),
  [FLEXPART version 6.2](https://doi.org/10.5194/acp-5-2461-2005).
- Forster, Stohl, and Seibert (2007),
  [convective-transport parameterization](https://doi.org/10.1175/JAM2470.1).
- Hittmeir, Philipp, and Seibert (2018),
  [conservative interpolation of extensive quantities](https://doi.org/10.5194/gmd-11-2503-2018).
- Pisso et al. (2019),
  [FLEXPART version 10.4](https://doi.org/10.5194/gmd-12-4955-2019).
- Bakels et al. (2024),
  [FLEXPART version 11](https://doi.org/10.5194/gmd-17-7595-2024).

### Inversion, deposition, dust, and CTM use

- Thompson and Stohl (2014),
  [FLEXINVERT](https://doi.org/10.5194/gmd-7-2223-2014).
- Eckhardt et al. (2017),
  [backward source–receptor matrices for deposited mass](https://doi.org/10.5194/gmd-10-4605-2017).
- Groot Zwaaftink et al. (2017),
  [FLEXDUST / Icelandic dust emission and transport](https://doi.org/10.5194/acp-17-10865-2017).
- Groot Zwaaftink et al. (2018),
  [FLEXPART 8-CTM-1.1 and three-dimensional methane](https://doi.org/10.5194/gmd-11-4469-2018).

### Major variants

- Brioude et al. (2013),
  [FLEXPART-WRF 3.1](https://doi.org/10.5194/gmd-6-1889-2013).
- Cassiani et al. (2016),
  [FLEXPART-NorESM/CAM](https://doi.org/10.5194/gmd-9-4029-2016).
- Verreyken, Brioude, and Evan (2019),
  [FLEXPART-AROME 1.2.1 turbulence](https://doi.org/10.5194/gmd-12-4245-2019).
- Katharopoulos et al. (2022),
  [FLEXPART-COSMO in the turbulence “grey zone” at 1 km](https://doi.org/10.1007/s10546-022-00728-3).
- Foreback et al. (2024),
  [FLEXPART with Enviro-HIRLAM input](https://doi.org/10.1080/20964471.2024.2316320).

## HYSPLIT documentation

- [NOAA HYSPLIT home](https://www.arl.noaa.gov/hysplit/)
- [Get/run HYSPLIT](https://www.arl.noaa.gov/hysplit/getrun-hysplit/)
- [HYSPLIT 5.4 HTML user guide](https://www.ready.noaa.gov/hysplitusersguide/)
- [HYSPLIT 5.4 PDF user guide](https://www.arl.noaa.gov/documents/reports/hysplit_user_guide.pdf)
- [Tutorial collection](https://www.ready.noaa.gov/HYSPLIT_Tutorials.php)
- [Basic tutorial](https://www.ready.noaa.gov/documents/Tutorial/html/index.html)
- [Version/update history](https://www.arl.noaa.gov/hysplit/hysplit-model-updates/)
- [Official model publications and meteorological-data information](https://www.arl.noaa.gov/hysplit/hysplit-publications-meteorological-data-information/)
- [Official application-reference list](https://www.arl.noaa.gov/hysplit/hysplit-references/)
- [Linux source-request terms](https://www.ready.noaa.gov/HYSPLIT_linux.php)
- [Public Windows trial/package information](https://www.ready.noaa.gov/HYSPLIT_hytrial.php)
- [READY web interface](https://www.ready.noaa.gov/HYSPLIT.php)

The guide marked 5.4 was last revised in April 2025. The model-update page
provides release notes for 5.4 and earlier 5.x versions.

### Licensing caveat

HYSPLIT should be described as **publicly available software with restricted
source**, not as open source. NOAA’s Linux download page says the source is
provided only to registered users, on a discretionary basis, for
non-commercial use. The public Windows package includes executables, scripts,
examples, and selected utility source, but not the complete model source.

## HYSPLIT core and method papers

- Draxler (1992),
  [Hybrid Single-Particle Lagrangian Integrated Trajectories (HY-SPLIT), version 3.0: user’s guide and model description](https://repository.library.noaa.gov/view/noaa/31300).
- Draxler and Hess (1997),
  [Description of the HYSPLIT_4 modeling system, NOAA ARL-224](https://www.arl.noaa.gov/wp_arl/wp-content/uploads/documents/reports/arl-224.pdf).
- Draxler and Hess (1998),
  [overview of HYSPLIT_4 trajectories, dispersion, and deposition](https://www.arl.noaa.gov/documents/reports/MetMag.pdf).
- Draxler (1999),
  [HYSPLIT4 user’s guide, NOAA ARL-230](https://www.arl.noaa.gov/wp_arl/wp-content/uploads/documents/reports/arl-230.pdf).
- Draxler (2007),
  [global Eulerian-module methodology](https://doi.org/10.1016/j.atmosenv.2006.08.052).
- Hegarty et al. (2013),
  [controlled-tracer evaluation of HYSPLIT, STILT, and FLEXPART](https://doi.org/10.1175/JAMC-D-13-0125.1).
- Stein et al. (2015),
  [NOAA’s HYSPLIT atmospheric transport and dispersion modeling system](https://doi.org/10.1175/BAMS-D-14-00110.1).
- Ngan, Stein, and Draxler (2015),
  [inline WRF–HYSPLIT coupling](https://doi.org/10.1175/JAMC-D-14-0247.1).
- Chai et al. (2017),
  [volcanic-ash data assimilation](https://doi.org/10.5194/acp-17-2865-2017).
- Rolph, Stein, and Stunder (2017),
  [Real-time Environmental Applications and Display sYstem (READY)](https://doi.org/10.1016/j.envsoft.2017.06.025).
- Loughner et al. (2021),
  [STILT features incorporated into HYSPLIT 5](https://doi.org/10.1175/JAMC-D-20-0158.1).

The official NOAA export in this directory contains 31 model-publication
entries and 162 application-reference entries. NOAA’s model list itself
contains a few duplicates; they are preserved so the CSV remains traceable to
the source pages.

## Searchable paper indexes

| File | Rows | Purpose |
|---|---:|---|
| [`flexpart_title_matches.csv`](flexpart_title_matches.csv) | 292 | Compact set naming FLEXPART in the title |
| [`hysplit_title_matches.csv`](hysplit_title_matches.csv) | 404 | Compact set naming HYSPLIT in the title |
| [`flexpart_openalex.csv`](flexpart_openalex.csv) | 4,309 | Broad OpenAlex full-text search |
| [`hysplit_openalex.csv`](hysplit_openalex.csv) | 14,017 | Broad OpenAlex full-text search |
| [`combined_openalex_deduplicated.csv`](combined_openalex_deduplicated.csv) | 17,629 | DOI/title-year deduplicated union |
| [`hysplit_noaa_official_bibliography.csv`](hysplit_noaa_official_bibliography.csv) | 193 | Exact export of NOAA’s two official lists |
| [`openalex_search_summary.json`](openalex_search_summary.json) | — | Search method and counts |

Each OpenAlex row includes model, relevance tier, year, title, authors, source,
work type, DOI, landing page, open-access status, citation count, and OpenAlex
ID. Citation count is useful for sorting, not for judging scientific quality.

Rebuild with:

```sh
# Full network refresh:
python3 scripts/build_transport_literature_index.py

# Or regenerate filters and the deduplicated union without calling OpenAlex:
python3 scripts/build_transport_literature_index.py --from-existing

python3 scripts/collect_hysplit_official_bibliography.py
```

## Newer or more capable open-source options

“More capable” is workload-specific. The table separates direct Lagrangian
alternatives from broader or specialist models.

| Model | Best use | Capability advantage | License / status | Important limitation |
|---|---|---|---|---|
| [MPTRAC](https://github.com/slcs-jsc/mptrac) | Free-tropospheric and stratospheric trajectory/dispersion ensembles | Modern MPI, OpenMP, OpenACC, and GPU implementation; large particle ensembles; diffusion, convection, sedimentation, chemistry, and deposition modules | GPL-3.0; latest tagged release 3.1 (2026) | Not a universal FLEXPART replacement; its center of gravity is the free troposphere/stratosphere rather than every boundary-layer and operational application |
| [QES-Plume](https://github.com/UtahEFD/QES-Public) | Urban, building, vegetation, and complex-terrain boundary layers | GPU/CUDA stochastic Lagrangian dispersion coupled to QES-Winds and QES-Turb; can use diagnostic, RANS, or LES winds | GPL-3.0 | Microscale specialist, not regional/global; repository notes no automated QES-Plume tests |
| [GRAMM/GRAL](https://gral.tugraz.at/) | Local-to-urban regulatory dispersion over complex terrain | Mesoscale GRAMM wind fields plus building-resolving GRAL Lagrangian dispersion and GUI | GPL-3.0; [source organization](https://github.com/GralDispersionModel); [manuals](https://gral.tugraz.at/download/documentations/) | Not intended as a global long-range source–receptor replacement |
| [SILAM](https://silam.fmi.fi/) | Operational air quality, chemistry, source inversion, and emergency response | Hybrid Eulerian/Lagrangian framework, detailed chemistry and physical transformation modules, global-to-sub-kilometre simulations, and variational/ensemble data assimilation | GPL-3.0 [source](https://github.com/fmidev/silam-model) | Broader chemistry-transport system, not a drop-in LPDM replacement |
| [FALL3D](https://fall3d-suite.gitlab.io/fall3d/) | Volcanic ash, tephra, aerosols, and radionuclides | Scalable Eulerian transport and deposition with source-specific physics | GPL-3.0 [source](https://gitlab.com/fall3d-suite/fall3d) | Eulerian and source-specialized |
| [AgPaDS](https://doi.org/10.5194/gmd-19-4857-2026) | Agricultural pathogen dispersal across global crop landscapes | New CUDA/C++ model with live 3-D visualization and millions of particles; paper reports up to three orders of magnitude speedup over HYSPLIT | MIT-licensed [code archive](https://doi.org/10.5281/zenodo.18362547) | Very new (2026) and domain-specific; validation breadth is much smaller |
| [TRACMASS](https://github.com/TRACMASS/Tracmass) | Offline parcel trajectories, pathways, and streamfunctions in atmosphere or ocean | Efficient forward/backward trajectory analysis across several circulation-model grids | MIT | Particle tracking rather than a full dispersion/deposition system; repository says earlier subgrid turbulence parameterizations are not yet available in v7 |

### Primary papers for alternatives

- MPTRAC 2.2:
  [model description and performance](https://doi.org/10.5194/gmd-15-2731-2022);
  MPTRAC 2.6:
  [GPU optimizations](https://doi.org/10.5194/gmd-17-4077-2024);
  [diabatic advection](https://doi.org/10.5194/gmd-17-4467-2024);
  [JOSS software paper](https://doi.org/10.21105/joss.08177).
- QES-Plume:
  [GPU-accelerated microscale Lagrangian model](https://doi.org/10.5194/gmd-16-5729-2023).
- SILAM:
  [Eulerian atmospheric-dispersion core](https://doi.org/10.5194/gmd-8-3497-2015);
  [NO2 and O3 data assimilation](https://doi.org/10.5194/gmd-8-191-2015).
- FALL3D 8.0:
  [model description](https://doi.org/10.5194/gmd-13-1431-2020).
- AgPaDS 1.0:
  [GPU agricultural pathogen dispersion](https://doi.org/10.5194/gmd-19-4857-2026).
- TRACMASS 6.0:
  [trajectory code](https://doi.org/10.5194/gmd-10-1733-2017).
- STILT:
  [original formulation](https://doi.org/10.1029/2002JD003161),
  [STILT-R 2](https://doi.org/10.5194/gmd-11-2813-2018),
  [X-STILT](https://doi.org/10.5194/gmd-11-4843-2018), and
  [STILT-NOx](https://doi.org/10.5194/gmd-16-6161-2023).

### Source-available models with licensing caveats

- [STILT](https://github.com/uataq/stilt) is highly relevant for receptor
  footprints and trace-gas inversions, and its documentation calls it open
  source. However, the current repository does not expose a top-level software
  license. Treat reuse rights as unclear until the maintainers clarify them.
- HYSPLIT’s full source has the restrictions described above.

Models whose code is only “available on request,” limited to a consortium, or
published without a verifiable open-source license were not placed in the
open-source shortlist.

## Selection guide

- Choose **FLEXPART 11.1** for a defensible, broad, open-source LPDM baseline,
  especially for backward sensitivities, deposition, and established
  atmospheric source–receptor work.
- Add or benchmark **MPTRAC 3.1** when particle count, GPU throughput, or
  upper-troposphere/stratosphere work dominates.
- Choose **SILAM** when chemistry, air-quality forecasting, or data assimilation
  matters more than staying with a pure LPDM.
- Choose **QES-Plume** or **GRAMM/GRAL** for building-resolving or
  complex-terrain microscale work.
- Choose **FALL3D** for volcanic ash/tephra and related aerosol hazards.
- Treat **AgPaDS** as a promising specialist for agricultural bioaerosols, not
  yet as a general-purpose replacement.
