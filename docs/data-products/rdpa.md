# RDPA precipitation-analysis data contract

**Verification date:** 2026-07-16  
**Verified valid time:** 2026-07-16 12Z  
**Implementation state:** automatic discovery, GRIB2 ETL, catalogue, and display enabled

The operational DAG downloads all configured preliminary/final 6-hour and
24-hour GRIB2 precipitation fields for the current valid time.

## Authoritative references

- [RDPA overview](https://eccc-msc.github.io/open-data/msc-data/nwp_rdpa/readme_rdpa_en/)
- [RDPA on the MSC Datamart](https://eccc-msc.github.io/open-data/msc-data/nwp_rdpa/readme_rdpa-datamart_en/)
- [MSC Open Data usage policy](https://eccc-msc.github.io/open-data/usage-policy/readme_en/)

## Analysis-time contract

RDPA estimates precipitation over past 6- or 24-hour periods. The filename
timestamp is the analysis valid time and accumulation end, not a forecast
initialization. `PT0H` is an analysis marker.

| Accumulation | Valid times | Revisions |
|---|---|---|
| 6 hours | 00, 06, 12, and 18 UTC | preliminary and final |
| 24 hours | 06 and 12 UTC | preliminary and final |

Preliminary products arrive roughly one hour after valid time and final products
after the longer observation cut-off, roughly seven hours after valid time.

## Source layout and grid

```text
https://dd.weather.gc.ca/today/model_rdpa/10km/{HH}/
https://dd.weather.gc.ca/{YYYYMMDD}/WXO-DD/model_rdpa/10km/{HH}/
```

```text
{YYYYMMDD}T{HH}Z_MSC_RDPA[-Prelim]_
  APCP-Accum{6|24}h_Sfc_RLatLon0.09_PT0H.grib2
```

| Property | Value |
|---|---|
| Grid | `RLatLon0.09` |
| Dimensions | 1140 by 1045 |
| Nominal resolution | 10 km |
| Coverage | North America, including Canada, the United States, and Mexico |

RDPA dimensions differ from RDPS despite the shared `RLatLon0.09` grid label.
Each product retains an independent domain and raster validation contract.

## Live metadata inventory

```bash
uv run weather-ingest --config-root config inspect-source \
  --product rdpa \
  --reference-time 2026-07-16T12:00:00Z \
  --format json \
  --summary-only
```

The command retrieved one dated HTML listing and no GRIB payloads. Four provider
objects were present: preliminary/final 6-hour analyses and preliminary/final
24-hour analyses. All mapped without unknown objects or parser errors, and all
are enabled for operational download. Rounded listing sizes totalled 9,961,470
bytes.

As with HRDPA, a confidence index is embedded in each GRIB rather than published
as a separate file. The reviewed configuration identifies band 1 as the intended
precipitation source, but a real payload must prove that message/band selection.

## Current boundary

The source mappings, catalogue rows, styles, domain, semantic database
constraints, and `eccc_rdpa_ingest` DAG route are installed. Analysis catalogue
times store no forecast lead: `forecast_hour` is null, `valid_time` equals
`interval_end`, interval bounds are explicit, and `time_kind` is `accumulation`.

The operational DAG downloads, validates, converts, and displays preliminary
and final 6-hour and 24-hour precipitation for every discovered valid time.
Each visible analysis cycle and its payloads remain available through the
shared historical archive.
