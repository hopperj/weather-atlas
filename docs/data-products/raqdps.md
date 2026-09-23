# RAQDPS air-quality data contract

**Verification date:** 2026-07-16  
**Verified run:** 2026-07-16 12Z, all forecast hours 000–072  
**Implementation state:** adapter, inventory, catalogue, and config-driven DAG

## Authoritative references

- [RAQDPS overview](https://eccc-msc.github.io/open-data/msc-data/nwp_raqdps/readme_raqdps_en/)
- [RAQDPS on the MSC Datamart](https://eccc-msc.github.io/open-data/msc-data/nwp_raqdps/readme_raqdps-datamart_en/)
- [Official RAQDPS variable table](https://eccc-msc.github.io/open-data/assets/csv/RAQDPS_Variables-List_en.csv)
- [MSC Open Data usage policy](https://eccc-msc.github.io/open-data/usage-policy/readme_en/)

The ECCC AMQPS availability feed is the primary real-time path. The
parameterless DAG also reconciles only missing catalogue slots against recent
archive listings so missed notifications do not leave a partial run.

## Current source contract

| Property | Value |
|---|---|
| Product kind | Deterministic air-quality forecast |
| Domain | North America |
| Runs | 00 and 12 UTC |
| Lead times | 000–072 hourly |
| Grid | Rotated latitude/longitude, `RLatLon0.09` |
| Dimensions | 729 by 599 |
| Nominal resolution | 10 km at 60 degrees north |

Rolling and dated source paths:

```text
https://dd.weather.gc.ca/today/model_raqdps/10km/grib2/{HH}/{hhh}/
https://dd.weather.gc.ca/{YYYYMMDD}/WXO-DD/model_raqdps/
  10km/grib2/{HH}/{hhh}/
```

Filename grammar:

```text
{YYYYMMDD}T{HH}Z_MSC_RAQDPS_{VAR}_{LEVEL}_RLatLon0.09_PT{hhh}H.grib2
```

## Enabled surface fields

| Field | Source selector | Official source unit | Canonical unit |
|---|---|---|---|
| PM2.5 | `PM2.5 / Sfc` | kg/m3 | ug/m3 |
| PM10 | `PM10 / Sfc` | kg/m3 | ug/m3 |
| Ozone | `O3 / Sfc` | ppb | ppb |
| Nitrogen dioxide | `NO2 / Sfc` | ppb | ppb |
| Sulfur dioxide | `SO2 / Sfc` | ppb | ppb |

The particulate conversion multiplies kg/m3 by 1,000,000,000. It is a named,
tested conversion—never an evaluated configuration expression.

The current source also exposes nitric oxide, wildfire-smoke components, and
column-integrated particulate fields. They remain unknown/disabled until a
specific product decision is made. CO and AQHI are not present in the current
official RAQDPS Datamart variable list or the verified run, so this adapter does
not pretend they are available.

## Full-run metadata inventory

The following command retrieved only 73 directory listings and no GRIB payloads:

```bash
uv run weather-ingest --config-root config inspect-source \
  --product raqdps \
  --run 2026-07-16T12:00:00Z \
  --format json \
  --summary-only
```

| Measurement | Result |
|---|---:|
| All listed objects | 882 |
| All listed bytes | 303,930,368 bytes |
| Enabled pollutant objects | 365 (5 fields × 73 hours) |
| Enabled listed bytes | 178,524,160 bytes (about 170.3 MiB/run) |
| Estimated enabled raw volume | about 340.5 MiB/day |
| Estimated processed volume at ratio 1.15 | about 391.6 MiB/day |
| Missing enabled field-hours | 0 |
| Parser errors | 0 |

Directory sizes are rounded planning values. Exact integrity checks use the HTTP
`Content-Length`, streamed byte count, and SHA-256 when an object is downloaded.
No operational GRIB file was downloaded during this verification.

## Remaining work

The adapter, strict configuration, field classification, conversion definitions,
full-run inventory, catalogue mappings, field-specific display palettes, and the
generated `eccc_raqdps_ingest` route are in place. A representative real
GRIB/COG run, field-range benchmarks, and end-user visual verification remain
operational acceptance work.
