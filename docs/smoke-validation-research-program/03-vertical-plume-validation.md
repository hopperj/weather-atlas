# W3 research plan: acceptance-capable vertical plume validation

> **2026-07-27 expanded-availability update:** The immutable original
> 16-orbit cohort still contains only 6 all-gate-eligible cases. An exhaustive
> 2017-current MERLIN query has now identified 109 observation-qualified
> fire-overpass candidates; 88 also have complete Fire M3 and independent
> MCD64A1 area inputs, spanning 37 distinct MISR orbits. This resolves the
> observation-availability shortage, but the expanded pool is not yet a
> frozen independent-fire cohort and has no completed meteorology or causal
> CFFEPS histories. See
> [the expanded MISR record](progress/2026-07-27-w3-expanded-misr-2017-current.md)
> and
> [the immutable original-cohort record](progress/2026-07-27-w3-blind-observation-and-causal-emissions.md).

**Blocker:** the pilot TROPOMI comparison was diagnostic and failed RMSE; no
acceptance-capable vertical observation was evaluated  
**Dependency:** W1 vertical cohort and W5 frozen model release  
**Estimated active effort:** 3–8 person-weeks  
**Output:** independently QA-screened MISR/lidar fire-overpass matchup

## Research question

Does the transported FLEXPART aerosol vertical distribution reproduce
independently observed wildfire plume height at overpass time, without using
that observation to set CFFEPS injection?

## Primary and secondary observations

### Primary: MISR MINX/MERLIN

NASA's MISR Enhanced Research and Lookup Interface (MERLIN) exposes the public
MISR Plume Height Project database and provides download scripts for
MINX-generated wildfire plume files. NASA also distributes the free MINX tool
for processing additional MISR scenes. See
[NASA ASDC MERLIN/MINX access](https://asdc.larc.nasa.gov/news/merlin-a-new-tool-for-misr-plume-height-project-access-and-analysis).

MISR is primary because its multi-angle stereo retrieval supplies plume
heights and wind information near the source. MINX plume delineation is
labour-intensive and partly analyst-driven, so independent annotation QA is
mandatory.

### Secondary: lidar

Use CALIOP Level 2 aerosol profile/layer products when a track intersects a
modelled smoke plume. NASA ASDC provides 5 km aerosol profile data and a
vertical feature mask; the latter distinguishes aerosol and cloud features.
Examples are the
[CALIOP 5 km aerosol profile product](https://asdc.larc.nasa.gov/project/CALIPSO/CAL_LID_L2_05kmAPro-Standard-V4-10_V4-10)
and
[vertical feature mask](https://asdc.larc.nasa.gov/project/CALIPSO/CAL_LID_L2_VFM-Standard-V4-21_V4-21).

MISR remains the formal acceptance test unless a new protocol prospectively
defines lidar-specific thresholds. TROPOMI aerosol mid-height remains a
secondary column diagnostic and must not be pooled with stereo/lidar heights.

## Sample design

The formal minimum is 10 independent, quality-screened fire-overpasses.
Target at least 20 so exclusions and event clustering do not reduce the
effective sample below 10.

The independent unit is one fire-overpass. Multiple MINX retrieval pixels or
lidar bins within a plume are used to compute that overpass's summary, not
counted as independent pairs. Seek:

- at least 5 distinct fires;
- more than one fuel family and area stratum;
- a range of plume heights and atmospheric stability;
- no more than 30% of primary pairs from one fire; and
- overpasses that occur inside a complete model transport interval.

These distribution targets improve interpretation but do not replace the
frozen minimum sample and performance gates.

## Blinded observation workflow

1. Use event location and date to identify potential MISR/lidar overpasses.
2. An observation analyst delineates and QA-screens the plume without viewing
   CFFEPS or FLEXPART height.
3. A second analyst independently reviews every retained plume boundary,
   source assignment, wind direction, terrain treatment, and exclusion.
4. Disagreements are resolved with a recorded rule, not model agreement.
5. Freeze plume polygons, valid retrieval points, QA flags, overpass time,
   terrain source, and summary statistics.
6. Hash the observation ledger.
7. Only then sample the already frozen model output.

If one person must perform both roles, separate the sessions, hide model
output during observation processing, and retain the complete audit trail.

## Observation operator

Freeze these choices before extraction:

- wind-corrected MISR height as primary; zero-wind height as sensitivity;
- metres above ground level using one common terrain reference;
- plume polygon supplied by MINX or independently frozen delineation;
- source assignment based on event identity and geometry;
- maximum overpass-to-model time offset;
- interpolation to overpass time;
- treatment of pixels below terrain or with invalid wind/height QA; and
- rules for overlapping plumes and multiple candidate sources.

The existing pilot used a 90-minute maximum offset. Retain it unless reviewers
approve a prospective change before holdout extraction.

## Model quantities

For every plume polygon at overpass time calculate:

1. **Mass-weighted mean height**

   ```text
   sum(concentration × layer thickness × layer midpoint)
   / sum(concentration × layer thickness)
   ```

2. **Robust model plume top:** the AGL altitude below which 95% of column
   aerosol mass resides.
3. **Raw CFFEPS plume top** at release time as a source-component diagnostic.
4. **Layer mass profile** and total polygon column mass.

Intersect the full FLEXPART horizontal grid with the observed plume polygon.
Use area-weighted model-cell overlap rather than only the pixel containing the
source. Apply a minimum model column-mass threshold frozen before results, and
report every zero-column rejection.

Compare like quantities:

- MISR mean/median valid plume height to FLEXPART mass-weighted mean;
- a robust upper MISR height statistic, frozen prospectively, to the model
  95%-mass top; and
- lidar smoke-layer boundaries/profile to the model vertical profile.

Do not call a TROPOMI extinction mid-height a direct plume-top measurement.

## Metrics and frozen acceptance gates

Primary MISR fire-overpass results require:

- pair count at least 10;
- mean bias from -1,000 to 1,000 m;
- RMSE no greater than 2,000 m; and
- Pearson correlation at least 0.40.

Report MAE, median bias, Spearman correlation, FAC2 in height where defined,
and event-block bootstrap 95% intervals as secondary statistics. The frozen
point estimates remain the pass/fail rule.

Report by area stratum, fuel family, stability, and time since release when
sample sizes permit. Label all such subgroup analyses exploratory unless
preregistered.

## Implementation plan

Add a source-neutral vertical-observation contract:

```text
python/weather_ingest/vertical_plume_observations.py
python/weather_ingest/misr_minx.py
python/weather_ingest/caliop_profiles.py
scripts/catalogue_vertical_plume_overpasses.py
scripts/build_misr_flexpart_height_pairs.py
scripts/build_caliop_flexpart_profile_pairs.py
scripts/evaluate_vertical_plumes.py
tests/ingestion/test_misr_minx.py
tests/ingestion/test_vertical_plume_observations.py
```

The contract should store:

- observation product/version and file hash;
- event and overpass identity;
- plume geometry;
- terrain reference;
- valid height samples and QA;
- aggregation method;
- model time/space interpolation;
- rejection reason; and
- acceptance role.

Do not modify `tropomi_height_intercomparison.py` to masquerade TROPOMI as the
new primary test. Retain that result separately.

## Sensitivities

Run without replacing the primary result:

- zero-wind versus wind-corrected MISR heights;
- mass-weighted mean versus 95%-mass model top;
- nearest output time versus linear temporal interpolation;
- exact polygon overlap versus a frozen uncertainty dilation;
- central versus uniform/alternative injection; and
- model profile with and without deposition if the overpass occurs late enough
  for removal to matter.

The central injection result is always reported first.

## Required artifacts

```text
evaluation/vertical/
  overpass-catalogue.json
  observation-ledger.json
  observation-files/
  plume-geometries.gpkg
  independent-qa/
  misr-pairs.csv
  caliop-profile-pairs.nc
  rejection-ledger.json
  central-evaluation.json
  sensitivity-evaluations/
  figures/
```

## Definition of done

- At least 10 independent primary fire-overpasses survive QA.
- Observation processing was blind to model height.
- All terrain, time, footprint, aggregation, and rejection rules were frozen.
- The primary point estimates pass all four height gates.
- Clustered uncertainty and sensitivity results are reported.
- Raw CFFEPS top and transported FLEXPART vertical metrics are separated.
- Both reviewers accept the observation operator and interpretation.

If the primary metrics fail, W3 remains failed. Investigate injection on a
training cohort, freeze a revised profile, and use a new holdout.

## 2026-07-27 expanded availability result

The original seeded 16-orbit pool was superseded for availability planning by
an exhaustive 2017-current MERLIN query. It found 388 Canadian-interior
fire-plume families in 78 orbits. Under the unchanged provisional rule, 109
observations qualified; 88 also received complete Fire M3 state/fuel and
independent MCD64A1 burned area, spanning 37 orbits.

This resolves the observation-availability shortage but does not complete W3.
The physical-fire clustering rule, central/reserve cohort, historical
meteorology, causal CFFEPS histories, and independent review are not yet
frozen. See the
[expanded MISR acquisition and screening record](progress/2026-07-27-w3-expanded-misr-2017-current.md).

## Main risks and mitigations

| Risk | Mitigation |
|---|---|
| Too few existing MERLIN plumes | Process additional MISR scenes with MINX; use a multi-year cohort |
| Manual plume boundary subjectivity | Blind dual review and polygon/zero-wind sensitivities |
| MISR overpass misses peak plume | Report time since release and use multiple events; do not retime emissions to fit |
| Lidar track sparsity | Treat CALIOP as complementary, not a replacement for the MISR minimum |
| Mass versus optical-height mismatch | Use stereo/lidar primary; keep TROPOMI separate |

## Execution checklist

- [x] Catalogue public MERLIN observations exhaustively for 2017-current.
- [x] Identify more than 20 source-area-qualified candidate plume-overpasses.
- [ ] Freeze terrain, time, polygon, QA, and aggregation operators.
- [ ] Complete blind MINX/observation processing and second review.
- [ ] Freeze the observation ledger hash.
- [ ] Build FLEXPART polygon/profile statistics.
- [ ] Evaluate central result and clustered uncertainty.
- [ ] Run frozen sensitivities.
- [ ] Obtain independent vertical-method sign-off.
