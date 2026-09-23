# Publication update: expanded MISR evidence for W3

**Date:** 2026-07-27  
**Status:** candidate-discovery and source-area screening complete; formal
FLEXPART comparison not started  
**Observation interval requested:** 2017-01-01 through 2026-07-27  
**Processed archive coverage returned:** summer 2017 and summer 2018  
**FLEXPART output used in selection:** no

This document updates the publication narrative after the exhaustive MISR
inventory. It does not replace the immutable March–May 2026 pilot or the
original 16-case W3 analysis.

The complete integrated manuscript draft is
[Building a Performance-Blind, Provenance-Preserving Validation Framework for
CFFEPS–FLEXPART Wildfire Smoke Simulation over Canada](../research-paper-cffeps-flexpart-validation.md).

## Working title

**A Performance-Blind, Multi-Year MISR Framework for Evaluating Wildfire
Plume Injection in CFFEPS–FLEXPART over Canada**

An alternative title, if the final transport experiment passes all gates, is:

**Evaluating CFFEPS–FLEXPART Wildfire Plume Injection over Canada with
Multi-Angle Satellite Heights and Causal Fire Histories**

The first title is appropriate now because it makes no claim that FLEXPART
performance has already been demonstrated.

## Revised paper summary

The study develops and tests a reproducible Canadian wildfire-smoke modelling
chain linking Fire M3 detections and fire-weather state, independently mapped
MCD64A1 burned area, CFFEPS combustion and plume rise, and FLEXPART transport.
Its main methodological contribution is a prospective separation between
observation selection, causal source construction, and model evaluation.
MISR/MINX plume heights are selected and quality-controlled without consulting
FLEXPART heights, while fire and meteorological information available after
the satellite overpass is prohibited from influencing the simulated plume at
overpass time.

The original seeded W3 sample contained 16 MISR orbits and produced only 6
all-gate-eligible observations. An exhaustive query of the public MERLIN
archive changes the interpretation of that result. The archive search found
388 Canadian-interior plume families in 78 orbits. Under the unchanged
provisional observation rule, 109 plume-overpass candidates qualified, and 88
also had complete Fire M3 state/fuel and qualifying independent MCD64A1 burned
area. These 88 records span 37 orbits. The earlier shortfall therefore arose
from a narrow seeded sample and subsequent QA attrition, not from a general
lack of usable public MISR observations.

The expanded result establishes an acceptance-capable candidate population,
not a completed validation. Several plume families can occur in one satellite
orbit, and nearby records can represent a common fire complex. A
performance-blind physical-fire clustering rule and independent scientific
review must therefore precede central-cohort selection. Historical
meteorology, strictly causal CFFEPS emission histories, FLEXPART runs, and
model–observation statistics remain future work.

## Provisional abstract

Wildfire-smoke forecasts depend on both the magnitude and vertical
distribution of emissions, yet apparent agreement in surface concentration
can conceal compensating errors in burned area, fuel consumption, plume rise,
transport, and deposition. We developed a component-wise, provenance-preserving
framework for evaluating a Canadian wildfire-smoke system that combines
NRCan Fire M3 detections and CFFDRS state, MODIS MCD64A1 burned area, CFFEPS
4.1 emissions and plume rise, and FLEXPART 11.1 atmospheric transport. The
framework separates satellite observation selection from source construction
and prohibits model performance or post-overpass information from influencing
the validation cohort.

We queried the NASA MISR Plume Height Project through MERLIN for
2017-01-01–2026-07-27 and downloaded every returned MINX plume file intersecting
predefined Canadian-interior screening regions. The public processed archive
returned records for 2017 and 2018 only. The acquisition yielded 772
checksummed files representing 388 band-independent plume families in 78 MISR
orbits. Height-blind metadata and geometry QA selected 386 families. Applying
a provisionally frozen requirement of at least 10 wind-corrected retrievals
at or above 250 m AGL retained 109 plume-overpass observations. All 109
matched complete Fire M3 fuel and fire-weather state; 88 also passed an
independent MCD64A1 burned-area operator and represented 37 distinct orbits.

This expansion removes the observation-availability bottleneck identified in
an earlier 16-orbit sample, in which only 6 cases survived all provisional
requirements. It does not yet establish plume-height skill: physical-fire
clustering, independent review of the observation operator, central and
reserve cohort freezing, historical meteorology, causal pre-overpass emission
histories, and formal FLEXPART comparisons remain incomplete. The resulting
design provides a performance-blind foundation for testing wildfire plume
injection without using satellite plume heights to tune the model being
evaluated.

## Introduction opening

Wildfire-smoke exposure is controlled not only by the amount of material
emitted but also by the altitude at which that material enters the
atmosphere. Injection within the boundary layer can strongly affect nearby
surface concentrations, whereas lofting above the boundary layer can promote
long-range transport and alter the timing and location of downwind exposure.
For a Lagrangian particle-dispersion model such as FLEXPART, the vertical
release profile is therefore a first-order scientific input rather than a
minor implementation detail.

Evaluating that input is difficult because the source and transport system is
only partially observed. Satellite burned-area products constrain where and
when burning occurred, fire-weather analyses constrain fuel dryness, and
emissions models translate those quantities into species-resolved mass and
plume rise. Each transformation introduces uncertainty. End-to-end agreement
with surface PM2.5 alone cannot identify which component is correct, because
source, injection, transport, and deposition errors can offset one another.
A defensible validation must consequently examine the source magnitude,
vertical plume structure, surface concentration, and numerical behaviour as
separate but connected questions.

MISR provides a particularly useful independent constraint on vertical plume
structure because its multi-angle imagery supports stereo retrievals of plume
height and motion through MINX. However, plume delineation and quality
screening involve analyst decisions, and satellite sampling is clustered by
fire and orbit. There is also a strong risk of circularity if observed plume
heights are used to select fires, tune injection, or revise exclusion rules
after model results are known. We address these risks with a
performance-blind workflow: MINX files are selected before height extraction,
MISR heights never seed CFFEPS or FLEXPART, and source histories are truncated
at the satellite overpass.

An initial prospectively seeded inventory retained only 16 MISR orbit
overpasses and yielded 6 cases after observation and input screening. We
therefore expanded the availability search without consulting FLEXPART
output. The expanded inventory demonstrates that the six-case outcome was not
a general limit of the public MISR record: 109 observations meet the same
provisional measurement rule, and 88 have the fire-state and burned-area
support needed to enter a future causal transport experiment.

## Methods text for the expanded MISR inventory

### Archive discovery and geographic screen

The NASA MERLIN provider was queried separately for every calendar year from
2017 through 2026, with the last interval ending on 2026-07-27. Annual
catalogue responses, including empty responses, were retained with
checksums. The public provider returned 5,030 records for 2017 and 4,946 for
2018, and no records for 2019–2026.

Candidate availability was screened with four fixed Canadian-interior
rectangles covering the British Columbia interior, Prairies, central/eastern
interior, and territorial interior. The screen is intentionally conservative
and is not represented as a national boundary. Every provider orbit
intersecting a screening rectangle was retained; no seeded truncation or
model-performance filter was applied.

All 772 referenced MINX text files were downloaded and verified against their
recorded size and SHA-256. The files total 65,274,882 bytes. Red- and
blue-band files with the same orbit, block, and plume identity were grouped
into 388 band-independent plume families.

### Height-blind product selection

Selection was completed before height extraction. Permitted inputs were
product identity, acquisition time, orbit, categorical provider quality,
aerosol and geometry type, polygon validity, retrieval point identities and
coordinates, terrain validity, and source-to-polygon distance. Height
columns, provider height summaries, CFFEPS height, FLEXPART output, and
performance statistics were unavailable to the selector.

Candidates were ranked by `Good` before `Fair` quality, blue before red for
land smoke, greater raw retrieval support, and finally region name. No
alternate-band fallback was permitted after height extraction. This selected
386 of 388 plume families: 374 blue and 12 red, with 316 `Good` and 70 `Fair`
provider-quality selections.

### Provisional measurement rule

After file identities and checksums were frozen, the primary observation was
calculated as wind-corrected MINX ASL height minus the same-row terrain ASL.
Valid retrievals required AGL height of at least 250 m, and a plume family
required at least 10 valid retrievals. No alternate band was consulted if the
selected file failed. This retained 109 observations: 73 in 2017 and 36 in
2018, spanning 39 MISR orbits.

The 250 m and 10-retrieval limits are provisional. They were not modified
after the resulting sample became known, but they still require independent
plume-science review. Observed height magnitudes remain sealed until the
observation and model operators are frozen.

### Fire-state and burned-area support

Observation-qualified sources were matched to annual Fire M3 archives within
5 km and 3 hours. A match required finite FFMC, DMC, and DC and a fuel code
resolvable through the frozen FBP crosswalk. Ties were resolved by distance,
time difference, region identity, and provider-row hash. All 109 observations
received complete state and fuel assignments.

MCD64A1 Collection 6.1 burned-area occurrences were processed independently
of plume height. The operator retained distinct burn occurrences at the same
cell on different dates, removed identical cross-month duplicates, excluded
ambiguous occurrences claimed by multiple events, and required at least one
high-confidence pixel. Eighty-eight candidates passed the area operator.

## Results text

The expanded public-archive query returned 9,976 provider records. After
Canadian-interior screening, 78 MISR orbits and 772 MINX files were retained.
Those files represented 388 band-independent plume families. Height-blind
selection retained 386, of which 109 met the provisional post-selection
measurement rule.

All 109 observation-qualified records received a complete Fire M3
fuel/CFFDRS assignment. Independent MCD64A1 processing retained 55 of 73
observation-qualified records in 2017 and 33 of 36 in 2018, for 88
source-area-qualified candidates. The 21 burned-area exclusions comprised 17
records without enough unambiguous area or a high-confidence pixel and 4 that
also lacked a matched burn seed.

### Candidate-pool composition

| Attribute | Result |
|---|---:|
| Source-area-qualified candidates | 88 |
| Distinct MISR orbits | 37 |
| Distinct overpass dates | 34 |
| 2017 candidates | 55 |
| 2018 candidates | 33 |
| Blue-band selections | 85 |
| Red-band selections | 3 |
| Weak burned-area stratum | 5 |
| Moderate burned-area stratum | 28 |
| Major burned-area stratum | 55 |
| Fuel mappings represented | 12 |

The retained candidates contain 10–842 valid retrievals, with a median of
31.5 and an interquartile range of 16.75–73.75. Central independently mapped
area ranges from 64.40 to 58,473.02 ha, with a median of 1,524.08 ha and an
interquartile range of 520.55–5,693.82 ha.

The orbit distribution is strongly clustered. Twenty orbits contain one
retained plume family, while 17 contain two or more; one orbit contains 13.
Consequently, 88 records cannot be interpreted as 88 statistically
independent validation samples. Even a conservative one-record-per-orbit
upper-level design leaves 37 potential orbit units, but physical-fire
clustering and input completion must be applied before the formal sample size
is declared.

## Revised interpretation

The additional MISR evidence changes one conclusion and leaves the scientific
acceptance decision unchanged:

1. **Changed:** usable MISR availability is no longer a blocking shortage.
   The earlier six-case result was specific to a narrow seeded cohort.
2. **Unchanged:** no acceptance-capable FLEXPART plume-height comparison has
   yet been executed, so no plume-height bias, RMSE, correlation, or pass/fail
   claim can be made.

The work currently supports a methods and cohort-construction result. It does
not support claims that CFFEPS injection heights are accurate, FLEXPART
reproduces MISR heights, or the complete smoke system is scientifically
accepted.

## Limitations and independence disclosure

- MERLIN is a processed research archive rather than a continuously produced
  annual MISR plume-height product. Its lack of records after 2018 is an
  archive-coverage limitation, not evidence that MISR lacked later
  observations.
- The four geographic rectangles are conservative Canadian-interior
  availability screens, not an exact national or ecozone boundary.
- The 88 records have not yet been clustered into independent physical fires.
  Orbit-level and fire-complex dependence must be represented in cohort
  selection, uncertainty estimation, and interpretation.
- MCD64A1 is used retrospectively to constrain burning that physically
  occurred by overpass time. Its finalized burn map would not have been
  available to a real-time forecast at that time. Formal claims must label
  this as retrospective physical reconstruction, not operational causality.
- One raw MINX header was viewed during earlier implementation work and
  contained provider height summaries. The expanded selector itself does not
  read those summaries or height columns, and no FLEXPART height was opened,
  but an external reviewer must determine whether this deviation requires
  independent reprocessing or additional blinding controls.
- The same implementation agent constructed parts of the acquisition and QA
  workflow. Machine-enforced separation of fields reduces circularity but
  does not constitute independent scientific review.
- The provisional 250 m AGL and 10-retrieval rule is conservative but not a
  universal published MINX validity threshold. It must be accepted or replaced
  prospectively without reference to FLEXPART agreement.

## Required update to the formal experiment

Before FLEXPART output is generated or opened:

1. an independent plume scientist must accept or revise the observation
   operator without reference to the retained sample count or model output;
2. a physical-fire clustering rule must group common fires and fire complexes
   using only source location, time, scar identity, and ancillary fire
   metadata;
3. central and reserve cases must be selected performance-blind, targeting at
   least 20 central candidates so upstream exclusions do not reduce the
   experiment below 10 independent fire-overpasses;
4. historical GFS must be downloaded and validated for only the frozen
   central and reserve cases;
5. Fire M3 state, MCD64A1 area, and meteorology must be translated into
   strictly causal pre-overpass CFFEPS histories;
6. the protocol, observation ledger, source histories, model executable, and
   analysis code must be frozen under an immutable source identity; and
7. only then may the model–observation comparison be run.

The primary W3 gates remain at least 10 independent fire-overpasses, mean bias
within ±1,000 m, RMSE no greater than 2,000 m, and Pearson correlation at
least 0.40.

## Provenance

The complete acquisition and scientific record is
[W3 expanded MISR/MINX inventory](progress/2026-07-27-w3-expanded-misr-2017-current.md).
The height-free list of 88 candidates is stored at:

```text
/Volumes/BigMrStorage/weatherapp_data/weather/derived/smoke/validation/
cohorts/w3-misr-merlin-2017-current-expanded-v1/
source-area-qualified-candidates-r1.csv
```

Its SHA-256 is:

```text
c5a03a41e5f51753359e08ecf570a706d6a59a81b6bbf1c27c1a4026ded11ffc
```

The complete candidate-readiness artifact has SHA-256:

```text
e644123a5c0a40cfd487b1581fd26103194399e68f3a28e0abf8ee11a96cbdb1
```

NASA's
[MERLIN release description](https://asdc.larc.nasa.gov/news/merlin-a-new-tool-for-misr-plume-height-project-access-and-analysis)
and
[MERLIN user guide](https://asdc.larc.nasa.gov/documents/misr/guide/MERLIN_User_Guide.pdf)
describe the processed archive's limited temporal coverage. NASA separately
catalogues a
[Canadian and Alaskan wildfire-smoke collection](https://asdc.larc.nasa.gov/project/MISR_Wildfire_Research/MISR_Canadian_and_Alaskan_Wildfire_Smoke_1)
for 2016–2019, which remains a provider-access follow-up.
