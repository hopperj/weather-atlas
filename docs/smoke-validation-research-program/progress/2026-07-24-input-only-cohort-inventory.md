# W1 research notebook: input-only historical cohort inventory

**Program:** `cffeps-flexpart-acceptance-program-v1`  
**Workstream:** W1  
**Status:** in progress  
**Started:** 2026-07-24  
**Scope:** historical input and observation-availability feasibility only  

## Selection firewall

This inventory may inspect only:

- raw provider products and catalogues;
- provider discovery metadata and documentation;
- event identity, location, date, area, ecozone, and fuel attributes;
- fire-weather and meteorological input completeness; and
- independent-observation presence, coverage, and quality metadata.

It must not open or derive information from:

- FLEXPART concentration or deposition output;
- CFFEPS/FLEXPART versus GFAS comparison results;
- predicted versus observed plume height;
- predicted versus observed PM2.5; or
- any performance metric from a proposed historical cohort.

The already completed 2026 pilot may be referenced only to define input
requirements and known software limitations. It cannot be used to choose
historical events. The scanner will reject paths under candidate
`transport`, `evaluation`, and `verification` trees by construction.

## Research question

Which historical periods can support independently selected source/GFAS,
vertical-plume, and surface-PM2.5 cohorts with complete, versioned inputs
before any new model output is created?

## Prospective candidate periods

The first catalogue scan covers:

1. the 2023 Canadian fire season as the preferred source/GFAS and surface
   feasibility period; and
2. the public MISR Plume Height Project periods, including the 2017 and 2018
   summer collections, as alternate vertical-observation feasibility periods.

These are catalogue hypotheses, not selected validation cohorts. A period
will be retained only after the input-only scanner establishes data
completeness under the frozen rules.

## Required product classes

For each period the inventory records:

| Role | Required source/product class | Completeness test |
|---|---|---|
| Fire identity/fuel | NRCan CWFIS Fire M3 or authoritative archive | event records, coordinates, times, fuel evidence |
| Independent area | MCD64A1 C6.1; VNP64A1 V2 sensitivity | QA-valid burn occurrence and date coverage |
| Fire-weather state | authoritative FFMC, DMC, DC | every positive-area source day complete |
| Transport meteorology | one consistent GFS/GDAS family | full source day and transport horizon |
| Source comparison | CAMS GFAS, frozen version | complete event/domain dates and required species |
| Vertical observations | MISR/MINX/MERLIN or accepted lidar | overpass metadata and QA available |
| Surface observations | final ECCC NAPS hourly PM2.5 | station metadata and fixed-domain hourly coverage |

## Machine-readable statuses

Each product-period entry uses one of:

- `local_complete`
- `local_partial`
- `remote_available`
- `manual_request_required`
- `unavailable`
- `not_checked`

Local evidence includes file count, byte count, temporal coverage inferred
from trusted manifests/filenames, and manifest hashes. Remote evidence includes
the official discovery source, product/version, advertised coverage, access
method, retrieval timestamp, and any account/manual-access constraint.

## Chronological log

### 2026-07-24 — inventory opened

- Established the selection firewall above.
- Inspected only the raw data hierarchy and the existing 2026 raw catalogue.
- Found local raw holdings for ECMWF GFAS, NOAA GFS, NASA MCD64A1, NRCan CWFIS,
  ECCC NAPS, EPA AirNow/AQS, Copernicus TROPOMI, and several ECCC numerical
  products.
- The visible year partitions are concentrated in 2025–2026. No conclusion
  about remote historical availability has yet been drawn.
- Began a generalized inventory scanner that reports period/product
  availability without reading model outputs.

No historical event has been selected or excluded yet.

### 2026-07-24 — product-period inventory v1

The scanner completed 24 product-period checks across the 2023 Canadian fire
season and the 2017/2018 MISR summer periods. It opened only provider files
below the raw-data root.

```text
/Volumes/BigMrStorage/weatherapp_data/weather/derived/smoke/validation/
  cohorts/input-only-inventory-v1/inventory-manifest.json
SHA-256:
916b1757e464d6c55e7c2fef94a74b510cc9a0bb3ec0d4c8419ed038aff24f4a

/Volumes/BigMrStorage/weatherapp_data/weather/derived/smoke/validation/
  cohorts/input-only-inventory-v1/no-output-access-audit.json
SHA-256:
1ac449f2d1e4ec1c9c0adcc3a94ef964b52dfb497156519d6e50dd3904decbdb
```

No proposed-period files were initially local. Official discovery establishes
remote archives for MCD64A1, NOAA GFS/GDAS, GFAS, MISR, and NAPS. The main
known 2023 input bottleneck is authoritative gridded CWFIS FFMC/DMC/DC:
the public CWFIS 2.0 time dimension starts on 2024-01-01. A provider archive
request or a preregistered, independently reviewed station reconstruction is
therefore required unless the Fire M3 record proves sufficient under the
successor protocol.

This is a product-level availability result, not an event-level completeness
result and not a selected cohort.

### 2026-07-24 — 2023 Fire M3 acquisition

The official NRCan directory was queried directly and confirmed annual
archives from 1994 through 2025, including the exact 2023 file. The 2023
archive was downloaded without credentials and passed ZIP integrity and safe
member-name checks.

```text
Archive:
/Volumes/BigMrStorage/weatherapp_data/weather/raw/nrcan/cwfis/firem3/
  archive/2023_hotspots.zip
Bytes: 216213914
SHA-256:
e5475a66f76fd7a4fe6d8643d955761aeda0cdcffcbf7b39954e3e1dcc9a5334

Acquisition manifest:
/Volumes/BigMrStorage/weatherapp_data/weather/raw/nrcan/cwfis/firem3/
  archive/2023_hotspots.manifest.json
SHA-256:
4298070435e870c08227566fbbe1845ac86e24f940bbb94a77fa8fa7232eab87
```

The single CSV member is 748,475,815 uncompressed bytes and includes detection
time, satellite/sensor, FRP, country, agency, ecozone, fuel, and the FFMC, DMC,
and DC fields needed for the next input-only completeness audit. No event or
area stratum has yet been selected.

### 2026-07-24 — 2023 Fire M3 input-only completeness audit

The annual CSV was streamed without extraction and filtered only by the
prospectively declared 2023 Canadian fire-season dates and Canadian records.
The audit did not inspect any model output, comparison, plume-height residual,
or PM2.5 performance field.

```text
Summary:
/Volumes/BigMrStorage/weatherapp_data/weather/derived/smoke/validation/
  cohorts/input-only-inventory-v1/firem3-2023-summary.json
SHA-256:
99c2a8c1dbf7b99727fec859897b07c1fdfba714dccd4ac51485a4020bd64a06
```

Results:

- 3,674,409 rows occur in the full annual archive;
- 3,471,852 rows occur during May 1 through October 31;
- 3,180,234 of those period rows are Canadian;
- all 184 calendar dates in the declared period are represented;
- all Canadian period rows have valid coordinates;
- all 3,180,234 Canadian period rows contain FFMC, DMC, and DC;
- 976 rows report DMC equal to zero and 1,079 report DC equal to zero; these
  are retained as provider values and are not silently treated as missing;
- records span multiple agencies, ecozones, and fuel classes.

The product-period scanner was rerun after acquisition and now classifies the
2023 Fire M3 input as `local_complete`. This establishes hotspot and associated
fire-weather-field availability, not independent burned area, unique fire
events, or cohort representativeness. Hotspot detections are repeated
satellite observations and must not be counted as independent fires.

The next inventory stage will catalogue MCD64A1 C6.1 and VNP64A1 V2 burned-area
granules for the same frozen period, then construct event identities and area
strata without accessing predicted outputs. The event-selection ledger remains
unopened until those independent-area inputs and transport/source-comparison
inputs are complete.

### 2026-07-24 — historical burned-area catalogues frozen

NASA CMR was queried prospectively for granules intersecting the declared
Canadian bounding box (`-141,41,-52,84`) during 2023-05-01 through
2023-10-31. The query used product identity, version, time, and geography only.
It did not download or decode burned-area pixels and did not access any model
output.

```text
Catalogue manifest:
/Volumes/BigMrStorage/weatherapp_data/weather/raw/catalogues/
  smoke_validation_historical/
  burned-area-catalogue-manifest-2023-05-01_2023-10-31.json
SHA-256:
a788790a1d2fe4045840f0f77abf1b323393dcad440e8e4cea27cc55a2a81066
```

The frozen catalogue contains:

| Product | Version | Intersecting granules | Catalogue SHA-256 |
|---|---:|---:|---|
| MCD64A1 | 061 | 138 | `2f5de53f5ecee2a2e85e136839300e07db05fee8579dc1f8766843b1945e3918` |
| VNP64A1 | 002 | 203 | `d9bd9e87d3af2c34ed4f3b45420480e02967e01c68a868a91725fb5cf6646d5b` |

This establishes that both primary and sensitivity burned-area products have
provider-catalogued coverage for the prospective period. It does not establish
local data completeness or QA-valid area. The next permitted steps are
checksum-verified acquisition, product-specific QA decoding, and event-area
construction under the already frozen operator. Event selection remains
forbidden until those steps and the other required input inventories are
complete.

## Planned artifacts

```text
cohorts/input-only-inventory-v1/
  inventory-manifest.json
  period-product-availability.csv
  candidate-periods.json
  access-gaps.json
  no-output-access-audit.json
```

Later event-level ledgers will be produced only after the product-level
inventory establishes which periods can be assessed without ad hoc filling.

## Decision policy

The 2023 period will advance only if authoritative fire identity/fuel,
independent area, daily FFMC/DMC/DC, consistent transport meteorology, and GFAS
are obtainable. Vertical and surface ledgers may span different years, but
their selection rules and observation-availability queries must be frozen
before model output. Missing historical CWFIS state triggers an archive
request or a separately reviewed station reconstruction; it never triggers
silent nearest-neighbour or temporal filling.

### 2026-07-26 — perimeter and burned-area acquisition complete

The 2023 Fire M3 buffered-perimeter archive was downloaded and integrity
checked:

```text
2023_perimeters.zip SHA-256:
787e398652ac6e35a2ecb5af2238c6cb06dc2729836d32466254efbd53bacda2

Feature count: 1,144
Screening strata: 145 weak, 456 moderate, 543 major
```

Every NASA granule in the previously frozen Canadian CMR catalogues was then
downloaded and checksummed. This is pixel-product acquisition, not an
acceptance result:

| Product | Files | Bytes | Download manifest SHA-256 |
|---|---:|---:|---|
| MCD64A1 v061 | 138 | 431,859,842 | `c5e15ca8d09b54ef6851ca051163c127589831b3b186cc2fdd995d353bcc1362` |
| VNP64A1 v002 | 203 | 557,579,310 | `052a8ec90364a36588ff2e4ea78a81032cd2a167590e6a4be4a159cf15312763` |

Perimeters were stratified only by provider area and deterministically
hash-ranked to form an oversized event-screening pool. Fire M3 location, time,
fuel, ecozone, and CFFDRS fields are the only other event-reconciliation
inputs. No candidate transport, GFAS comparison, plume-height residual, or
surface-PM2.5 residual was opened.

### 2026-07-26 — prospective observation-availability ledgers frozen

The final 2023 NAPS hourly PM2.5 file was downloaded from the ECCC archive.
It contains 365 dates, 231 stations, and 1,929,470 valid hourly values.

```text
PM25_2023.csv SHA-256:
9d87fd544c88bb42aa16aac092838e75bff65a624ffc670e6563a9adc036535a

Surface ledger SHA-256:
30dbfefe3210ec78702768f9eba84c264e531e97cf3243c0ce8fe06ddee10cd0
```

The frozen surface ledger records 231 station identities and 951,598 valid
May-through-October station-hours. It retains availability and missingness
only. Concentrations were neither retained nor ranked, and no predicted value
or residual was accessed.

The public MISR Plume Height Project/MERLIN catalogue was queried for the
prospectively named 2017 and 2018 periods. A deterministic seeded selection
retained eight Canadian-interior orbit overpasses per year. In total, 16
independent overpasses and 114 raw MINX plume files are locally checksummed.

```text
Vertical ledger SHA-256:
e77132958ee94c18e730f269b8391f6b8322b1e710975d81fbc4266b1b7f4b6c
```

Observed plume heights were not used for ranking. Event pairing, plume QA,
and the fire-overpass operator remain W3 work; the ledger only establishes
prospective independent-observation availability.

### 2026-07-26 — exact W1 blockers

W1 is not being labelled complete merely because most inputs are local. Its
definition also requires a frozen source/GFAS cohort with complete,
consistent historical meteorology and independent no-performance-selection
sign-off.

The ECMWF delivery portal's rolling GFAS v1.4.2 tree does not contain 2023.
The applicable historical product is GFAS v1.2 daily analysis in the
Copernicus Atmosphere Data Store. The authorized local environment currently
contains delivery-portal credentials, but not an ADS personal access token.
Those are different authentication systems. An ADS request therefore cannot
be made until the account has accepted the dataset terms and a personal token
is provided through a local secret, never through a research manifest.

The event-reconciliation and MCD64A1 area stages are now complete. The
remaining technical sequence is:

1. finish retrieval of GFAS v1.2 and the consistent historical GFS family for
   the frozen retained/reserve dates and transport horizons;
2. close the per-event area, fuel, FFMC/DMC/DC, GFAS, and meteorology
   completeness audit;
3. freeze `source-gfas-ledger.json`, exclusions, and the successor protocol;
   and
4. obtain an independent audit signature that no model-performance variable
   entered selection.

Current status is
`in_progress_blocked_on_ads_access_and_independent_review`. No holdout
FLEXPART output has been created and no production-write setting was changed.

### 2026-07-26 — event reconciliation and independent-area design pass

The final bounded implementation streamed the Fire M3 archive, retained only
the two nearest admissible predecessor distances needed for ambiguity
reporting, and vectorized clearly inside/outside distance classifications.
Exact threshold cases and reported nearest distances still use the original
great-circle operation. Regression tests cover input-order independence,
dense ambiguity, and a new detection that bridges two previously separate
components.

```text
Candidate events SHA-256:
5de50a7f23a9abdca8fd3b9c21b05613476c87a4a49caa02f63b92802a77d358

Candidate report SHA-256:
c67f9e2074037845856109281d841a7c12b8d2ddc7faa25fb0f5a394135ee92d

Input detections: 556,111
Reconciled candidate events: 464
```

The frozen `mcd64a1-event-area-v2` operator then loaded all 138 local
MCD64A1 granules, applied the declared QA/reliability rules, seeded and grew
eight-connected burn occurrences, and excluded every burn occurrence claimed
by more than one event.

```text
MCD64A1 event areas SHA-256:
2a18e14bb2757775aa0f0c0c7f37aaf85e78ac55c7d5d22f6232f331716f61f4

Eligible events: 54
Weak: 30
Moderate: 19
Major: 5
Ambiguous occurrences excluded from all claimants: 106,774
```

The independent-area 3/3/3 design therefore passes before any model output.
A deterministic SHA-256 rank retained three events per stratum and froze two
reserves per stratum. The nine retained events span six Fire M3 ecozones and
three FBP fuel families; every detection has finite FFMC, DMC, and DC.

```text
Preliminary source candidate ledger SHA-256:
69940bc97e74792a0aefd4a3e23e4728c1c6dc9686da96875f9ac229f1e5ca40

Retained events: 9
Reserve events: 6
Positive-area retained/reserve acquisition dates: 77
```

This is intentionally a preliminary frozen ledger, not
`source-gfas-ledger.json`: its GFAS and historical-meteorology completeness
flags remain false until those archives are locally complete and checksummed.

### 2026-07-26 — historical source meteorology complete

The preliminary retained/reserve ledger contains 77 distinct positive-area
source dates. Adding the prospectively declared one-day spin-up and
deduplicating adjacent dates produced 102 required 00Z GFS cycles. NOAA's
historical open-data archive supplied all nine three-hourly `f000` through
`f024` files per cycle. Every GRIB passed the existing FLEXPART-oriented
surface-field and pressure-level completeness checks before its cycle manifest
was committed.

```text
Historical GFS ledger SHA-256:
1331d36e1f0b8a3e20e9a165f85889225afed98edeb4d2c1e181dc917d72c3fc

Cycles: 102
Files: 918
Bytes: 40,927,328,307
```

The W1 historical-meteorology flag is now true. Historical GFAS v1.2 and
independent no-performance-selection review remain false.

```text
Combined W1 progress manifest SHA-256:
de80750bd88dfd46d6156b6d3004412e530a4f1db1f45a7d8417149997e895c4

Machine status:
technical_inputs_complete_except_gfas_and_independent_review
```

### 2026-07-26 — ADS personal token authenticated

The local `ADS_PERSONAL_ACCESS_TOKEN` authenticated successfully with the
official ADS/CDS API client, and the CAMS GFAS collection metadata was
accessible. The secret value was not printed or copied into an artifact.

This removes the missing-credential condition but does not complete W1.
Historical GFAS v1.2 still has to be requested for the frozen 2023 dates,
downloaded, validated, checksummed, and added to the source/GFAS completeness
ledger. Independent no-performance-selection review also remains unsigned.
