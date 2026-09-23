# Formal W2–W8 sequence execution record

**Started:** 2026-07-27  
**Candidate:** `cffeps-flexpart-successor-2026-v1`  
**Status:** machine prerequisites complete; independent-review gate blocks formal holdout

> **Superseding W3 update, later on 2026-07-27:** The earlier r7 vertical
> readiness result below established input availability only. Subsequent
> height-blind observation QA and causal-emission construction leave 6
> eligible overpasses versus the formal minimum of 10. The status-only W3
> final readiness r3 SHA-256 is
> `73d6ad2319af348417587a68729e16519249bcf4a4e8a39d65122f2c4e818104`.
> Formal W3 execution remains unauthorized. See
> [the complete addendum](2026-07-27-w3-blind-observation-and-causal-emissions.md).

> **Expanded-availability addendum, later on 2026-07-27:** An exhaustive
> 2017-current MERLIN query identified 109 observation-qualified candidates;
> 88 also have complete Fire M3 and MCD64A1 area inputs across 37 orbits. This
> resolves the candidate-availability shortage but does not amend the
> original cohort. Physical-fire clustering, central/reserve selection,
> historical GFS, causal emissions, and independent review remain incomplete.
> See
> [the expanded MISR inventory](2026-07-27-w3-expanded-misr-2017-current.md).

## 1. Purpose and execution rule

This record covers the requested sequence:

1. W2, W3, and W4 central experiments;
2. all 16 frozen W6 sensitivity runs;
3. final W7 independent review;
4. one uncounted W8 rehearsal; and
5. four later consecutive scheduled W8 cycles.

The prospective firewall remains binding. Central and sensitivity holdout
outputs must not be opened until the machine Phase 0 preflight passes. Phase 0
requires complete input-only prerequisites and favourable, artifact-specific
pre-execution decisions from both required independent reviewer roles. W8
requires the final reviewed release and real elapsed schedule windows. A
locally generated signoff or synthetic cycle timestamp would not be scientific
evidence.

`SIMULATION_WRITES_ENABLED` remains false. Nothing in this work authorizes
interactive or production simulation writes.

## 2. W3 input-only fire assignment

### 2.1 Frozen population

The existing W1 availability ledger contains 16 prospectively selected,
unique MISR orbit overpasses: eight from June–August 2017 and eight from
June–August 2018. Selection was previously performed using a fixed seeded
rank over provider availability. No candidate-model output was involved.

The complete candidate-pool rule is now explicit:

- the 16 selected orbit overpasses are the complete frozen pool;
- input-invalid cases may be excluded only before model output;
- there is no performance-based replacement; and
- W3 fails for insufficient sample size if fewer than ten cases survive input
  validity and independent observation QA.

### 2.2 Fire M3 acquisition and assignment operator

The public NRCan CWFIS Fire M3 annual hotspot archives for 2017 and 2018 were
downloaded from the provider archive and frozen with acquisition manifests and
SHA-256 hashes.

`scripts/build_vertical_input_assignments.py` implements the input-only
assignment operator `firem3-location-time-frozen-source-v1`. For every frozen
overpass it:

1. groups MERLIN records that share source time and coordinates;
2. searches Canadian Fire M3 records within 5 km and 3 hours;
3. requires a supported FBP fuel and finite FFMC, DMC, and DC;
4. ranks valid matches by distance, absolute time offset, MISR region name,
   and provider-row SHA-256; and
5. writes separate checksummed fire-assignment, fuel, and CFFDRS-state
   artifacts.

The builder does not read plume-height fields or candidate output. All 16
overpasses received a Fire M3 assignment. The maximum selected discrepancy
was 0.54 km and 33 minutes; most selected records were effectively coincident
with the MERLIN source coordinates and time.

### 2.3 Independent burned area

NASA MCD64A1 Collection 6.1 catalogues were frozen separately for
June–August 2017 and June–August 2018. All 138 catalogued HDF granules were
downloaded with the configured Earthdata authorization:

- 69 granules and 210,121,899 bytes for 2017;
- 69 granules and 214,258,368 bytes for 2018.

The preregistered MCD64A1 v2 occurrence operator was applied separately to the
eight frozen source events in each year. It uses QA-valid MODIS sinusoidal
burn occurrences, burn-date uncertainty, a 1.5 km source seed, eight-connected
scar growth, and exclusion of occurrences claimed by more than one event.

Results:

- 2017: 8/8 events had eligible independent area;
- 2018: 7/8 events had eligible independent area;
- `2018-O098725` was excluded before model output because it had no
  spatiotemporally matched, unambiguous, high-confidence burn occurrence; and
- 15 input-qualified overpasses remain, still above the formal minimum of ten.

The weak/moderate/major distribution target is descriptive for W3 and is not
the W3 pass/fail rule. The W3 acceptance unit remains one independently
QA-screened fire-overpass.

### 2.4 Historical transport meteorology

The current NOAA cloud archive does not contain 2017/2018 GFS objects. The
official historical source selected for this input-only completion is NSF
NCAR GDEX dataset
[d084001](https://gdex.ucar.edu/datasets/d084001/),
DOI `10.5065/D65D8PWK`, which archives NOAA/NCEP GFS 0.25-degree analysis and
forecast grids.

`scripts/download_w3_gfs_gdex.py` freezes:

- the 00 UTC cycle on each surviving overpass date;
- one fixed prior spin-up day;
- forecast hours 0 through 24 at three-hour intervals;
- the provider URL, local path, byte size, and SHA-256 of every object; and
- ecCodes verification of grid dimensions, valid/initialization time, at
  least 20 common pressure levels for U, V, W, temperature and humidity, plus
  the required surface fields.

The fixed request contains 29 cycles and 261 GRIB2 files (54,352,724,120
provider-listed bytes). Completion and validation are recorded in the final
artifact inventory below.

The downloader also emits the exact normalized `provider=noaa`,
`product=gfs`, `filename`, forecast-hour, and valid-time fields consumed by
the existing profile extractor and FLEXPART run preparer. Archive provenance
remains explicit as NSF NCAR GDEX dataset `d084001`.

This acquisition is necessary but is not, by itself, a frozen W3 release
history. The emissions/plume reviewer must still freeze the causal
pre-overpass operator that determines which MCD64A1 area increments can
contribute, how burn-date uncertainty is handled, the spin-up interval, and
how the Fire M3 CFFDRS state evolves over that interval. That distinction is
recorded as a blocking pre-execution issue; a file-completeness audit must not
be mistaken for scientific approval of the source-history model.

## 3. W4 performance-blind background exclusions

`scripts/build_w4_background_exclusions.py` implements the machine-resolvable
part of the final-NAPS background freeze without reading NAPS concentration or
candidate output.

The operator:

- excludes all 77 frozen retained/reserve source dates nationally;
- scans the complete 2023 NRCan Fire M3 archive;
- for each Canadian satellite fire within 150 km of a frozen NAPS station,
  excludes station hours from the first whole UTC hour at or after detection
  through 24 hours afterward; and
- retains the nearest supporting detection, time, sensor, source, and distance
  for each excluded station-hour.

The resulting ledger contains:

- 3,674,409 annual Fire M3 rows scanned;
- 3,113,811 Canadian rows in the background-screen interval;
- 2,794,566 station/detection proximity matches; and
- 284,291 unique station-hour exclusions.

The artifact remains explicitly
`machine_fire_screen_complete_pending_independent_review`. An independent
air-quality reviewer must still check known non-wildfire exceptional-event and
maintenance/calibration records. Missing/invalid final-NAPS values and the
constant-coordinate station-history check are already machine enforced.

## 4. Prospective-firewall deviation

During mechanics inspection, the first lines of one raw MINX text file were
displayed in the implementation session. Its header contains observational
height summaries. No displayed height was used in overpass selection, Fire M3
matching, MCD64A1 processing, exclusion, or model configuration; those
decisions are implemented by deterministic code that does not access height
fields.

Nevertheless, this is a real blinding deviation and must not be hidden. The
implementation author cannot serve as the independent W3 observation reviewer.
Before formal execution, the emissions/plume reviewer must:

1. review the deterministic assignment operator and complete 16-case audit
   trail;
2. independently decide which MINX retrieval represents each fire-overpass
   under a prospectively recorded QA/band rule;
3. review plume boundary, source attribution, terrain and wind treatment
   without viewing candidate output; and
4. explicitly accept or reject this deviation in their pre-execution signoff.

If the reviewer judges that the deviation compromises the holdout, the current
vertical cohort must be retired and a new prospective cohort frozen. It must
not be repaired by selecting cases based on agreement.

## 5. Formal execution gate

The central W2/W3/W4 experiments and W6 matrix are not run merely because
their software exists. They start only when a fresh Phase 0 artifact reports
`holdout_execution_authorized: true`.

Known non-machine substitutions are prohibited:

- the implementation author cannot create either W7 reviewer decision;
- a pending independent W4 review cannot be marked complete by software;
- manual MINX QA cannot be inferred from MERLIN availability alone;
- a W8 rehearsal cannot precede the reviewed release; and
- four consecutive W8 cycles must occupy four actual announced schedule
  windows.

The refreshed review package carries three open blocking issues:

1. independent W3 MINX observation QA and disposition of the documented
   blinding deviation;
2. the causal pre-overpass W3 emissions/source-history and historical-GFS
   interface; and
3. independent W4 exceptional-event, maintenance/calibration, and station
   history review.

## 6. Artifact inventory and final outcomes

### 6.1 Completed machine prerequisites

| Artifact | SHA-256 | Outcome |
|---|---|---|
| W3 normalized GDEX GFS acquisition ledger r2 | `55e083f1de456100a2e0588e442223e9b381fe6d633cfc98820a9a6abecbd5a0` | 29 cycles; 261/261 GRIB2 files content-valid; 54,352,724,120 bytes |
| W3 input-only assignment ledger r2 | `ce541e36a02cf7e54ab56a2b58708705830263f0828ce5359108ef7f87060d15` | 16 assigned; 15 area- and meteorology-complete; one pre-output area exclusion |
| W3 vertical readiness r7 | `f7077b216fff6d99103a9063618f53ca591852f14fed1839a368c6a0e0796152` | passed; 15 ready, minimum 10 |
| W4 machine background exclusions r1 | `e09a79560e3c7e3bba57321f9d25c4c9d246821aafac711e8bcf77bed0ce11bb` | machine fire screen complete; independent review pending |
| Corrected model release freeze r3 | `518f5cb44f6bdfcafcb3761a9639468cf5fb041296a8ccf58e5d6825e391206c` | frozen pending independent review |
| Successor protocol freeze r4 | `4a88f676e52ba621d18c7e37d42bb7da084511463c4956880caa5890368ee7da` | frozen with new W3/W4 inputs and operators |

The historical GFS validator passed every object. An end-to-end profile test
then exposed an unused requirement for pressure-level specific humidity
(`q`), while the archive provides relative humidity (`r`). CFFEPS consumes
the sampled two-metre specific-humidity scalar and pressure-level temperature
and geopotential height; the rejected pressure-level `q` values were not read
by the profile constructor. The extractor now requires the fields it actually
uses. A regression test covers a complete `t`/`gh` profile without `q`.

The real frozen 2017 interface test produced 25 hourly profiles spanning
00:00 through 24:00 UTC, each with 40 strictly ordered pressure/height levels,
finite surface humidity and wind, and the expected 1000-to-100 hPa model
range. Because this changed runner source, it is recorded in model release
r3 and cannot inherit r2 review.

The complete Python ingestion and Airflow suite passed after these changes:
187 tests passed with no failures. Nine NumPy deprecation warnings remain;
none affected values or pass/fail status.

### 6.2 Formal Phase-0 outcome

The final review package is generated only after this execution record is
frozen, so its manifest can hash this document without a self-referential
checksum. It includes 30 source, cohort, methods, model-release, protocol,
input, W5, and W6-matrix artifacts; a reviewer template; the reviewer
handoff; and the three-issue blocking ledger.

The subsequent machine Phase-0 preflight has these results:

```text
all_required_inputs_complete = true
vertical_inputs_complete = true
cohorts_frozen = true
model_release_frozen = true
operators_and_thresholds_frozen = true
sensitivity_matrix_frozen = true
holdout_output_opened_before_freeze = false
reviewer_approval_to_execute = false
holdout_execution_authorized = false
```

This is the intended fail-closed state. The implementation author has not
signed either reviewer role or resolved a scientific issue on a reviewer's
behalf.

### 6.3 Experiments deliberately not executed

Because `holdout_execution_authorized` is false:

- the W2, W3, and W4 central holdout outputs remain unopened;
- none of the 16 W6 formal candidate runs has been launched;
- W7 final results review and a reviewed release do not yet exist;
- the W8 rehearsal has not been run; and
- no elapsed W8 schedule window has been claimed.

The next permissible action is independent pre-execution review, not model
execution. After both role-specific reviews are favourable and the blocking
issues are closed, rerun the signoff verifier and Phase 0. Only a passing
fresh Phase-0 artifact authorizes the central experiments and the complete W6
matrix. W8 remains later still: it follows final W7 approval and requires one
real rehearsal plus four genuinely elapsed consecutive schedule windows.
