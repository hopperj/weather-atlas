# November 2025 central candidate run

**Candidate ID:** `november-2025-mcd64a1-central-v1`  
**Status:** frozen before generating candidate emissions  
**Frozen:** 2026-07-23 19:38:19 UTC  
**Configuration:** [`../config/smoke/validation_candidate.yaml`](../config/smoke/validation_candidate.yaml)  
**Configuration SHA-256:** `dcf91ba627149c60617f3987d67cbf3ba4a6045f37ab3bfe1af24f1c2d959d52`

## Selection

The candidate contains every frozen November event that passed
`mcd64a1-event-area-v1`. The selection produced four events and ten event-day
area increments: two weak events and two moderate events. No major event is
available, so this run cannot satisfy the parent protocol's complete area-strata
design and cannot establish population-level scientific acceptance.

The run remains useful for component verification, inventory comparison, and
exercising the complete CFFEPS/FLEXPART chain. No event may be removed because
of its subsequent performance.

## Source construction

For each eligible event:

1. select the unique modal CWFIS/FBP fuel code among its frozen VIIRS
   detections; a tied mode is ineligible;
2. treat each MCD64A1 central daily increment as an independent source day;
3. distribute the day-only area linearly from 00:00 through 24:00 UTC rather
   than deriving timing from FRP or GFAS;
4. sample FFMC, DMC, and DC from the checksum-verified CWFIS grids dated to that
   source day at the frozen event centroid;
5. extract the atmospheric profile from that day's archived NOAA GFS 00 UTC
   cycle using the existing nearest-grid, three-hour linear-time, and
   log-pressure vertical operator;
6. run CFFEPS 4.1 with central PM2.5, CO, and BC emission factors and 12
   mass-conserving vertical release layers; and
7. rescale native hourly growth to the independent cumulative MCD64A1 area
   curve while retaining CFFEPS fuel consumption, phase partition, and plume
   rise.

The nominal detection time passed to the daily CFFEPS driver is 12:00 UTC on
the MCD64A1 source day. This is a declared temporal convention, not an inferred
satellite overpass or ignition time.

## Transport

Each distinct source day is transported for 24 hours. Events sharing a day are
combined into the same transport members. PM2.5, CO, and BC remain isolated so
species-specific settling and deposition are retained. Each member uses
150,000 particles, at least 50 particles per release, eight OpenMP threads, and
a recorded deterministic species/day seed.

The output and GFAS comparison domain was fixed from the eligible-event
geography before inspecting emissions:

```text
west=-132, south=47, east=-118, north=58; spacing=1 degree
```

GFAS v1.2 is used only as a diagnostic inventory intercomparison. Its emissions,
FRP, and plume heights do not enter CFFEPS or FLEXPART. The active-union
comparison will therefore expose GFAS-active cells that the four-event
area-qualified candidate does not represent.

## Interpretation

Software completion, mass conservation, and a GFAS diagnostic score are
necessary checks but are not sufficient scientific acceptance. The run lacks a
major event and does not yet have MISR plume-height or NAPS smoke-enhancement
pairs. Conclusions must be reported as November component results, not as
validation of general Canadian wildfire performance.
