# HRDPA precipitation-analysis data contract

**Verification date:** 2026-07-16  
**Verified valid time:** 2026-07-16 12Z  
**Implementation state:** automatic discovery, GRIB2 ETL, catalogue, and display enabled

## Authoritative references

- [HRDPA overview](https://eccc-msc.github.io/open-data/msc-data/nwp_hrdpa/readme_hrdpa_en/)
- [HRDPA on the MSC Datamart](https://eccc-msc.github.io/open-data/msc-data/nwp_hrdpa/readme_hrdpa-datamart_en/)
- [MSC Open Data usage policy](https://eccc-msc.github.io/open-data/usage-policy/readme_en/)

## Analysis-time contract

HRDPA is an analysis, not a forecast. The timestamp in a filename is treated as
the valid time and end of the accumulation interval. `PT0H` identifies an
analysis and must not be exposed as a zero-hour forecast.

| Accumulation | Valid times | Revisions |
|---|---|---|
| 6 hours | 00, 06, 12, and 18 UTC | preliminary and final |
| 24 hours | 06 and 12 UTC | preliminary and final |

The preliminary file generally arrives about one hour after valid time; the
final file follows after the longer observation cut-off, approximately seven
hours after valid time. The adapter derives `interval_start` by subtracting the
filename's accumulation from its valid time and sets `interval_end` to the
valid time.

## Source layout and grid

```text
https://dd.weather.gc.ca/today/model_hrdpa/2.5km/{HH}/
https://dd.weather.gc.ca/{YYYYMMDD}/WXO-DD/model_hrdpa/2.5km/{HH}/
```

```text
{YYYYMMDD}T{HH}Z_MSC_HRDPA[-Prelim]_
  APCP-Accum{6|24}h_Sfc_RLatLon0.0225_PT0H.grib2
```

| Property | Value |
|---|---|
| Grid | `RLatLon0.0225` |
| Dimensions | 2538 by 1288 |
| Nominal resolution | 2.5 km |
| Domain | Pan-Canadian |

The dimensions differ from HRDPS even though both products use a grid labelled
`RLatLon0.0225`. Processing must validate the actual raster and must not reuse
HRDPS dimensions.

## Live metadata inventory

This operator command retrieved one HTML listing and no GRIB payloads:

```bash
uv run weather-ingest --config-root config inspect-source \
  --product hrdpa \
  --reference-time 2026-07-16T12:00:00Z \
  --format json \
  --summary-only
```

The listing contained preliminary/final 6-hour analyses and preliminary/final
24-hour analyses. All four parsed and mapped, with no unknown objects or parser
errors. All four are enabled for operational download. Apache's rounded sizes
totalled 24,431,820 bytes.

The GRIB files also contain a confidence-index field that is not represented by
a second remote object. The reviewed configuration selects source band 1 as the
intended precipitation band, but that selection is not trusted for production
until it has been checked against a real payload.

## Current boundary

The remote-file mappings, catalogue rows, styles, domain, semantic database
constraints, and `eccc_hrdpa_ingest` DAG route are installed. Analysis catalogue
times use `forecast_hour = NULL`, `valid_time = interval_end`, explicit interval
bounds, and `time_kind = accumulation`.

The operational DAG downloads, validates, converts, and displays preliminary
and final 6-hour and 24-hour precipitation for every discovered valid time.
Each visible analysis cycle and its payloads remain available through the
shared historical archive.
