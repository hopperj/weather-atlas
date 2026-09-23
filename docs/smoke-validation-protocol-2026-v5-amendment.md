# March–May 2026 validation protocol v5 amendment

**Protocol ID:** `cffeps-flexpart-external-validation-2026-07-24-v5`  
**Status:** surface-observation operator frozen before surface pair generation  
**Frozen:** 2026-07-24 13:20:45 UTC (10:20:45 ADT)  
**Parent protocol:** [`smoke-validation-protocol-2026-v4-amendment.md`](smoke-validation-protocol-2026-v4-amendment.md)  
**Evaluation gates:** [`../config/smoke/validation_2026_v5.yaml`](../config/smoke/validation_2026_v5.yaml)

## Timing and scope

This amendment was written after the central candidate, GFAS diagnostic, and
TROPOMI diagnostic existed, but before any AirNow or AQS matchup was generated
or any surface statistic was calculated. It cannot alter the candidate, event
selection, GFAS result, TROPOMI result, or any numerical evaluation threshold.
It closes implementation details left ambiguous in the parent protocol so that
the surface observation adapters have no discretionary choices after seeing
their results.

## Frozen AirNow operator

AirNow supplies the Canadian observation network for this test. A record is
eligible when `CountryCode=CA`, `PM25_Measured=1`, PM2.5 is finite, and the
unit is `UG/M3`. `AQSID` is the station key. The hourly filename and matching
`ValidDate`/`ValidTime` are interpreted as UTC; disagreement is a hard input
error. Duplicate station-hours with conflicting values are a hard error.

## Frozen AQS operator

AQS supplies the independent United States regulatory-source test. Parameter
codes 88101 and 88502 are retained when the unit is
`Micrograms/cubic meter (LC)`, the value is finite, and `Qualifier` is empty.
A monitor is the state, county, site, parameter, and POC tuple. This preserves
parallel instruments instead of averaging them after inspecting their values.
`Date GMT` and `Time GMT` define UTC.

## Background and pairing

For each source-day station-hour, the central background is the median of that
same station or monitor and same UTC hour over the 14 preceding and 14
following calendar days. All eight candidate source dates are excluded from
every background sample. At least seven finite background observations are
required. The already-declared 20th percentile is generated as a sensitivity
from the identical background sample using NumPy's linear percentile
interpolation.

Observed smoke enhancement is `max(raw PM2.5 - background, 0)` in µg m-3.
The model value is the lowest FLEXPART layer (0–50 m AGL) in the containing
regular output-grid cell at the matching interval-end timestamp, converted
from ng m-3 to µg m-3. A pair is retained only when model PM2.5 is at least
0.01 µg m-3. Missing observations, missing backgrounds, and stations outside
the FLEXPART grid remain explicit rejection counts.

The original ±14-day AirNow acquisition ended 2026-05-31, which was
insufficient for source dates through 2026-05-25. Before pair generation,
2026-06-01 through 2026-06-09 was acquired using the same downloader and raw
product. Its separate immutable download manifest is retained. The AQS archive
already extends beyond the required background interval.

All scientific roles are unchanged: AirNow and current-year AQS are
provisional, not acceptance-capable, until final archives are frozen and
reviewed.
