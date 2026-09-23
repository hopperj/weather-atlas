# MCD64A1 burned-area observation operator

**Operator ID:** `mcd64a1-event-area-v1`  
**Status:** frozen before reading any `Burn Date` pixel values  
**Frozen:** 2026-07-23 19:32:57 UTC  
**Configuration:** [`../config/smoke/mcd64a1_area.yaml`](../config/smoke/mcd64a1_area.yaml)  
**Configuration SHA-256:** `aefc9a786761fd4e4cb3fdaa252788844d2af3b3ae0ea65ba2938632d3bf89b9`

## Purpose

This operator translates the independent NASA MCD64A1 Collection 6.1 monthly
500 m burned-area product into daily area increments for the fire events frozen
by the November 2025 CWFIS/VIIRS event-reconciliation audit. It is an input
observation operator, not a calibration against CFFEPS, FLEXPART, or GFAS. No
candidate emissions or transport result was inspected when its rules were
chosen.

MCD64A1 detects rapid changes in MODIS surface reflectance, aided by active-fire
observations, and reports an ordinal burn date for each classified burned grid
cell. The product is distributed on the global MODIS sinusoidal equal-area
grid. The five required HDF4 layers are `Burn Date`, `Burn Date Uncertainty`,
`QA`, `First Day`, and `Last Day`. Product definitions and QA bit semantics
follow the [MCD64A1 v6.1 user guide](https://lpdaac.usgs.gov/documents/1006/MCD64_User_Guide_V61.pdf).

## Grid and area calculation

The operator verifies each granule's HDF-EOS grid metadata against the frozen
configuration before reading science data. A tile is 2400 by 2400 pixels. Pixel
centres are located on the MODIS sinusoidal grid using:

```text
x = global_upper_left_x + (global_column + 0.5) × pixel_size
y = global_upper_left_y - (global_row + 0.5) × pixel_size
```

The projection uses a sphere radius of 6,371,007.181 m and a nominal pixel
spacing of 463.312716527778 m. Because the projection is equal-area, each
accepted pixel contributes:

```text
pixel area = pixel_size² = 214,658.6733 m² = 21.46586733 ha
```

Latitude and longitude used for geodesic matching are obtained by inverse
sinusoidal transformation. Area is never inferred from active-fire detection
count, FRP, GFAS, or the number of event members.

## Central QA screen

A central-analysis burned pixel must satisfy all of the following:

1. `Burn Date` is a valid ordinal day in the frozen experiment interval;
2. QA bit 0 identifies land;
3. QA bit 1 identifies sufficient valid input data; and
4. the burn date lies between the pixel's `First Day` and `Last Day`, inclusive.

QA bit 2, a shortened mapping period, does not invalidate a burn whose date is
inside the explicitly reliable interval. QA bit 3, contextual relabelling, is
also retained by the central product because it is part of the documented
MCD64A1 classification algorithm. Both flags are counted and exposed. A
high-confidence sensitivity subset excludes pixels carrying either flag.

## Event association

The frozen event IDs and their member-detection coordinates and UTC times are
not modified. Association proceeds deterministically:

1. A burned pixel is temporally compatible with an event when the pixel
   interval `Burn Date ± Burn Date Uncertainty` intersects the event's
   first-to-last detection interval padded by one calendar day.
2. A compatible pixel becomes a seed when its centre is no more than 1500 m
   geodesically from any member detection.
3. The event claim grows from its seeds through eight-connected, QA-accepted,
   temporally compatible burned pixels. This recovers the connected scar rather
   than treating the active-fire point itself as an area measurement.
4. Cross-tile adjacency is handled in global sinusoidal row/column coordinates.
5. Duplicate cross-month classifications must be identical and are then
   deduplicated; a conflict is a hard error.
6. A pixel claimed by more than one frozen event is excluded from every event
   and reported as ambiguous. It is never counted twice or assigned using
   candidate-model output.

The 1500 m seed radius covers several MCD64A1 pixels and the differing spatial
support and geolocation of the 375 m VIIRS detection and 500 m burned-area
classification. Connected growth permits a larger scar only when independent
MCD64A1 pixels support it.

## Daily curve and eligibility

Each unambiguous accepted pixel contributes its equal-area cell area on the
reported burn date. Event daily increments are summed into a cumulative curve.
The uncertainty layer also produces earliest and latest cumulative timing
curves by shifting each pixel within its reported date uncertainty. These are
timing bounds, not a claim that MCD64A1 omission error is bounded.

An event passes the burned-area part of eligibility only when it has at least
one assigned central pixel and at least one assigned high-confidence pixel.
Area strata use the final central area:

- weak: less than 100 ha;
- moderate: 100–1,000 ha; and
- major: greater than 1,000 ha.

Passing this operator does not by itself make an event scientifically eligible.
Fuel parameters, fire-weather state, meteorological profiles, independent
comparison data, and ambiguity checks from the parent validation protocol still
apply.

## Limitations and amendment rule

MCD64A1 can omit small, cloudy, or spectrally ambiguous burns; a missing match is
therefore not proof that a hotspot was false. Conversely, nearby burns can form
a connected scar. The frozen temporal rules and ambiguous-pixel exclusion
reduce, but do not eliminate, attribution uncertainty.

All unmatched detections, excluded pixels, shortened-period pixels, relabelled
pixels, ambiguous claims, tile failures, and cross-month duplicates remain in
the machine-readable report. Any change to QA, radius, connectivity, temporal
matching, or ambiguity handling requires a new operator ID and must be tested on
a separate analysis version.
