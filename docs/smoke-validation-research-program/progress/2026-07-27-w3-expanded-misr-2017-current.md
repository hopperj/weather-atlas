# W3 expanded MISR/MINX inventory, 2017 to current

**Date:** 2026-07-27  
**Requested interval:** 2017-01-01 through 2026-07-27  
**Geography:** conservative Canadian-interior screening boxes  
**Status:** observation and source-area candidate screen complete; central
cohort, meteorology, causal CFFEPS histories, and independent review pending  
**FLEXPART output opened:** no

Publication-facing interpretation and draft manuscript language are in the
[expanded MISR publication update](../w3-expanded-misr-publication-update-2026-07-27.md).

## Executive finding

The original W3 pool was unnecessarily restricted to eight seeded MISR orbits
from each of 2017 and 2018. The live NASA MERLIN catalogue was therefore
queried exhaustively from 2017 through the current date, and every
Canadian-interior plume file returned by the provider was downloaded.

The expanded result is:

| Stage | Count |
|---|---:|
| Provider records returned | 9,976 |
| Canadian-interior MISR orbits | 78 |
| Downloaded MINX plume files | 772 |
| Band-independent fire-plume families | 388 |
| Height-blind selections | 386 |
| Observation-qualified fire-overpasses | 109 |
| Fire M3 assignments with complete state/fuel | 109 |
| Independent MCD64A1 area-qualified candidates | 88 |
| Distinct MISR orbits represented by the 88 | 37 |
| Formal minimum | 10 independent fire-overpasses |

The observation sample shortage is therefore resolved at the candidate-pool
stage. Formal W3 execution is **not** yet authorized. The 88 records are
source- and area-qualified candidates, not 88 proven-independent fires and
not 88 completed FLEXPART experiments.

## Archive coverage is not continuous through the current year

The date query was complete, but the public MERLIN Plume Height Project is not
a continuously processed annual product.

NASA's [MERLIN release description](https://asdc.larc.nasa.gov/news/merlin-a-new-tool-for-misr-plume-height-project-access-and-analysis)
and [MERLIN user guide](https://asdc.larc.nasa.gov/documents/misr/guide/MERLIN_User_Guide.pdf)
state that the comprehensive public database contains globally digitizable
plumes for 2008–2011 and the summers of 2017 and 2018. The live endpoint
confirmed that limitation:

| Year | Provider records | Canadian-interior orbits |
|---|---:|---:|
| 2017 | 5,030 | 51 |
| 2018 | 4,946 | 27 |
| 2019 | 0 | 0 |
| 2020 | 0 | 0 |
| 2021 | 0 | 0 |
| 2022 | 0 | 0 |
| 2023 | 0 | 0 |
| 2024 | 0 | 0 |
| 2025 | 0 | 0 |
| 2026 through July 27 | 0 | 0 |

Zero records after 2018 mean “not present in MERLIN,” not “MISR did not fly”
or “no fires occurred.”

NASA separately describes a
[Canadian and Alaskan Wildfire Smoke collection](https://asdc.larc.nasa.gov/project/MISR_Wildfire_Research/MISR_Canadian_and_Alaskan_Wildfire_Smoke_1)
covering May–September 2016–2019. Its collection page exposes metadata and a
DOI but currently does not expose downloadable file links through MERLIN,
CMR, or the ASDC direct-download hierarchy tested in this run. Its 2019 data
were therefore not silently treated as absent; they are an identified
provider-access follow-up.

Later public MINX case studies also exist, including two California fires from
the [2022 CalFiDE field campaign](https://asdc.larc.nasa.gov/micro-article/misr-observations-of-wildfire-smoke-plumes-during-the-calfide-field-campaign).
Those are not a systematic Canadian archive and cannot be mixed into the
Canadian Fire M3/CFFEPS cohort without a new geography and source-input
protocol.

Raw MISR imagery is available after 2018, but producing new plume-height
observations requires manual or independently reviewed MINX processing. Raw
imagery and an automatically generated plume-height archive are not
interchangeable.

## Acquisition method

Provider endpoint:

```text
https://l0dup05.larc.nasa.gov/merlin/merlin/query/
```

The query covered each calendar year separately from 2017-01-01 through
2026-07-27. Empty annual responses were preserved as checksummed catalogue
artifacts.

The geographic availability screen used the pre-existing conservative
Canadian-interior rectangles:

| Region | West | South | East | North |
|---|---:|---:|---:|---:|
| British Columbia interior | -128 | 49 | -114 | 60 |
| Prairies | -114 | 49 | -95 | 60 |
| Central/east | -95 | 45 | -57 | 57 |
| Territories interior | -136 | 60 | -102 | 70 |

This is a reproducible availability screen, not a national boundary. It
deliberately excludes coastal and border ambiguity.

All 78 qualifying orbits were retained. The former deterministic
eight-orbits-per-year truncation was disabled. All 772 referenced text files
were downloaded from the provider host, for a total of 65,274,882 bytes.
Existing files were reused only after checksum calculation.

## Unit of observation

The expanded analysis distinguishes:

1. **MISR orbit:** one satellite pass;
2. **MINX band file:** red- or blue-band output for a delineated plume;
3. **plume family:** the red/blue pair after removing the band identifier; and
4. **fire-overpass candidate:** one plume family observed in one orbit.

The 772 files form 388 band-independent plume families in 78 orbits. Treating
an orbit as if it contained only one fire discarded scientifically useful
observations in the original inventory.

Multiple plume families in the same orbit still share acquisition time and
some meteorological errors. They must not be assumed statistically
independent. Among the final 88 source-area candidates, 37 distinct orbits
remain. A conservative one-candidate-per-orbit analysis can therefore still
exceed the formal sample minimum.

## Height-blind selection

File selection was completed before height extraction. The selector was
permitted to use:

- orbit, time, product version, and region identity;
- `Smoke` aerosol and `Polygon` geometry;
- provider `Good` or `Fair` categorical quality;
- raw row count, point identity, coordinates, and terrain validity;
- polygon geometry; and
- provider source coordinate and source-to-polygon distance.

It did not parse MINX height columns, provider median/max height summaries,
CFFEPS height, FLEXPART output, or model performance.

The frozen selection order was:

1. `Good` before `Fair`;
2. blue before red for land smoke;
3. greater raw retrieval support; and
4. region name.

No alternate-band fallback was allowed after extraction.

Blind selection result:

```text
plume families                         388
selected                               386
excluded                                 2
selected blue band                     374
selected red band                       12
selected provider quality Good         316
selected provider quality Fair          70
```

One excluded family had fewer than ten raw rows and `Poor` quality. The other
had only `Poor` candidates.

## Post-selection measurement rule

The same provisional rule used in the earlier 16-orbit analysis was applied
unchanged:

```text
primary field       wind-corrected MINX height
vertical reference  AGL = wind-corrected ASL - MINX terrain ASL
minimum AGL         250 m
minimum samples     10 valid retrievals per fire-overpass
summary             median of retained AGL values
```

Of 386 blind-selected plume families:

```text
observation-qualified       109
measurement-invalid         277
qualified by year      2017: 73
                       2018: 36
qualified unique orbits      39
```

The qualified cases contain 10–842 valid retrievals, with a median of 31.
Observed height magnitudes remain in the sealed observation ledger and were
not emitted into this report.

The 250 m floor remains provisional. Expanding the pool does not supply the
independent scientific justification that the earlier W3 review requested.

## Fire M3 source and state matching

The 109 observation-qualified records were matched to the complete annual
2017 and 2018 NRCan CWFIS Fire M3 archives using the unchanged
performance-blind rule:

```text
maximum source distance       5 km
maximum absolute time offset  3 hours
required state                finite FFMC, DMC, and DC
required fuel                 resolvable through the frozen FBP crosswalk
tie breaks                    distance, time offset, region, provider-row hash
```

All 109 received a complete Fire M3 source, fuel, and CFFDRS-state
assignment. No plume height or model value entered the match.

## Independent MCD64A1 burned area

The locally frozen MCD64A1 Collection 6.1 June–August archives were evaluated
with `mcd64a1_area_v2.yaml`. This configuration retains physically distinct
burn occurrences at the same grid cell on different dates while
deduplicating identical cross-month occurrences.

Results:

| Year | Observation-qualified | MCD64A1 area-qualified |
|---|---:|---:|
| 2017 | 73 | 55 |
| 2018 | 36 | 33 |
| **Total** | **109** | **88** |

The 21 area exclusions were:

- 17 with insufficient unambiguous pixels and no high-confidence pixel; and
- 4 with no spatiotemporally matched seed, insufficient unambiguous pixels,
  and no high-confidence pixel.

The 88 retained candidates span:

| Quantity | Result |
|---|---|
| Distinct MISR orbits | 37 |
| Distinct overpass dates | 34 |
| Weak area stratum | 5 |
| Moderate area stratum | 28 |
| Major area stratum | 55 |
| Central area range | 64.40–58,473.02 ha |
| Central area median | 1,524.08 ha |
| Fuel mappings represented | 12 |

The large pool also creates overlapping burned-area claims among nearby
sources. Ambiguous pixels were excluded from every event under the frozen
operator. The final central cohort needs an explicit physical-fire clustering
rule so multiple detections or plume polygons from one fire complex are not
treated as independent fires.

## Current interpretation

The original statement “only six of 16 overpasses are available” should no
longer be used as a description of observation availability.

The evidence now supports the following statement:

> An exhaustive performance-blind query of the public MERLIN archive found
> 388 Canadian-interior fire-plume families in 78 MISR orbits. Under the
> unchanged provisional measurement rule, 109 observations qualified; 88
> also had complete Fire M3 state/fuel assignments and independent MCD64A1
> burned area. These candidates span 37 distinct orbits, resolving the
> observation sample shortage while leaving central-cohort clustering,
> meteorological acquisition, causal emissions construction, and independent
> review incomplete.

## Historical GFS status

The full 88-case source-area pool spans 34 dates. A one-day-spin-up GDEX
inventory would require:

```text
57 GFS 00Z cycles
513 global 0.25-degree forecast files
108,144,052,343 estimated bytes
```

A full-pool transfer was intentionally stopped after discovery because a
formal central cohort has not yet been selected. Twelve complete raw files
entered the resumable cache, but no acquisition ledger was produced and they
are not counted as validated inputs. Four interrupted `.part` files were
removed.

Downloading meteorology for all 88 candidates is unnecessary. The next
scientific action is to freeze a sufficiently large, clustered,
performance-blind central cohort, then acquire and validate GFS only for that
cohort and declared reserves.

## Artifact inventory

Root:

```text
/Volumes/BigMrStorage/weatherapp_data/weather/derived/smoke/validation/
cohorts/w3-misr-merlin-2017-current-expanded-v1/
```

| Artifact | SHA-256 |
|---|---|
| Expanded vertical ledger | `b60e63d632ef62b13ba09868c800f019ed2d298a9193cca5fd9cad63fb7a2319` |
| Height-blind QA r1 | `13cc373ef3dc97077304bd7514b30d8d78edf859a217cccc8de8bd198e2b406c` |
| Sealed observation ledger r1 | `ddfc8900482c2ab9da2a0d8e6365401ef833a208fd78b2c807613d399f1faf9c` |
| Safe extraction audit r1 | `614b351ab7970cbe9ad3c3cd9e694f8fd4833c57167af55f3bb7f582eff66e1d` |
| Observation-qualified vertical ledger | `ddb829a3830c102adac550d6a6a6c76aa4c7b79cdf91bd28c13164ab0f671753` |
| Fire M3 assignment r1 | `3b02eae635c96cf5dde4144446cf1ff81988377734946f5ec261135286d48b31` |
| Fire M3 + MCD64A1 assignment r2 | `ed3250b14fcf64ddc4ed58e530a687948a11949be9ef3a9c52f4fd0937b13b34` |
| Expanded candidate readiness r1 | `e644123a5c0a40cfd487b1581fd26103194399e68f3a28e0abf8ee11a96cbdb1` |
| Source-area-qualified candidate CSV | `c5a03a41e5f51753359e08ecf570a706d6a59a81b6bbf1c27c1a4026ded11ffc` |
| MCD64A1 2017 results | `356627ab075fe4943731faaaac4398d180a1d4cfd1bff0901c2e60a27863673f` |
| MCD64A1 2018 results | `43b7ecd20e3305d45a26e6be2a8a9bd1130dd72b93a26f61f5724b07dd867381` |

The CSV is the convenient, height-magnitude-free list of the 88 currently
qualified candidates.

## Reproduction commands

Acquisition:

```bash
PYTHONPATH=python .venv/bin/python \
  scripts/freeze_misr_merlin_vertical_ledger.py \
  --data-root /Volumes/BigMrStorage/weatherapp_data/weather \
  --output-directory "$EXPANDED" \
  --start-date 2017-01-01 \
  --end-date 2026-07-27 \
  --all-overpasses \
  --download-workers 8 \
  --ledger-name vertical-ledger-expanded-r1.json
```

Observation processing:

```bash
PYTHONPATH=python .venv/bin/python \
  scripts/build_misr_merlin_expanded_blind_qa.py \
  --vertical-ledger "$EXPANDED/vertical-ledger-expanded-r1.json" \
  --output "$EXPANDED/minx-expanded-blind-qa-r1.json"

PYTHONPATH=python .venv/bin/python \
  scripts/build_misr_merlin_expanded_observations.py \
  --blind-qa-ledger "$EXPANDED/minx-expanded-blind-qa-r1.json" \
  --observation-ledger "$EXPANDED/minx-expanded-observation-ledger-r1.json" \
  --extraction-audit "$EXPANDED/minx-expanded-extraction-audit-r1.json"
```

The complete source-area commands and exact artifact paths are represented by
the assignment and MCD64A1 ledgers. Credentials were not written to any
artifact.

## Implementation record

The expansion added or generalized the following code:

| File | Purpose | SHA-256 |
|---|---|---|
| `scripts/freeze_misr_merlin_vertical_ledger.py` | arbitrary date ranges, exhaustive orbit retention, parallel checksummed downloads | `86137a814b9fbafb3a836508ebf5131dd250fe437b509e8518e71712ec0c18a7` |
| `python/weather_ingest/minx_blind_qa.py` | band-independent plume-family identity | `975ceefc3e816611759df36ac4bc9ca1fc00c817203ee20016216966098ddd3a` |
| `scripts/build_misr_merlin_expanded_blind_qa.py` | one blind selection per plume family | `38c15c716852655ae56bd298e287a5c165d09173dfb0b40450d25c995d612859` |
| `scripts/build_misr_merlin_expanded_observations.py` | sealed height extraction and safe status audit | `72789a41826e2e20e85d8cff48ef7eeadb54976e050baf438e7252bdcf807749` |
| `scripts/build_misr_merlin_qualified_vertical_ledger.py` | observation-qualified source ledger | `40f68971fdf407b0262651544c7a5d1b1cb3a0f1d360ae060c1b7211ddadc374` |
| `scripts/build_vertical_input_assignments.py` | generic complete-pool source assignment with event deduplication | `8126507701c9b0471b172b8c4919f38cbc8eb3e34073d10ae3bd60cb8469a8ac` |
| `scripts/build_misr_merlin_expanded_candidate_ledger.py` | joins blind QA, observation status, Fire M3, and MCD64A1 without exposing heights | `111b3abacfc0ec637cdb98da0610548d5fd221bc4b42319b62d24ab124f56b0a` |
| `scripts/download_w3_gfs_gdex.py` | concurrent metadata inventory and bounded retry | `2ad0ab5bc9c48ab3ba719852822d74493c104c6ab98d415e9c710365a20b217d` |

The workspace is not a Git worktree. These file hashes identify the exact
implementation used here, but publication should rerun the workflow from a
version-controlled, immutable source commit.

## Verification

Final verification on 2026-07-27 produced:

```text
Ruff, changed implementation and test set             passed
focused MINX/W3 tests                                  7 passed
repository-wide tests                                 274 passed
optional PostgreSQL integration tests                  19 skipped
downloaded MINX files hash-checked                     772/772
downloaded MINX bytes hash-checked                  65,274,882
candidate CSV data rows                                 88
candidate-status reconciliation          2+277+21+88 = 388
acceptance-evidence-matrix.yaml                         parsed
local Markdown links checked                            36
missing local Markdown links                             0
incomplete .part files                                   0
```

The skipped tests require `WEATHER_TEST_DATABASE_URL`; none exercises the
MISR/MINX processing added here. The full test run emitted 11 existing
NumPy/rasterio warnings and no failures.

## Remaining work

1. Obtain external plume-science review of the 250 m/10-retrieval operator.
2. Obtain the 2019 Canadian/Alaskan collection through a provider-supported
   download route, if available.
3. Freeze a physical-fire clustering rule and a central/reserve selection
   without FLEXPART output or model-observation agreement.
4. Target at least 20 central cases so later causal-input exclusions do not
   reduce the formal sample below 10.
5. Download and validate historical GFS for the frozen central and reserve
   cases.
6. Construct time-causal source and CFFEPS emission histories.
7. Refreeze the successor protocol and software identity.
8. Only then execute and open the formal FLEXPART comparison.
