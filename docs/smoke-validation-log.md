# Smoke validation research log

This is the chronological, human-readable companion to the immutable manifests
under `derived/smoke/validation`. Entries record successful, failed, and blocked
work so that a later manuscript can reconstruct both methods and researcher
decisions.

## 2026-07-22 — Validation initiation and protocol freeze

### Objective

Begin external scientific validation of the CWFIS/GFS/CFFEPS 4.1/FLEXPART 11.1
smoke chain, initially using the archived 2025-11-10 through 2025-12-01 GFAS
experiment, while retaining enough provenance for a publishable methods record.

### Actions completed before candidate inspection

1. Inventoried the active evaluator, thresholds, model build metadata, archived
   input manifest, prior software regressions, and external dataset coverage.
2. Archived the original threshold file verbatim as
   `config/smoke/validation-v1.yaml`.
3. Froze protocol
   `cffeps-flexpart-external-validation-2026-07-22-v1` and threshold version
   `smoke-validation-v2-preregistered-2026-07-22`.
4. Reclassified GFAS as a diagnostic inventory intercomparison that cannot by
   itself count toward scientific acceptance.
5. Required the primary MISR comparison to operate on the transported FLEXPART
   aerosol vertical profile, with raw CFFEPS plume top retained as a component
   diagnostic.
6. Required NAPS total PM2.5 to be transformed to a documented smoke enhancement
   before comparison with primary wildfire-only model output.
7. Added normalized mean absolute error and explicit undefined-denominator
   behaviour to the evaluation implementation.

### Frozen input evidence

- Experiment manifest:
  `/Volumes/BigMrStorage/weatherapp_data/weather/derived/smoke/validation/input-archives/gfas-v1.2-2025-11-10_2025-12-01/manifest.json`
- Verification status: `complete`; no required raw input was missing according
  to the ingestion contract.
- GFAS SHA-256:
  `f243c964a016f95f86932ce8ba00b66dc79c0ed6cabd95bb2be8ad37eb49821b`.
- Hotspot selection: 44,812 rows, of which 7,722 have country code `C` and
  35,433 are VIIRS-I; selection SHA-256
  `3b78e1446bfe95f601c59c2bc4e42b6d93179964ed77832494c33adbd2aa9418`.

### Blocking scientific fact discovered

The annual 2025 hotspot archive schema has no `estarea` field. The separately
downloaded final CWFIS buffered-hotspot perimeter archive contains 737 polygons,
but its latest `LASTDATE` is 2025-11-07, before this experiment. The public dated
URL for `20251110.csv` now returns HTTP 404. Therefore the current November
archive cannot independently constrain daily burned area, which is a required
input to bottom-up emissions.

No candidate emissions result will be produced by inventing area from hotspot
counts or by feeding GFAS FRP/emissions into CFFEPS and then comparing CFFEPS
back to GFAS. The next acquisition target is MCD64A1 v6.1 burn-date data or an
agency perimeter progression covering eligible November events. If no Canadian
November event has a defensible area signal, this window will be reported as an
adapter rehearsal and a fire-season validation window will be acquired.

### Software identity observations

- CFFEPS archive v4.1 SHA-256:
  `8aac1918bb4c8897c1e07166939d96d1a3470ddf43dca7d66200e96eed7a503a`.
- Current CFFEPS executable SHA-256:
  `261af3d712c6ff4506db269958e1b51e670f57eaa28e233ab44a9cfa0f38d649`.
- FLEXPART archive SHA-256:
  `f01758e7bfc3861b6f0b923666b0f4547fa8ca687921ddc6fb234c79e92564c3`.
- Current FLEXPART executable SHA-256:
  `172910544d0acf9d9f9dcef8621d9070beefb786d93ee138b94905cd672e9dac`.
- The official FLEXPART 11.1 source archive prints an internal 11.0 runtime
  banner. The release archive hash, not that stale banner, identifies the code.
- Host at protocol freeze: Apple M1 Ultra, arm64, Darwin 25.0.0; project virtual
  environment Python 3.14.3.

### First event-eligibility execution

The deterministic audit is archived under:

`/Volumes/BigMrStorage/weatherapp_data/weather/derived/smoke/validation/experiments/gfas-v1.2-2025-11-10_2025-12-01/eligibility/`

It retained 4,903 unique, supported-fuel Canadian VIIRS-I detections and
reconciled them into 869 provisional events using `fire-events-v1`. Explicit
exclusions included 36,488 non-Canadian detections, 1,373 non-VIIRS Canadian
detections, 1,273 `farm` detections, and 80 water/non-fuel/unknown/low-vegetation
detections. The final perimeter archive has zero features overlapping the
2025-11-10 through 2025-12-01 interval.

The NASA CMR query found 46 MCD64A1 v6.1 monthly granules intersecting the
Canadian bounding box for November and December 2025. The CMR response is frozen
at
`/Volumes/BigMrStorage/weatherapp_data/weather/raw/nasa/lpdaac/mcd64a1/v061/cmr/2025-11_2025-12-canada.json`.
The LP DAAC data GET requires NASA Earthdata authorization. A second independent
check found that the anonymous Microsoft Planetary Computer mirror has no
MCD64A1 items after July 2025. No protected granule was downloaded and no
credential was requested, printed, or stored.

### Evaluation implementation and checks

- Added a direct ecCodes reader for GFAS GRIB and a species-specific pair builder
  for PM2.5, CO, and BC.
- GFAS flux is converted to cell-day kilograms as `flux × WGS84 geodesic cell
  area × 86,400 s`; CFFEPS layer masses are summed into the same cell and UTC
  day. Pair files retain the active union so source omissions are not hidden.
- The builder records input/pair hashes, ecCodes version, bounding box, grid,
  event IDs, positive-pair counts, and mass totals. It rejects a bounding box
  that omits any candidate source.
- Synthetic end-to-end GRIB/NetCDF tests verify flux-to-mass conversion and
  provenance. The evaluator now reports NMAE and treats a zero normalization
  denominator as undefined rather than perfect performance.
- Results at this point: 13 targeted Python tests passed; all 10 CFFEPS golden
  cases and six FBP sensitivity cases passed; the smoke scientific configuration
  validated as `validation_only/pending_independent_review`.

### Frozen eligibility result

The final audit was executed at 2026-07-23 02:14:10 UTC with this command:

```bash
.venv/bin/python scripts/audit_smoke_validation_eligibility.py \
  --hotspots /Volumes/BigMrStorage/weatherapp_data/weather/raw/nrcan/cwfis/firem3/archive/selections/2025-11-09_2025-12-01.csv \
  --perimeters /Volumes/BigMrStorage/weatherapp_data/weather/raw/nrcan/cwfis/perimeters/archive/2025_perimeters.zip \
  --start 2025-11-10 \
  --end 2025-12-01 \
  --mcd64-cmr /Volumes/BigMrStorage/weatherapp_data/weather/raw/nasa/lpdaac/mcd64a1/v061/cmr/2025-11_2025-12-canada.json \
  --output-directory /Volumes/BigMrStorage/weatherapp_data/weather/derived/smoke/validation/experiments/gfas-v1.2-2025-11-10_2025-12-01/eligibility
```

The command returned status 2 by design because no event met the independent
daily-area requirement. It did not run CFFEPS or FLEXPART and did not inspect a
candidate scientific score. Frozen artifacts are:

- candidate event ledger SHA-256
  `f71e463a333997ec12ed4fec7a7353eebe710eec908f3064a66a54ab6b45bd55`;
- eligibility report SHA-256
  `cf918d051943588514a684ccfa499219b0a48182abe70c9556d0421fb2405394`;
- protocol SHA-256
  `fc8801b7bcc768dd28b2cca38e6fc770988f96f6ebf839d2e8ea2f129ad46342`;
  and
- threshold configuration SHA-256
  `2b789afafb1739cc49d42f9216f8cdd72e416de14da6e08fec1fc84475c31727`.

The report also records the exact Python version, platform, relevant adapter
and evaluator source hashes, event configuration, fuel crosswalk, and source
data hashes. It is the authoritative machine-readable account of why the first
candidate run was not scientifically eligible.

### Verification after the audit

- Full Python suite: 196 passed and 19 PostgreSQL integration tests skipped
  because `WEATHER_TEST_DATABASE_URL` was not configured. The suite emitted six
  upstream NumPy masked-array deprecation warnings and two raster test warnings;
  no test failed.
- All files added or changed for this validation pass the Ruff linter.
- The repository-wide Ruff scan also exposed three pre-existing, automatically
  fixable findings in two literature-index scripts outside this validation
  change. They were recorded but not modified as part of the frozen scientific
  implementation.
- `uv lock --check` succeeded, confirming that the dependency lock is current.
- Ten CFFEPS golden cases and six FBP sensitivity cases passed. The GFAS reader,
  mass conversion, active-union pairing, provenance, evaluator, and smoke
  pipeline are covered by 13 targeted passing tests.

### Next preregistered action

Acquire the 46 catalogued MCD64A1 v6.1 granules through locally configured NASA
Earthdata authorization, verify their HDF checksums, decode `Burn_Date` and QA,
and spatially join accepted burn pixels to the frozen 869-event ledger. Then:

1. calculate daily burned-area increments and uncertainty bounds without using
   GFAS emissions or candidate output;
2. apply the frozen event eligibility and weak/moderate/major stratification;
3. generate CFFEPS emissions and plume profiles for eligible events;
4. run FLEXPART with the frozen GFS meteorology;
5. build PM2.5, CO, and BC GFAS matched pairs and independent MISR/NAPS pairs;
6. evaluate the central and sensitivity runs using the unchanged v2 gates; and
7. archive every successful and failed command, input, output, warning, runtime,
   and checksum before interpreting the results.

## 2026-07-23 — ECMWF Data Portal acquisition decision

ECMWF Data Portal access became available after the November 2025 GFAS v1.2
archive had already been ingested. The frozen manifest was reinspected before
requesting another download. It contains 396 GRIB1 messages: 22 daily fields
for each of 18 variables on the global 0.1-degree grid. The file includes all
preregistered GFAS requirements (`pm2p5fire`, `cofire`, `bcfire`, `frpfire`,
`crfire`, `offire`, `apb`, `apt`, and `injh`) plus `mami` and additional carbon,
particulate, and gas species. Its SHA-256 remains
`f243c964a016f95f86932ce8ba00b66dc79c0ed6cabd95bb2be8ad37eb49821b`.

No additional ECMWF download is required for the frozen 2025-11-10 through
2025-12-01 experiment. The ECMWF Data Portal now distributes GFAS v1.4.2,
which became operational in December 2025, uses MODIS and VIIRS, and produces
hourly and 24-hour rolling-average fields. It is a scientifically different
product from the daily MODIS-based v1.2 archive and will not be spliced into the
November experiment.

For a future, separately versioned operational experiment, collect GFAS v1.4.2
analysis surface fields using the provider manifest as the completeness marker:

- hourly (`001`): `pm2p5fire`, `cofire`, `bcfire`, `apt`, `apb`, `injh`,
  `frpfire`, `crfire`, and `offire`;
- 24-hour rolling average (`024`): `pm2p5fire`, `cofire`, `bcfire`, and
  `crfire`; and
- optional aerosol diagnostics: `ocfire`, `tpmfire`, and `tcfire`.

That future collection must use a new product/version identifier and must not
alter the frozen v1.2 comparison. ECMWF access does not resolve the current
eligibility block: independent MCD64A1 burned-area pixels must still be
retrieved from NASA LP DAAC with Earthdata authorization.

## 2026-07-23 — Current-year input acquisition started

A separately versioned 2026 experiment was frozen for 2026-03-19 through
2026-05-31, with 2026-03-18 as one day of spin-up. The acquisition rationale,
source roles, exact file inventory, source gaps, commands, and remaining
authorization blockers are recorded in
`docs/smoke-validation-input-acquisition-2026.md`.

Completed public acquisitions include 675 NOAA GFS files, 74 source-available
CWFIS CFFDRS days, 69 source-available CWFIS Fire M3 days, 1,800 hourly AirNow
files, and the two 2026 EPA AQS PM2.5 archives plus station metadata. Satellite
catalogues were frozen for 69 MCD64A1 granules, 977 TROPOMI aerosol-layer-height
products, and 1,408 products for each of the two required EarthCARE ATLID
collections.

CWFIS does not provide hotspot files for 2026-03-25 through 2026-03-30 and its
CFFDRS WCS does not provide 2026-05-10. These are explicit provider gaps.
The public TROPOMI transfer subsequently completed all 977 catalogued products
(98,351,152,435 bytes). Authenticated GFAS v1.4.2 subsequently completed all
16,280 selected GRIB files and 1,850 provider completeness manifests. NASA
MCD64A1 and EarthCARE assets remain
authorization-gated; their exact catalogues are local, but catalogue presence
does not count as downloaded scientific data.

### Acquisition finalization

The GFAS transfer completed with 8,774,355,000 selected-data bytes. A late
portal response was truncated after 4,439,994 of 4,529,160 bytes; the atomic
downloader discarded the incomplete temporary file. A concurrent local DNS
outage prevented ordinary hostname resolution. The remaining 734 files were
retrieved by connecting to the DNS-over-HTTPS-resolved portal address while
retaining `aux.ecmwf.int` as the HTTP Host and TLS SNI name; certificate
verification was not disabled. The resumed transfer successfully re-fetched
the file that had been truncated.

The deterministic collection audit at that stage passed with status
`complete_with_provider_and_authorization_gaps`. The report is:

```text
/Volumes/BigMrStorage/weatherapp_data/weather/derived/smoke/validation/input-archives/observations-2026-2026-03-19_2026-05-31/verification.json
```

It verifies 675 GFS files, 222 CFFDRS grids across 74 source-available days,
96,017 normalized hotspot features across 69 source-available days, 1,800
AirNow hourly files, three AQS archives, 16,280 GFAS data files plus 1,850
provider manifests, 977 TROPOMI files, and seven frozen catalogue artifacts.
At that stage, NASA MCD64A1 and ESA EarthCARE were explicit authorization gaps.
No credential value was recorded in a data or verification manifest.

## 2026-07-24 — Current-year MCD64A1 acquisition completed

A NASA Earthdata token was supplied through the local `.env` file as
`EARTHDATA_TOKEN`. It was read only into process memory and was not printed or
recorded. The exact frozen CMR catalogue was used without another search.

LP DAAC authorized each catalogue URL with an HTTP redirect to NASA's CloudFront
object-delivery distribution. The downloader was tightened to allow only that
exact delivery host and to omit the Earthdata bearer token from the delivery
request. All 69 selected MCD64A1 v061 granules downloaded successfully,
totalling 258,259,753 bytes. Every file passed HDF4 signature validation and has
a SHA-256 checksum in:

```text
/Volumes/BigMrStorage/weatherapp_data/weather/raw/nasa/lpdaac/mcd64a1/v061/2026-manifest.json
```

The collection audit now treats MCD64A1 as a complete required input. Its
status is `complete_with_provider_gaps_and_optional_authorization_gap`: the only
remaining authorization-gated satellite collection is optional EarthCARE ATLID,
because the frozen experiment already has complete TROPOMI aerosol-layer-height
coverage. The CWFIS source gaps remain unchanged. Download completion does not
by itself complete MCD64A1 QA, event-area extraction, or scientific acceptance.

## 2026-07-24 — Current-year protocol frozen

Protocol `cffeps-flexpart-external-validation-2026-07-24-v1` was frozen at
2026-07-24 12:41:53 UTC, before reconciling 2026 events or reading any 2026
MCD64A1 Burn Date, QA, or uncertainty value. The frozen files and SHA-256
identities are:

- `docs/smoke-validation-protocol-2026.md`:
  `5718ee339a26b87e6791f7e0b79acdb58943d40f0fa30d43b368f63b858e838f`;
- `config/smoke/validation_2026.yaml`:
  `247ff9e6426aba732a00a0930821b5b883f6add61fa2d26add1b31dbde14c2a7`;
- `config/smoke/validation_candidate_2026.yaml`:
  `c36986bd8a39d126bad5182a5f32503fd92db1cb764959f586559144914bdae6`;
- unchanged event matching:
  `ecc56a9914eb74442ef33e2790629c9094110b91c3f47c14f0d94298d760b2c6`;
- unchanged MCD64A1 operator:
  `aefc9a786761fd4e4cb3fdaa252788844d2af3b3ae0ea65ba2938632d3bf89b9`.

The protocol predeclares Canadian point selection with Natural Earth Admin 0
v5.1.1; unchanged event reconciliation; unchanged MCD64A1 QA and ambiguity
rules; all area-qualified events with unique modal fuel; a Canada-wide fixed
transport domain; a midpoint reconstruction only for the May 10 CFFDRS source
gap; GFAS as diagnostic; TROPOMI as a mass-versus-extinction vertical
diagnostic; and AirNow/AQS as provisional surface tests. The declared
observation limitations mean that completing this experiment can produce a
scientific result but cannot, by itself, satisfy every production-unlock gate.

### Frozen 2026 event ledger

Natural Earth Admin 0 Countries 1:10m v5.1.1 was downloaded from its official
S3 distribution and frozen with SHA-256
`ce1ac7036499a0edd641fbc093cd209a98f96a49d2eca8480aaacad35138a7f6`.
The extracted `ADM0_A3=CAN` geometry contains 412 polygon parts and has SHA-256
`dda4dd4643f69228dde6b3b8362d02c42da8713bed07bf7d470d1aaff5a77344`.

Across the 68 source-available experiment dates, CWFIS supplied 92,841
normalized VIIRS-I features. Point-in-polygon selection excluded 85,030
features outside Canada. Fuel screening excluded 975 additional detections:
768 `farm`, 108 `water`, 71 `low_veg`, 25 `non_fuel`, and three unsupported
`M1/2_25` codes. The remaining 6,836 supported detections were reconciled into
329 frozen events. No detections were imputed for the six missing CWFIS dates.

The candidate event ledger SHA-256 is
`80181aa0b9028ae745fa46781f97ca9695909abce3d177f2843966de0cc34850`;
the ledger report SHA-256 is
`11566d51d70ab771b7f09fe910cc8dc87a45349ac1d20264872e41cf47d6b362`.
No MCD64A1 pixel value or candidate output had been inspected when these event
identities were frozen.

### MCD64A1 area attempts and v2 amendment

The first current-year area command failed before opening a science layer
because acquisition initially stored the monthly granules under product
day-of-year directories (`060`, `091`, and `121`), whereas the established
reader resolves the CMR product date to calendar-month directories (`03`,
`04`, and `05`). The downloader was corrected to use calendar months and to
migrate only files that already passed its HDF4 signature and size checks. All
69 files were moved, not redownloaded; the now-empty legacy directories were
retained. The acquisition manifest was regenerated with the same file hashes.

The second v1 attempt opened and QA-screened the granules but failed before
producing an event-area file:

```text
ValueError: conflicting cross-month MCD64A1 classifications at
(11087, 22254): (2026-04-24, 1, 3, 80, 140) !=
(2026-05-23, 1, 3, 104, 171)
```

The v1 operator keyed observations only by spatial coordinate, so it could not
represent a temporally distinct mapped burn at a previously burned cell. This
was a structural input-model failure. No candidate emissions, FLEXPART output,
observation matchup, or metric had been generated.

Protocol `cffeps-flexpart-external-validation-2026-07-24-v2` was therefore
frozen at 2026-07-24 12:49:05 UTC. It identifies a burn occurrence by global
row, global column, and burn date. Exact duplicate classifications are
deduplicated; different dates at one coordinate are retained as distinct
occurrences. Every other QA, association, candidate, and evaluation rule is
unchanged. Frozen files and hashes are:

- `docs/smoke-validation-protocol-2026-v2-amendment.md`:
  `3eb51047700f148d328e7c9ba3ac432f94ee089d83b2f45b6b4a6f0fc4fff478`;
- `config/smoke/mcd64a1_area_v2.yaml`:
  `d56286db419b177a724330542ce0b73221f12a1409cbdc3c30ade9bbba7d6eba`;
- `config/smoke/validation_candidate_2026_v2.yaml`:
  `deca72bdd517ef8051d25a262c18253c829b3ac8ac7cd57d6000b0852149801d`;
- `config/smoke/validation_2026_v2.yaml`:
  `27298c9179590888f85bdee3df69c61676895f5263d43f7df9f6f13136ebf9a0`.

Before rerunning the real data, ten targeted tests passed. They include
synthetic cross-month cases proving that distinct dates at one coordinate are
counted as separate daily occurrences, identical records are counted once,
and multi-event claims remain excluded.

The v2 operator completed at 2026-07-24 12:51:47 UTC. Across 69 granules it
found 3,820 QA-accepted burn occurrences at 3,818 spatial cells; two cells each
contained two distinct burn dates. No exact duplicate occurrence was present.
Of 329 frozen events, 22 had at least one spatiotemporal seed and six passed all
area/high-confidence/ambiguity requirements. The eligible population contains
four weak events, two moderate events, and no major event. The frozen
three-per-stratum design therefore failed before candidate execution.

The six events contribute ten UTC source days and 365 ha in total. Their frozen
fuel observations all have unique modes, so no additional fuel-tie exclusion
is required. None of those source days is the missing 2026-05-10 CFFDRS date;
the preregistered midpoint reconstruction is consequently not invoked.

The event-area report SHA-256 is
`c89771592451a53514a94ab0b9d7ac7ae03844a87673e4f0ad6aedce04b7f49d`;
the summary SHA-256 is
`5d59b4f5116433dfb9fe726fb8e13b00ff90ab15cb0a457ea2c4adb312f66c47`.
There are 410 burn occurrences claimed by more than one event; all were
excluded from every claimant under the frozen rule. Candidate execution
continues for all six eligible events even though the population-design gate
has already failed.

Candidate `attempt-001` then failed during configuration parsing, before its
output directory was created. The generic `FlexpartDomain` safety guard limited
the product of longitude span and latitude span to 2,500 square degrees. The
frozen Canada-wide box spans 3,827 square degrees despite containing only
3,960 output grid cells at 1-degree resolution. The guard also ignored grid
spacing, so it did not directly bound the allocated array it was intended to
protect.

The implementation guard was corrected to cap the actual horizontal output
grid at 50,000 cells, consistent with the simulation API limit. This admits the
unchanged frozen 90-by-44 grid and still rejects an excessively fine global
grid. No domain edge, spacing, source, physical option, model output, or
evaluation rule changed. Regression tests cover both the accepted frozen grid
and the rejected oversized case. Because no attempt directory or scientific
output existed, the rerun retains the `attempt-001` label; the preflight
failure remains recorded here.

The rerun of v2 `attempt-001` reached its first CFFEPS event-day and then failed
the 5% source mass check before FLEXPART preparation. Its raw output contains
1,220.575896 t of phase fuel released during the 24-hour driver window and
1,325.131590 t of cumulative consumed fuel, a 7.8902% difference. Source review
found that CFFEPS distributes fuel into future phase queues according to
combustion residence time. The v2 check omitted the queue remaining after hour
24 and therefore compared different accounting boundaries. The partial
attempt, input manifest, driver inputs, raw output, logs, hashes, and exclusion
reason are preserved; it is not a valid candidate result.

Protocol v3 was frozen at 2026-07-24 12:56:13 UTC before any v3 output. The
portable boundary now exposes the unmodified CFFEPS kernel's final pending
flaming, smouldering, and residual queues. The unchanged 5% unit-integrity gate
compares released plus pending fuel to cumulative consumption. Only fuel
actually released inside the unchanged 24-hour transport horizon enters
FLEXPART; pending mass and its fraction are mandatory truncation provenance.
No pending mass is moved earlier or assigned an invented injection height.
This resolves finite-window bookkeeping but explicitly does not provide
continuous multi-day source or smoke carry-over.

The frozen v3 configuration hashes are:

- `config/smoke/validation_candidate_2026_v3.yaml`:
  `5e1acc27a1905964b1b4891c014a5b05ffa2d27302f7d55d4e65e85769bc63fc`;
- `config/smoke/validation_2026_v3.yaml`:
  `48e26dff9bafe789ca31333926e75534052c968fdd627c0bd53b3cd03ac27473`;
- `docs/smoke-validation-protocol-2026-v3-amendment.md`:
  `1505d5294d17910e2c2c768b2b3cdab80cf7e39fa97240c65474d9f1fc8666a6`.

The rebuilt portable executable SHA-256 is
`80475fa0b30ef65beafb4ac2b52ab416e1ac0e335951cccbb4f5adf671aaa885`;
the local driver/patch identity is
`adedc358c618daf8284f1caf377231a26ad3cbb5786e1f4fd2700b3d2453a542`.
The ten updated golden cases retain identical plume heights, areas, and
in-window phase masses while their exact CSV hashes change only because the
three pending-queue columns were added.

Version 3 completed eight valid CFFEPS source days, then stopped before any
FLEXPART member was prepared because the frozen CWFIS FFMC grid is `NoData` at
event `f8bad2a73b535ddc231c97f7` on 2026-04-21. An input-only audit confirmed the
same missing FFMC cell on 2026-04-22 and valid FFMC/DMC/DC samples on all eight
source days belonging to the other five events. The partial v3 outputs and
their hashes are preserved in `attempt-status.json` and excluded.

Protocol v4 was frozen at 2026-07-24 13:05:20 UTC before any v4 candidate
output. It explicitly preflights unique fuel, frozen-domain inclusion, and
checksum-verified FFMC/DMC/DC coverage for every positive-area source date.
An event missing any required state is excluded in full, with all dates and
errors recorded. Sampled state and source-manifest hashes are frozen in the
input manifest and reused for CFFEPS. This input-availability rule does not
inspect model or observation performance. The event is not replaced.

The v4 hashes are:

- `config/smoke/validation_candidate_2026_v4.yaml`:
  `640471b011a06370d882695dda070ad1b0a97f3e3a0af85383d91095df918817`;
- `config/smoke/validation_2026_v4.yaml`:
  `341a1131347a04cb534891b1b7989a268f77183d4fe43405b2aaa46753f1f287`;
- `docs/smoke-validation-protocol-2026-v4-amendment.md`:
  `793960a35fd89e05cf8e1b552f32e721fb18388cd54f3c8cbdd139c6bfe0510c`.

## 2026-07-23 — MCD64A1 v6.1 acquisition organized

A user-provided NASA Earthdata batch named
`MCD64A1_061-20260723_190404` was found under the repository's temporary
`data/` directory. Inspection showed that it contains the complete global
MCD64A1 monthly product for November and December 2025 rather than only the
46 Canada-intersecting granules selected by the frozen CMR query:

- 268 HDF4 granules for product day `A2025305` (November);
- 268 HDF4 granules for product day `A2025335` (December);
- 536 granules and 1,025,284,518 bytes in total; and
- all 46 granules in the frozen Canada CMR selection present by exact producer
  granule ID.

The files were moved without renaming into the raw-data hierarchy:

```text
raw/nasa/lpdaac/mcd64a1/v061/
├── 2025/11/   # A2025305, 268 granules
├── 2025/12/   # A2025335, 268 granules
├── cmr/       # frozen Canada catalogue query
└── manifests/ # batch metadata and per-granule SHA-256 inventory
```

The machine-readable batch manifest is
`raw/nasa/lpdaac/mcd64a1/v061/manifests/MCD64A1_061-20260723_190404.json`.
The 536-line checksum inventory has SHA-256
`5d03bdbed76b4aa15b5b3736eb20bbf0134b034923ee90ea71d3d6bdc3a7d026`.
The `file` utility recognized all 536 objects as HDF4. The locally installed
GDAL build does not include an HDF4 driver, so storage integrity and CMR
membership are verified but scientific decoding of `Burn_Date`,
`Burn_Date_Uncertainty`, `QA`, `First_Day`, and `Last_Day` remains pending.
The prior eligibility report remains an immutable account of the earlier
blocked attempt; a new audit will be issued after layer decoding and QA.

## 2026-07-23 — MCD64A1 decoding, area eligibility, and candidate execution

### Observation operator freeze

The MCD64A1 event-area operator was specified and frozen at
2026-07-23 19:32:57 UTC, before any `Burn_Date` pixel values were read. The
full method and rationale are in `docs/smoke-mcd64a1-area-operator.md`; the
machine-readable configuration is `config/smoke/mcd64a1_area.yaml`, SHA-256
`aefc9a786761fd4e4cb3fdaa252788844d2af3b3ae0ea65ba2938632d3bf89b9`.

The operator reads the HDF4 scientific data sets directly with pyhdf 0.11.7,
checks the tile identity and product metadata, and uses the native MODIS
sinusoidal grid. Each 463.3127165 m pixel represents 21.46586733 ha in this
equal-area projection. Central estimates require land, valid data, a non-zero
burn date inside the tile's reliable mapping interval, and retain the
contextually relabelled and shortened-mapping QA states. The high-confidence
curve additionally excludes both of those states. Event assignment uses a
1,500 m detection seed, burn-date uncertainty, a one-day event-time pad, and
8-neighbour connected growth. A pixel claimed by multiple events is excluded
from every claimant rather than assigned subjectively.

The exact execution was:

```bash
.venv/bin/python scripts/build_mcd64a1_event_areas.py \
  --mcd64-root /Volumes/BigMrStorage/weatherapp_data/weather/raw/nasa/lpdaac/mcd64a1/v061 \
  --cmr /Volumes/BigMrStorage/weatherapp_data/weather/raw/nasa/lpdaac/mcd64a1/v061/cmr/2025-11_2025-12-canada.json \
  --events /Volumes/BigMrStorage/weatherapp_data/weather/derived/smoke/validation/experiments/gfas-v1.2-2025-11-10_2025-12-01/eligibility/candidate-events.json \
  --config config/smoke/mcd64a1_area.yaml \
  --start 2025-11-10 \
  --end 2025-12-01 \
  --output-directory /Volumes/BigMrStorage/weatherapp_data/weather/derived/smoke/validation/experiments/gfas-v1.2-2025-11-10_2025-12-01/mcd64a1/mcd64a1-event-area-v1
```

Two synthetic tests verified connected-scar growth, exact pixel-area
accounting, daily allocation, and conservative overlap exclusion before the
real execution.

### Burned-area result

All 46 Canada-intersecting CMR granules decoded successfully. They contained
282 QA-accepted pixels with burn dates in the experiment interval, including
23 contextually relabelled pixels and no shortened-mapping pixels. No interval
pixel failed the land, valid-data, or reliable-window screens, and no identical
cross-month duplicate was found.

Five of the 869 frozen events seeded an accepted scar. Four received at least
one unambiguous central and high-confidence pixel and became area eligible.
Two pixels were claimed by more than one event and were excluded. The eligible
event areas were:

| Frozen event | Fuel selected later | Central area (ha) | Stratum |
|---|---:|---:|---|
| `0d345695144eaf09813a566f` | C3 | 64.3976 | weak |
| `064ab7723737feddb2f8a046` | C4 | 85.8635 | weak |
| `3c1fcc5d180489359985b4d5` | C5 | 107.3293 | moderate |
| `078b2261a884fd95c1e881d3` | C3 | 150.2611 | moderate |

This resolves the independent-area block for these four events, but it does
not satisfy the preregistered population design: there are two weak, two
moderate, and zero major events, versus a target of three per stratum.
Consequently, this window can test components and produce a diagnostic
inventory comparison, but cannot support a population-wide scientific
acceptance claim.

The event-area report SHA-256 is
`7cb7de0338e4707dcdad566e8bfe39d0f054c07c032d12c3ac2df13810a53b9f`;
the compact summary SHA-256 is
`946fbc49e15a02057a937b0bf9f32ec615d534e99f5685f50a5a6be1fed2ee72`.

### Frozen central candidate

The central candidate was specified independently of GFAS values and frozen as
`november-2025-mcd64a1-central-v1`. Its configuration SHA-256 is
`dcf91ba627149c60617f3987d67cbf3ba4a6045f37ab3bfe1af24f1c2d959d52`;
the full method is in `docs/smoke-validation-candidate-run.md`.

The candidate includes every area-eligible event and all ten independently
dated burned-area increments. Event fuel is the unique modal fuel among the
already frozen CWFIS detections. Each increment receives dated CWFIS
FFMC/DMC/DC, a complete same-day GFS 00 UTC profile, a linear 00–24 UTC area
curve, and central CFFEPS factors. PM2.5, CO, and black carbon are transported
in isolated 24-hour FLEXPART members so aerosol settling remains enabled.
Each species-day member uses 150,000 particles, a deterministic recorded seed,
all required transport physics, and hourly output.

Ten CFFEPS 4.1 executions completed successfully, and the combined emissions
bundle passed its structural and mass-conservation validator. The first
sequential FLEXPART pilot, PM2.5 for 2025-11-10, also completed successfully.
FLEXPART reported 642.375 seconds for 86,400 simulated seconds and 149,960
particles, ending with its successful-completion marker. The concentration
file SHA-256 is
`3f8971301c7dd8c8d893cb2a876522e93fa1cee9e47bb3132e6b2a5364c29da4`.

The automatically started CO member was intentionally interrupted before
completion after the pilot established real workload. It is excluded from all
results. This failed/partial attempt is preserved as `attempt-001`, including
`attempt-status.json`, rather than overwritten or silently deleted.

Because all 24 species-day members are scientifically independent and have
distinct run directories and deterministic seeds, the execution runner was
extended to schedule a bounded number of members concurrently. This changes
only process scheduling; it does not change scientific inputs or outputs.
Worker count and threads per member are now recorded in both input and result
manifests. Ruff passed, the Python modules compiled, and 12 targeted candidate
and smoke-pipeline tests passed before `attempt-002` began with six member
workers and eight OpenMP threads per member.

### Source-unit failure discovered by the diagnostic

The first `attempt-002` GFAS pairs reported only 0.5207 kg PM2.5, 3.1544 kg CO,
and 0.01752 kg black carbon from all ten event-days. These were not accepted as
scientific results. Tracing the normalized bundle back through the adapter and
portable Fortran output found that the CFFEPS phase arrays contain a
`1.0e-3` storage factor while the portable CSV labelled the values as metric
tonnes per hour. The CFFEPS cumulative consumed-fuel field has no such factor.

For all ten real event-days, multiplying the summed hourly phase arrays by
1,000 reproduced CFFEPS's cumulative consumed-fuel total. The ratio ranged
from 0.9936393 to 1.0000006; the small deficit in some cases is attributable
to phase residence-time mass extending beyond the 24-hour output boundary.
This is independent internal evidence for the unit diagnosis, not a correction
chosen to improve agreement with GFAS.

The invalid GFAS comparison and three already completed invalid transport
members are preserved under `attempt-002`, with their hashes and exclusion
reason in `attempt-status.json`. They do not count as a candidate result.

The portable driver now converts the arrays to the labelled metric-tonnes-per-
hour contract at the boundary. The adapter also requires the summed phase fuel
to agree with CFFEPS's cumulative total within 5%, making a recurrence of the
1,000-fold mismatch a hard failure. The rebuilt executable SHA-256 is
`0ff727ca54af92d7feda528135dc4ac3ba2ce0ac7556130c45b450e5da48b339`;
the local scientific driver/patch SHA-256 is
`8618ed789f66af1618fc7c270632b2d5d26632ae980fa066c970e45b51fe6183`.
All ten deliberately updated golden cases, six FBP sensitivities, 17 targeted
Python tests, and Ruff passed before a clean `attempt-003` was started.

### Daily-area conservation failure and v2 amendment

An additional source check during corrected v1 `attempt-003` summed the
`incremental_area_m2` values recorded in each event-day manifest. Every run
assigned exactly 95.8333% (`23/24`) of its MCD64A1 increment. CFFEPS's first
profile initializes state with zero phase fuel, leaving 23 active phase
intervals; the original curve operator did not redistribute the first
interval's area.

The run was stopped after 13 transport members had completed. Its valid unit
correction, invalid area allocation, corrected-but-incomplete GFAS diagnostic,
completed members, and exclusion decision are preserved under v1
`attempt-003/attempt-status.json`. No output from this attempt counts as a
candidate result.

Because temporal area allocation is a scientific operator, it was not silently
changed under v1. Candidate `november-2025-mcd64a1-central-v2` was frozen at
2026-07-23 20:16:08 UTC, before any v2 output. Its configuration SHA-256 is
`3a9832b6be385ff5a4e7f1368de5c05af6e0265c0fc9c96697ef982713951285`.
The amendment in `docs/smoke-validation-candidate-v2-amendment.md` conserves
the full daily MCD64A1 increment by proportionally normalizing the linear target
over active CFFEPS intervals. For this experiment the factor is exactly
`24/23`. All other scientific settings and all preregistered evaluation
thresholds remain unchanged.

### Corrected v2 central result

Candidate `november-2025-mcd64a1-central-v2`, `attempt-001`, completed at
2026-07-23 20:26:11 UTC. Ten CFFEPS source runs used the four eligible fires,
ten event-days, and 407.851479 ha of independent MCD64A1 area. Every daily
increment was conserved exactly within floating-point tolerance. The maximum
relative CFFEPS phase-fuel versus cumulative-fuel difference was 0.006361,
inside the frozen 0.05 hard gate.

The normalized bundle contains 16,560 release records and has SHA-256
`30128dc48e94bb1406f837e3b47c47d265f6db15899f96de7fd5a4fd7983a74e`.
Its species masses are 543.372678 kg PM2.5, 3,291.584587 kg CO, and
18.286587 kg black carbon.

All 24 species-day FLEXPART members completed in 569.133 seconds with six
independent member processes and eight threads per member. The independent
output verifier passed all members, 3.6 million particles, 16,560 releases,
24 hourly fields per member, nine heights, mass equality, distinct seeds,
completion markers, concentration hashes, and finite nonnegative nonzero
concentrations. The candidate manifest SHA-256 is
`c008b18d52b6dbe494eb1f6bcf6792dd99bde2d6dcb65960038d3e7c7c793fd9`;
the verifier report SHA-256 is
`60e7260bbe3962596aa23b3ee911dbacd206941fcb6a1e3b8123095029930c7a`.

After execution, 204 Python tests passed and 19 database integration tests were
skipped because `WEATHER_TEST_DATABASE_URL` is not configured. All ten CFFEPS
golden cases and six FBP sensitivity cases passed. Ruff passed for every
changed validation file, and `uv lock --check` passed.

### GFAS diagnostic result

The frozen domain-wide active-union operator produced 375 grid-cell-day pairs
per species. Only ten cell-days contain CFFEPS emissions from the four
independently supported events, while 366 contain GFAS emissions. PM2.5, CO,
and black carbon all failed the frozen diagnostic thresholds:

| Species | NMB | Pearson R | FAC2 |
|---|---:|---:|---:|
| PM2.5 | -0.999960 | -0.0339 | 0.000 |
| CO | -0.999971 | -0.0345 | 0.000 |
| Black carbon | -0.999970 | -0.0348 | 0.000 |

The GFAS manifest SHA-256 is
`917efe5ddb6b893f55ba5c6dea4848b72dcb20959cd8a8f9e6f8f0b7e52bde67`.
This failure is retained. Event-coverage incompleteness is a dominant known
cause because GFAS includes all active fires in the domain, but the result does
not establish that the four event-level CFFEPS sources are unbiased. GFAS is
not an acceptance-capable observation and this comparison does not evaluate
FLEXPART transport.

### Verification decision

The central source and transport chain is computationally verified. Scientific
acceptance under the frozen protocol is **not passed**. The event set lacks a
major fire and the full per-stratum design; the GFAS diagnostic has an
unresolved gross discrepancy; MISR plume-height and hourly NAPS
smoke-enhancement gates have not run; the required sensitivity matrix and
independent scientific reviews remain incomplete; and four scheduled-cycle
runs have not been demonstrated.

The complete assessment is recorded in
`docs/smoke-validation-verification-2026-07-23.md` and its machine-readable
companion `docs/smoke-validation-verification-2026-07-23.json`. This result
does not support removing the production submission lock.

The Markdown assessment SHA-256 is
`249e477efcb61d8ac29697967087707a82ad837d3a8db8210631e2361764270a`.
The JSON assessment SHA-256 is
`1b41e02f803548e39dc69bae858fa9d386085427ed5f918c7437d4d19759ce23`;
an identical copy is stored beside the run's output-verification report as
`verification/scientific-acceptance-status.json`.

## 2026-07-24 — March–May 2026 validation execution

### Frozen protocol chain and candidate

A separate current-year experiment was frozen for 2026-03-19 through
2026-05-31. Its protocol was amended in versioned stages rather than silently
changing failed operators:

- v2 represented a mapped reburn with a `(cell, burn date)` MCD64A1 occurrence
  key after the original spatial-only key failed before area output;
- v3 closed finite-window CFFEPS accounting with released plus final queued
  phase fuel after the first source-day hard gate failed;
- v4 excluded one entire event before output because the official CWFIS FFMC
  raster was `NoData` on both of its source days;
- v5 froze the exact AirNow/AQS surface operator before pair generation; and
- v6 froze six one-factor sensitivities before their output existed.

The MCD64A1 operator found six eligible events: four weak, two moderate, and no
major fire. The population design therefore failed before candidate execution.
The incomplete-FFMC exclusion left five events and eight source days in central
candidate `march-may-2026-mcd64a1-central-v4`.

The central candidate completed 24 species-day FLEXPART members in 265.417 s:
3.6 million particles and 16,272 releases. In-window mass was 111,273.8172 kg
PM2.5, 699,609.7036 kg CO, and 1,927.8362 kg BC. The candidate-manifest
SHA-256 is
`cd92715ca22f94f23118cc6304dd9c4b8b01fd507b39e54560532b031dc5aa33`.

The upgraded schema-v2 verifier checks concentration, wet deposition, and dry
deposition. Central passed all 24 complete members, release masses, unique
seeds, checksums, dimensions, hourly times, nine heights, completion markers,
finiteness, non-negativity, and nonzero concentrations. Its report SHA-256 is
`a93d60f4c578cf1dd73ce90c6367820493f6c294196e6bcb90505237eed07be2`.

### CFFEPS finite-window audit

CFFEPS reported 4,054.9270378 t cumulative consumed fuel. The 24-hour source
windows released 3,626.9706623 t (89.4460%), retained 421.1339681 t
(10.3857%) in final combustion queues, and left 6.8226212 t (0.1683%)
unaccounted within the per-event 5% gate. Every event-day passed. The latter
mass is the two O1A grass cases' 5% kernel remainder. No queued mass was shifted
into an earlier interval. Audit SHA-256:
`f8e4ca40063c06210154d70d30b26df91d6f96b4ab68c773c15c67dac45e4fd8`.

### External diagnostics

The checksummed GFAS v1.4.2 bundle contains eight source days and three
species. Every species produced 1,088 active-union cell-day pairs and failed
the frozen diagnostic:

| Species | NMB | R | FAC2 |
|---|---:|---:|---:|
| PM2.5 | -0.956146 | 0.142479 | 0.001840 |
| CO | -0.970501 | 0.140121 | 0.001840 |
| BC | -0.985563 | 0.143269 | 0.000920 |

The domain-wide GFAS field contains all GFAS-active fires while the candidate
contains five independently area-supported events. This is a known dominant
coverage confounder, but the gross discrepancy remains a failed diagnostic.
The bundle SHA-256 is
`fc314a88a17bf542efa20a2f71e32d014da43254281f6e29aca5bde32600cfec`;
the pair-manifest SHA-256 is
`4748c722b0cec5321740c096984691844a624a0a9f235faf59f9da95c906bd40`.

TROPOMI produced 83 quality-screened pixel/model pairs. Pair count, mean bias
(-1,140.8 m), and R (0.5160) passed, but RMSE (2,734.0 m) failed its 2,500 m
criterion. The comparison remains diagnostic because aerosol extinction
height is not the same quantity as modelled aerosol mass height and because
pixels are clustered within overpasses and fires. Pair SHA-256:
`a8d28b82056a8b58318955d35400ac4d5bbf3da2b5052544758d9253f1b41423`.

AirNow scanned 1,416 hourly files and produced only 14 pairs. Median-background
NMB, NMAE, and R were -0.9218, 1.0457, and -0.4177; the 20th-percentile
sensitivity was -0.9750, 0.9779, and 0.1429. All criteria, including the
100-pair minimum, failed. AQS streamed 2,315,564 records but no US monitor
coincided with an active model cell/hour, so zero pairs were retained. Both
sources are provisional and cannot satisfy scientific acceptance.

### Sensitivities and deposition

Low and high emission factors, high-confidence area, uniform vertical
injection, 300,000 particles, and one thread were run as frozen one-factor
candidates. The emission-factor bracket was ordered for every species. The
particle candidate differed from central by 0.00956 normalized concentration
L1 with R 0.99995. Uniform injection had the largest mass-invariant effect:
0.5600 normalized L1 and R 0.8451.

The high-confidence area candidate had the same retained source mass as
central, so its 0.00893 normalized L1 difference represents stochastic rerun
variation rather than a broad area perturbation.

The one-thread concentration field was finite and close to central, but the
May 25 PM2.5 member contained two non-finite cumulative wet-deposition values
at the grid corner in the final two times. The upgraded whole-output verifier
failed it; report SHA-256:
`a9012ba0521a24485c175218fe7d331451944888fdd8af080d3f4532bebb7067`.
This failure is retained and was not hidden by evaluating concentration alone.

Central final cumulative deposition was 22,946.3043 kg PM2.5 (20.6215% of
released mass), 43,310.9379 kg CO (6.1907%), and 368.2718 kg BC (19.1029%).
These values use each independent day-member's final cumulative field, not a
sum over cumulative hourly fields. An initial exploratory total that summed
all cumulative times was overwritten as methodologically invalid. The final
field-comparison report SHA-256 is
`0b5e092ed25122842a84b622c21c874febc88bbc877847ae44cd0e2f876078d0`.

### Decision and publication record

The central implementation is computationally verified, but scientific
acceptance is not passed. The population design, GFAS gross-discrepancy gate,
acceptance-capable vertical and final surface observations, complete
sensitivity matrix, independent reviews, and four scheduled cycles remain
blocking. The simulation-write lock must remain enabled.

Publication-oriented theory and methods are in
`docs/smoke-validation-methods-2026.md`; numerical results and limitations are
in `docs/smoke-validation-results-2026.md`. A machine-readable decision is
generated from the immutable artifacts by
`scripts/build_smoke_validation_assessment_2026.py`.

After the final assessment and documentation code was present, the complete
Python suite reported 220 passed, 19 PostgreSQL integration tests skipped
because `WEATHER_TEST_DATABASE_URL` is not configured, and eight non-fatal
warnings. Ten CFFEPS golden cases and six FBP sensitivity cases passed. Ruff
passed every changed validation Python file and test, and `uv lock --check`
passed with 91 packages resolved. The structured software-verification record
is `docs/smoke-validation-software-verification-2026-07-24.json`.

## 2026-07-24 — Prospective scientific acceptance research program

The negative March–May assessment was translated into eight prospective
research workstreams without changing its result:

1. assemble at least three weak, three moderate, and three major fires;
2. reconcile GFAS with a preregistered like-for-like event-support analysis;
3. build an acceptance-capable MISR/lidar vertical comparison;
4. build a final hourly NAPS PM2.5 smoke-enhancement comparison;
5. reproduce and fix the one-thread wet-deposition non-finite values;
6. complete meaningful area and wet/dry deposition sensitivities;
7. obtain independent emissions and air-quality review; and
8. complete four consecutive scheduled validation shadow cycles.

The program uses separate source/GFAS, vertical-overpass, and surface-monitor
holdout cohorts sharing one frozen model release. This avoids choosing one
short window that lacks enough observations while preserving separation from
training. Current official discovery routes for MCD64A1/VNP64A1, CWFIS,
NOAA historical meteorology, GFAS v1.4.2, MISR/MINX, CALIOP, and final NAPS
were checked before writing the acquisition plans.

The master sequence, individual plans, definitions of done, implementation
entry points, risks, artifact layouts, and machine tracker are under
`docs/smoke-validation-research-program/`. This planning work does not alter
the `not_accepted` status or authorize production simulation writes.

## 2026-07-27 — Expanded MISR cohort and publication update

The original W3 availability sample was expanded without opening FLEXPART
output. The public MERLIN endpoint was queried for every year from 2017
through 2026-07-27. It returned 9,976 provider records, all from 2017 and
2018. Every Canadian-interior MINX file returned by the fixed geographic
screen was downloaded.

The final acquisition contains 772 files and 65,274,882 bytes. File size and
SHA-256 verification passed for all 772. Red/blue files were grouped into 388
band-independent plume families across 78 orbits. Height-blind QA selected
386 families. The provisional post-selection requirement of at least 10
wind-corrected retrievals at or above 250 m AGL retained 109 observations.
All 109 received complete Fire M3 fuel and CFFDRS state; 88 also passed the
independent MCD64A1 area operator and span 37 orbits.

This result supersedes the earlier six-of-16 statement only as an availability
claim. It does not overwrite that experiment, constitute independent review,
or establish model skill. The expanded candidates still require physical-fire
clustering, central/reserve selection, historical GFS, causal CFFEPS
histories, protocol refreezing, and formal FLEXPART comparisons.

Publication-facing abstract, introduction, methods, results, interpretation,
and limitations were updated in
`docs/smoke-validation-research-program/w3-expanded-misr-publication-update-2026-07-27.md`.
The March–May methods and results records now carry prospective addenda while
retaining their original `not accepted` decision.

## 2026-07-27 — Integrated full manuscript draft

A complete journal-style paper was drafted at
`docs/research-paper-cffeps-flexpart-validation.md`. It integrates the CFFDRS,
MCD64A1, CFFEPS, vertical-adapter, FLEXPART, GFAS, MISR/MINX, and surface-PM2.5
theory; governing equations and units; data and software identities; the
March–May pilot; the zero-skew numerical investigation; the W1 input
inventory; the original and expanded W3 cohorts; assumptions; limitations;
reproducibility; claim status; and the remaining preregistered sequence.

The paper labels unexecuted central experiments as future work. It does not
report MISR–FLEXPART skill metrics, final-NAPS performance, or scientific
acceptance that do not yet exist. Human authorship, contributions, conflicts,
acknowledgements, external review, and a version-controlled publication
release remain to be completed.
