# W1 research plan: representative wildfire event population

**Blocker:** the pilot had four weak, one retained moderate, and zero major
fires  
**Priority:** critical path  
**Estimated active effort:** 2–5 person-weeks, excluding provider delays  
**Output:** immutable source/GFAS, vertical, and surface cohort ledgers

## Research question

Can the unchanged CFFEPS–FLEXPART system be evaluated on an independently
selected population that represents weak, moderate, and major Canadian fires,
multiple fuel families, and multiple ecozones?

The primary hypothesis is not a model-performance hypothesis. It is a design
claim: a complete, non-performance-selected cohort can be assembled with at
least three fires per area stratum and all required inputs.

## Design target

The minimum retained source/GFAS cohort is:

- 3 weak fires, final independent area `<100 ha`;
- 3 moderate fires, `100–1,000 ha`;
- 3 major fires, `>1,000 ha`;
- at least 2 Canadian ecozones;
- at least 2 FBP fuel families; and
- complete burned area, fuel, FFMC/DMC/DC, meteorology, and at least one
  applicable independent observation for every retained event.

Start with at least 12–15 input-qualified candidate fires because missing
state, ambiguous overlap, or poor satellite mapping can cause exclusions.
Never replace an event because its model result is poor.

## Cohort strategy

Create three ledgers from one input-only feasibility inventory:

1. **Source/GFAS ledger:** stratified area design and complete GFAS coverage.
2. **Vertical ledger:** eligible fires with MISR/MINX or lidar overpasses.
3. **Surface ledger:** eligible fires with final NAPS stations in the fixed
   model domain and sufficient background observations.

The source/GFAS ledger must independently meet the full nine-fire design. The
vertical and surface ledgers may contain additional events and span multiple
years. Selection may use observation availability, geography, area, fuel, and
input completeness, but never observed-model agreement.

## Data inventory

### Event identity and fuel

Use versioned NRCan CWFIS Fire M3 hotspot records and the existing
`fire-events-v1` reconciliation unless a new algorithm is prospectively
reviewed. Freeze the Canadian boundary source and event-matching configuration.
Retain every detection, duplicate decision, merge/split ambiguity, modal fuel
count, and exclusion reason.

The current CWFIS catalogue and service inventory are at the
[NRCan CWFIS data catalogue](https://cwfis.cfs.nrcan.gc.ca/datamart).
The catalogue is evolving; store the exact endpoint, layer name, response
metadata, retrieval timestamp, licence, and checksum rather than relying on a
generic catalogue URL.

### Independent burned area

Primary area remains NASA MCD64A1 Collection 6.1 burn-date pixels using the
audited `mcd64a1-event-area-v2` occurrence operator. Follow the
[MCD64A1 Collection 6.1 user guide](https://www.earthdata.nasa.gov/s3fs-public/2025-04/MCD64_User_Guide_V61.pdf)
for QA and burn-date interpretation.

Acquire VNP64A1 Version 2 as a prospective area sensitivity and continuity
source. NASA states that VNP64A1 covers March 2012 to the leading edge and is
available through Earthdata Search; use the
[official VNP64A1 release and DOI](https://forum.earthdata.nasa.gov/viewtopic.php?t=6121).

Where available, retain a versioned agency perimeter or National Burned Area
Composite as a secondary magnitude check. Do not substitute hotspot counts,
FRP, GFAS emissions, or the Fire M3 estimated-area field for the primary
independent area.

### Fire-weather state

Require authoritative FFMC, DMC, and DC for every positive-area source day.
First query versioned CWFIS grids. If a historical grid cannot be obtained:

1. request the archived product from NRCan;
2. if necessary, design a separate station-based CFFDRS reconstruction with
   station identity, noon weather, startup state, precipitation, snow, and
   interpolation methods;
3. obtain emissions-scientist review of that reconstruction; and
4. freeze it before model output.

No nearest-valid-cell substitution or temporal interpolation is allowed unless
explicitly preregistered as a sensitivity.

### Meteorology

Use a consistent GFS/GDAS product and grid across all central cohort members.
NOAA NCEI provides historical GDAS/GFS-family GRIB access through its
[GDAS archive](https://www.ncei.noaa.gov/products/weather-climate-models/global-data-assimilation)
and historical GFS products through NCEI/HAS/THREDDS. Record the model-product
identity, grid, cycle, forecast hour, and any system-upgrade boundary.

If a multi-year cohort crosses a major meteorological model change, either:

- use a consistent reanalysis/archived analysis accepted by FLEXPART for all
  events; or
- stratify the result by meteorological era and declare the heterogeneity.

Do not mix products silently.

## Input-only feasibility scan

Implement a scanner that never opens candidate output or evaluation values.
For each proposed event it must report:

- event ID, time span, centre, detection count, modal fuel and ambiguity;
- MCD64A1/VNP64A1 accepted occurrence count and daily/cumulative area;
- stratum and ecozone;
- FFMC/DMC/DC completeness by positive-area date;
- meteorological cycle completeness through the transport horizon;
- GFAS availability;
- MISR/lidar overpass count and QA availability;
- final NAPS station count in the proposed fixed domain and background-window
  coverage; and
- exact exclusion reason.

Suggested implementation entry points:

- `scripts/prepare_smoke_validation_events_2026.py`
- `scripts/build_mcd64a1_event_areas.py`
- `scripts/audit_smoke_validation_eligibility.py`
- `python/weather_ingest/mcd64a1.py`

Generalize date-specific script names only after tests preserve the 2026
operator.

## Selection procedure

1. Define candidate years and download only catalogues/metadata first.
2. Run the input-only scanner over every Canadian event in those periods.
3. Exclude events with machine-readable reasons.
4. Assign area stratum, ecozone, and fuel family without candidate output.
5. Select the full eligible set when practical. If sampling is necessary,
   use a deterministic seeded stratified draw and publish the seed.
6. Freeze all three ledgers and their hashes.
7. Have both independent reviewers verify that no performance variable entered
   selection.
8. Only then acquire remaining large files and run the model.

The preferred first feasibility period is the 2023 Canadian fire season,
because it is likely to contain major fires and final hourly NAPS observations.
That is a hypothesis to audit, not a preselected final cohort.

## Quality controls

- MCD64A1 and VNP64A1 area must be computed from pixel geodesy or declared
  equal-area cell size, never from detection count.
- Overlapping burn occurrences claimed by multiple events remain excluded
  from every claimant.
- Central daily area must sum exactly to each event's retained cumulative area.
- Events with incomplete required input are excluded before any model result.
- At least 20% of event geometry and area assignments receive independent
  visual review, oversampling all major fires and ambiguous overlaps.
- The final ledger is signed and checksummed before model execution.

## Required artifacts

```text
cohorts/
  feasibility-manifest.json
  all-candidate-events.parquet
  all-candidate-events.csv
  source-gfas-ledger.json
  vertical-ledger.json
  surface-ledger.json
  exclusions.json
  manual-review/
  protocol-freeze.json
```

Every ledger entry must link its source files and per-file hashes.

## Definition of done

W1 is complete only when:

- the retained source/GFAS ledger contains at least 3 weak, 3 moderate, and
  3 major events;
- at least 2 ecozones and 2 fuel families are represented;
- every retained source day has complete area, fuel, fire state, and
  meteorology;
- vertical and surface ledgers have enough prospective observations to pursue
  W3 and W4;
- all exclusions are machine-readable;
- independent reviewers sign the no-performance-selection audit; and
- cohort hashes appear in a frozen successor protocol before model output.

## Main risks and mitigations

| Risk | Mitigation |
|---|---|
| Historical CWFIS grids are unavailable | Request authoritative archive early; preregister reviewed station reconstruction only if necessary |
| MCD64A1 misses or merges complex major burns | Add VNP64A1 and agency perimeters as declared sensitivities; retain the primary operator |
| Vertical observations are sparse | Use a separate multi-year vertical cohort rather than weakening the source design |
| Surface stations are not downwind | Expand the pre-output multi-year cohort based on station availability, not observed concentrations |
| Input exclusions drop a stratum below 3 | Begin with 12–15 qualified candidates and freeze a deterministic reserve list before output |

## Execution checklist

- [ ] Choose candidate periods using catalogue metadata only.
- [ ] Verify CWFIS, Earthdata, NOAA, GFAS, MISR/lidar, and NAPS access.
- [ ] Run and test the generalized feasibility scanner.
- [ ] Produce all-candidate and exclusion ledgers.
- [ ] Confirm 3/3/3 strata, ecozones, and fuels.
- [ ] Freeze source/GFAS, vertical, and surface cohort hashes.
- [ ] Obtain no-performance-selection reviewer sign-off.
- [ ] Issue the successor protocol before any holdout model output.
