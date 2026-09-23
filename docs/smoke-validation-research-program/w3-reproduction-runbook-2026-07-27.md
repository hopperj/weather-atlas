# W3 blinded-analysis reproduction runbook

**Applies to:** W3 MISR QA, causal source histories, and causal CFFEPS
emission histories  
**Companion methods record:**
[W3 blinded MISR observation QA and causal pre-overpass emissions](progress/2026-07-27-w3-blind-observation-and-causal-emissions.md)  
**Artifact dictionary:**
[W3 artifact and data dictionary](w3-artifact-data-dictionary-2026-07-27.md)  

> **Scope notice:** This runbook reproduces the immutable original 16-case
> cohort. The
> [expanded 2017-current MISR inventory](progress/2026-07-27-w3-expanded-misr-2017-current.md)
> supersedes its availability conclusion but does not overwrite its artifacts.
> A new central/reserve freeze and expanded-cohort execution runbook are
> required before formal W3 execution.
**Final readiness:** blocked; 6 eligible of 10 required

## 1. Purpose

This runbook records:

- the execution environment;
- immutable input identities;
- exact operator order and parameters;
- the historical commands used to create the frozen artifacts;
- safe commands for an independent reproduction;
- integrity and scientific-content checks;
- the observation/model firewall; and
- the retention policy for failed and superseded revisions.

It does not authorize a FLEXPART holdout run. It does not authorize changing
an observation rule after learning the retained sample count.

## 2. Security and blinding boundary

The following artifact contains observed MISR height magnitudes:

```text
/Volumes/BigMrStorage/weatherapp_data/weather/derived/smoke/validation/
readiness/cffeps-flexpart-successor-2026-v1/w3-blind-analysis/
minx-observation-ledger-r1.json
```

Its SHA-256 is:

```text
777c6e5f926b25f15f18357fc61a9ed0c5471b491542d6d04975f7b15db21013
```

Do not display, summarize, or open that file in a session that is still making
plume, band, source, QA-threshold, injection, or model-configuration choices.
The extraction audit and final readiness ledger contain counts and statuses
but no height magnitudes and are safe for pre-execution review.

No command in the causal source or CFFEPS sections accepts the observation
ledger as an argument. No command in this runbook opens FLEXPART output.

## 3. Execution environment

The final r2 CFFEPS emission histories were built in:

| Component | Version |
|---|---|
| Platform | `macOS-26.0.1-arm64-arm-64bit-Mach-O` |
| Python | `3.14.3` |
| GNU Fortran | Homebrew GCC `16.1.0` |
| ecCodes command-line tools | `2.48.0` |
| Python `eccodes` | `2.47.0` |
| NumPy | `2.5.1` |
| netCDF4 | `1.7.4` |
| PyYAML | `6.0.3` |
| pytest | `9.1.1` |
| Ruff | `0.15.22` |

The project root was:

```text
/Users/hopperj/work/hobby/weatherapp
```

The CFFEPS build command uses the flags recorded in
`cffeps/Makefile.portable`:

```text
-O2 -g -fbacktrace -fcheck=bounds -ffree-line-length-none
```

### 3.1 Software identity and snapshot limitation

The project directory was not a Git working tree, so there is no commit SHA
that identifies the complete source state. Current relevant file hashes are:

| File | SHA-256 |
|---|---|
| `python/weather_ingest/minx_blind_qa.py` | `13c4c801d541f80bb5ffcc74c532735aff43dbb10e920030ffb85fb6aea84de8` |
| `python/weather_ingest/misr_minx.py` | `418b9de93e91f2802837fe57237b938539d2614d413f42b1213c43da5681fc0b` |
| `python/weather_ingest/w3_causal_history.py` | `cc691daee2f808c6d9934af69e3e1f3061e65863b334798a6b931cddb4bcf60a` |
| `python/weather_ingest/w3_readiness.py` | `9059630afda0071b7de29dce391de906bc4d4dc765757386860a7c9982e3be84` |
| `python/weather_ingest/cffeps.py` | `da8ddd7558ae9a310f1c85e2cd0c4bdaa37316fa2ef659726df1071bc9df5839` |
| `scripts/build_w3_blind_minx_qa.py` | `9d45e598a2bd7bf53a47b9d7dc99a3081cce5b6e68d9c036348058bf672baa0a` |
| `scripts/build_w3_minx_observations_from_blind_qa.py` | `5fb6869fb99ca638bdb436c09d92ad91859587a97b8b19378aa3bde08a0a3fc9` |
| `scripts/build_w3_causal_emission_histories.py` | `99f1818bc8e8aa90a8c21c26cada6191ea0ed759011345265539d1072a9155ca` |
| `scripts/build_w3_causal_cffeps_emissions.py` | `a9162a275f57be954a700eba6a37307e0da601d94ea55bf7767163077f1c8f1a` |
| `scripts/build_w3_blinded_readiness.py` | `c61a85574816af8e1d7a8930d16b7fd6eb8039a323a97980ae6d1d112c7a4a13` |
| `cffeps/src/weatherapp_cffeps_driver.f90` | `eb7e07f69d5aaba854ef4ae33d5e397871b8af1e9aed406dd8865de771a44771` |
| `cffeps/tests/verify_golden.py` | `83308aa355047b4acb9a2907a90b5c9f34e48b86366631c4b8b305a884645b6f` |

Ruff import/format normalization occurred after some early JSON ledgers were
created but did not change their operator logic. The final CFFEPS r2 and
readiness r3 runs used the current causal-CFFEPS and readiness implementations.
Frozen artifact hashes remain the authority for the executed results.

Before formal rerun or publication, put this source tree under version control
or create a checksummed source archive, then rerun all operators under that
single immutable software identity. This is a documented reproducibility
limitation, not an independent-review signoff.

## 4. Path definitions

The commands below use these shell variables:

```bash
export PROJECT=/Users/hopperj/work/hobby/weatherapp
export DATA=/Volumes/BigMrStorage/weatherapp_data/weather
export READY="$DATA/derived/smoke/validation/readiness/cffeps-flexpart-successor-2026-v1"
export ANALYSIS="$READY/w3-blind-analysis"
export VERTICAL="$DATA/derived/smoke/validation/cohorts/w1-2023-input-only-v1/vertical-ledger.json"
export ASSIGNMENT="$READY/vertical-input-assignment-r2.json"
export GFS="$READY/w3-historical-gfs-gdex-r2.json"
export FIREM3_2017="$DATA/raw/nrcan/cwfis/firem3/archive/2017_hotspots.zip"
export FIREM3_2018="$DATA/raw/nrcan/cwfis/firem3/archive/2018_hotspots.zip"
export MINX_ROOT="$DATA/raw/nasa/asdc/misr/merlin/plume-height-project-2"
export MCD64A1_ROOT="$DATA/raw/nasa/lpdaac/mcd64a1/v061"
export GFS_ROOT="$DATA/raw/noaa/gfs/gdex_d084001_global_0p25"

cd "$PROJECT"
export PYTHONPATH="$PROJECT/python"
```

No `.env` credential is required to reproduce the analysis from the local
frozen inputs. Never print or copy `.env` into a publication bundle.

### 4.1 Provider and product lineage

| Role | Provider/product | Local source |
|---|---|---|
| Plume observations | NASA ASDC MISR Plume Height Project/MINX V4.0 | `$MINX_ROOT/{2017,2018}` |
| Burn occurrence and area | NASA LP DAAC MCD64A1 Collection 6.1 | `$MCD64A1_ROOT/{2017,2018}` |
| Fire source, fuel, and weather codes | NRCan CWFIS Fire M3 | `$FIREM3_2017`, `$FIREM3_2018` |
| Meteorology | NOAA GFS GDEX `d084001`, global 0.25 degree | `$GFS_ROOT` |
| Fuel mapping | versioned CWFIS-to-FBP crosswalk | `config/smoke/fuel_crosswalk.yaml` |
| Species factors | phase-resolved validation registry | `config/smoke/emission_factors.yaml` |
| Emissions/plume rise | CFFEPS 4.1 portable driver | `cffeps/` |

The upstream input-only assignment used a maximum 5 km source match, maximum
3-hour time offset, and tie breaks by distance, absolute time offset, MISR
region name, then Fire M3 provider-row hash. Candidate output and plume height
were prohibited from that assignment.

## 5. Immutable input checks

Verify the principal frozen inputs before running an operator:

```bash
sha256sum \
  "$VERTICAL" \
  "$ASSIGNMENT" \
  "$GFS" \
  "$FIREM3_2017" \
  "$FIREM3_2018" \
  config/smoke/fuel_crosswalk.yaml \
  config/smoke/emission_factors.yaml \
  cffeps/upstream/cffeps-4.1.tar.gz
```

Expected hashes:

| Input | SHA-256 |
|---|---|
| MISR vertical availability ledger | `e77132958ee94c18e730f269b8391f6b8322b1e710975d81fbc4266b1b7f4b6c` |
| W3 assignment ledger r2 | `ce541e36a02cf7e54ab56a2b58708705830263f0828ce5359108ef7f87060d15` |
| Historical GFS GDEX ledger r2 | `55e083f1de456100a2e0588e442223e9b381fe6d633cfc98820a9a6abecbd5a0` |
| Fire M3 2017 archive | `cd6f01d10e8719ad23e9b15f5a4b8330e949c938c488c4733c11459536f8481c` |
| Fire M3 2018 archive | `3d4659e36c994cea4a6ddc18d1d057358828aa5d9f893c7e3682c7219096b131` |
| Fuel crosswalk | `c4d857d0988676f657e09fbef2cd402d0d39d10ca3a0bd304f4cad0e6dece675` |
| Emission factors | `0f9d462d10344603d99f4fdadf3acff06977e9ae53c0d2e3508a106b1aaef84a` |
| Upstream CFFEPS 4.1 archive | `8aac1918bb4c8897c1e07166939d96d1a3470ddf43dca7d66200e96eed7a503a` |

Every assignment record also carries checksums for its Fire M3 assignment,
fuel, fire-weather state, independent MCD64A1 area, and transport-meteorology
artifacts. Downstream builders verify the hashes they consume.

## 6. Build and verify CFFEPS

Build the portable driver:

```bash
make -C cffeps -f Makefile.portable -B all
```

Verify legacy and causal interfaces:

```bash
.venv/bin/python cffeps/tests/verify_golden.py \
  --executable cffeps/bin/weatherapp-cffeps
```

Expected result:

```text
PASS: 10 CFFEPS 4.1 golden cases and 6 FBP sensitivity cases;
hourly causal fire-weather and estimated-area profiles verified
```

The executable used for final emission ledger r2 has SHA-256:

```text
7934e39783f27ac74411349e8de2d5a978073bee6182a2abc0e70be2891cd96c
```

## 7. Operator sequence

The sequence is binding:

1. height-blind MINX file selection;
2. freeze the selection ledger hash;
3. post-selection observation extraction;
4. causal source-history construction;
5. causal CFFEPS emission construction;
6. status-only readiness join; and
7. independent review before any FLEXPART output is opened.

The observation and source branches may run independently after step 2, but
their statuses are not joined until both are frozen.

## 8. Historical frozen commands

These commands document how the current artifacts were produced. Do not rerun
them into the existing output paths.

### 8.1 Height-blind MINX QA r2

```bash
PYTHONPATH=python .venv/bin/python scripts/build_w3_blind_minx_qa.py \
  --vertical-ledger "$VERTICAL" \
  --assignment-ledger "$ASSIGNMENT" \
  --output "$ANALYSIS/minx-blind-qa-r2.json" \
  --minimum-raw-retrievals 10 \
  --maximum-source-polygon-distance-km 5
```

Expected summary:

```text
selected_count = 15
excluded_pre_observation_input_invalid_count = 1
excluded_blind_qa_count = 0
```

The earlier `minx-blind-qa-r1.json` is a retained failed attempt. It required
provider successful-retrieval count to equal raw result rows and therefore
rejected every case. It was corrected before height extraction.

### 8.2 Post-selection observation extraction r1

This is the only step that reads selected MINX height columns:

```bash
PYTHONPATH=python .venv/bin/python \
  scripts/build_w3_minx_observations_from_blind_qa.py \
  --blind-qa-ledger "$ANALYSIS/minx-blind-qa-r2.json" \
  --observation-ledger "$ANALYSIS/minx-observation-ledger-r1.json" \
  --extraction-audit "$ANALYSIS/minx-extraction-audit-r1.json"
```

Expected safe summary:

```text
frozen_observation_count = 6
excluded_post_selection_measurement_invalid_count = 9
height_values_emitted_to_stdout = false
```

The operator is fixed in code to:

```text
primary field                wind-corrected height
terrain conversion           AGL = height ASL - terrain ASL
aggregation                  median per fire-overpass
minimum AGL                  250 m
minimum valid retrievals     10
post-extraction band fallback false
```

Those measurement rules are provisional pending independent review. Do not
change them on this cohort to obtain a desired sample size.

### 8.3 Causal source-history ledger r1

```bash
PYTHONPATH=python .venv/bin/python \
  scripts/build_w3_causal_emission_histories.py \
  --assignment-ledger "$ASSIGNMENT" \
  --gfs-ledger "$GFS" \
  --hotspots "2017=$FIREM3_2017" \
  --hotspots "2018=$FIREM3_2018" \
  --output-directory "$ANALYSIS/causal-histories-r1" \
  --output-ledger "$ANALYSIS/causal-history-ledger-r1.json" \
  --history-hours 24 \
  --state-lookback-hours 24 \
  --maximum-fire-distance-km 5
```

Expected summary:

```text
ready_causal_history_count = 14
excluded_no_causal_central_area_count = 1
excluded_pre_history_input_invalid_count = 1
height_or_flexpart_values_emitted = false
```

This step extracts 40-level historical GFS profiles and can take several
minutes. It does not read the observation ledger.

### 8.4 Final causal CFFEPS emission ledger r2

```bash
PYTHONPATH=python .venv/bin/python \
  scripts/build_w3_causal_cffeps_emissions.py \
  --causal-history-ledger "$ANALYSIS/causal-history-ledger-r1.json" \
  --cffeps-executable cffeps/bin/weatherapp-cffeps \
  --emission-factors config/smoke/emission_factors.yaml \
  --fuel-crosswalk config/smoke/fuel_crosswalk.yaml \
  --output-directory "$ANALYSIS/causal-emissions-r2" \
  --output-ledger "$ANALYSIS/causal-emission-ledger-r2.json" \
  --vertical-layer-count 12
```

Expected summary:

```text
ready_emission_history_count = 13
excluded_count = 3
height_or_flexpart_values_emitted = false
formal_w3_execution_permitted = false
```

The retained r1 emission revision varied the fire-weather state but used total
pre-overpass area as constant `estarea`. It was superseded because this let an
early source hour use the fire's later pre-overpass size. Revision r2 supplies
both:

- latest-prior FFMC/DMC/DC at every source hour; and
- cumulative released area only through the end of that source hour.

It also disables active-interval area redistribution and clips the last
release interval at the exact overpass.

### 8.5 Final blinded readiness r3

```bash
PYTHONPATH=python .venv/bin/python scripts/build_w3_blinded_readiness.py \
  --blind-qa-ledger "$ANALYSIS/minx-blind-qa-r2.json" \
  --extraction-audit "$ANALYSIS/minx-extraction-audit-r1.json" \
  --causal-history-ledger "$ANALYSIS/causal-history-ledger-r1.json" \
  --causal-emission-ledger "$ANALYSIS/causal-emission-ledger-r2.json" \
  --output "$ANALYSIS/w3-blinded-readiness-r3.json" \
  --minimum-overpasses 10
```

Expected result:

```text
eligible_overpass_count = 6
minimum_overpasses = 10
sample_size_gate_passed = false
formal_execution_permitted = false
```

The join reads statuses, retrieval counts, and hashes. It does not open the
sealed observation ledger.

## 9. Independent reproduction without overwriting

Create a new revision label:

```bash
export REPRO=reproduction-$(date -u +%Y%m%dT%H%M%SZ)
export REPRO_DIR="$ANALYSIS/$REPRO"
mkdir -p "$REPRO_DIR"
```

Use the commands in section 8, replacing every output with a path under
`$REPRO_DIR`. Never write into:

```text
causal-histories-r1/
causal-emissions-r1/
causal-emissions-r2/
minx-*-r1.json
minx-*-r2.json
causal-*-r1.json
causal-*-r2.json
w3-blinded-readiness-r*.json
```

JSON artifacts include creation timestamps, and manifests embed artifact
paths. A reproduction at a new path will therefore not necessarily be
byte-identical even when scientific content is identical. Compare:

- prospective overpass IDs;
- selected MINX source-file hashes and bands;
- all gate statuses and exclusion reasons;
- per-case causal checks;
- hourly Fire M3 observation times and GFS initialization times;
- represented and omitted area;
- species mass totals within numerical tolerance;
- NetCDF row counts and variable values; and
- the absence of any release end after overpass.

Any scientific-content difference must be explained before publication. Do
not normalize away an unexplained difference merely to recover an expected
hash.

## 10. Frozen artifact integrity

The current final artifact hashes are:

```text
6f2ef2890e6f999be47b74f28e7c49e49c9045924c656332673caa7352b8d6dc  minx-blind-qa-r2.json
777c6e5f926b25f15f18357fc61a9ed0c5471b491542d6d04975f7b15db21013  minx-observation-ledger-r1.json
e0328527bb1317282f196144d8773e2aaf6ac234db7628c09e002013a8700bfd  minx-extraction-audit-r1.json
de50536131b4526b6b49943b73dc52894474a7b6ec83a89449c1fc6f4e76b0d0  causal-history-ledger-r1.json
18c7a97be1c60c8bf724ea1df7e58853179341d093b6840a899b1dee961d6522  causal-emission-ledger-r2.json
73d6ad2319af348417587a68729e16519249bcf4a4e8a39d65122f2c4e818104  w3-blinded-readiness-r3.json
```

Verify them without opening their contents:

```bash
cd "$ANALYSIS"
sha256sum \
  minx-blind-qa-r2.json \
  minx-observation-ledger-r1.json \
  minx-extraction-audit-r1.json \
  causal-history-ledger-r1.json \
  causal-emission-ledger-r2.json \
  w3-blinded-readiness-r3.json
```

## 11. Software verification

Run style checks:

```bash
.venv/bin/python -m ruff check \
  python/weather_ingest/cffeps.py \
  python/weather_ingest/minx_blind_qa.py \
  python/weather_ingest/w3_causal_history.py \
  python/weather_ingest/w3_readiness.py \
  scripts/build_w3_blind_minx_qa.py \
  scripts/build_w3_minx_observations_from_blind_qa.py \
  scripts/build_w3_causal_emission_histories.py \
  scripts/build_w3_causal_cffeps_emissions.py \
  scripts/build_w3_blinded_readiness.py
```

Run the repository test suite:

```bash
PYTHONPATH=python .venv/bin/pytest -q
```

Recorded result:

```text
273 passed, 19 skipped, 11 warnings
```

The 19 skips require an explicitly configured PostgreSQL
`WEATHER_TEST_DATABASE_URL`. They do not skip W3 or CFFEPS tests.

## 12. Required external-review reproduction

Before formal W3 execution, an external emissions/plume reviewer should:

1. verify every hash in sections 5 and 10;
2. independently inspect all 16 source-linked plume pairs without model
   output;
3. accept or reject the existing band, polygon, terrain, wind, AGL, and
   minimum-retrieval rules;
4. reproduce at least one complete causal source history by hand;
5. reproduce at least one CFFEPS emission bundle;
6. verify that no Fire M3 observation or GFS initialization used by a source
   hour occurs later than that hour;
7. verify that no MCD64A1 area or release interval occurs after overpass;
8. document the retrospective, not real-time, availability of final MCD64A1;
9. recognize the original six-case result as an insufficient-sample result
   for that immutable cohort and independently review the new expanded
   candidate pool before any replacement cohort is frozen; and
10. issue a reviewer-controlled, artifact-specific decision.

Only after that decision, a new protocol/package freeze, and a passing
pre-execution gate may the project open or generate formal W3 FLEXPART
comparison outputs.
