# RDPS regional data contract

**Verification date:** 2026-07-16  
**Sampled run:** 2026-07-16 12Z at forecast hours 000, 001, and 084  
**Implementation state:** representative inventory, catalogue, and config-driven DAG

## Authoritative references

- [RDPS overview](https://eccc-msc.github.io/open-data/msc-data/nwp_rdps/readme_rdps_en/)
- [RDPS on the MSC Datamart](https://eccc-msc.github.io/open-data/msc-data/nwp_rdps/readme_rdps-datamart_en/)
- [Official RDPS variable table](https://eccc-msc.github.io/open-data/assets/csv/RDPS_Variables-List_en.csv)

## Current source contract

| Property | Value |
|---|---|
| Product kind | Deterministic regional forecast |
| Domain | North America and adjacent areas |
| Runs | 00, 06, 12, and 18 UTC |
| Lead times | 000–084 hourly |
| Grid | Rotated latitude/longitude, `RLatLon0.09` |
| Dimensions | 1140 by 1045 (verified from the live GRIB2 product on 2026-07-17) |
| Nominal resolution | 10 km at 60 degrees north |

```text
https://dd.weather.gc.ca/today/model_rdps/10km/{HH}/{hhh}/
https://dd.weather.gc.ca/{YYYYMMDD}/WXO-DD/model_rdps/10km/{HH}/{hhh}/
```

```text
{YYYYMMDD}T{HH}Z_MSC_RDPS_{VAR}_{LEVEL}_RLatLon0.09_PT{hhh}H.{format}
```

The current operational filenames use descriptive `VAR` names. Examples observed
in the verified run include `AirTemp`, `RelativeHumidity`, `TotalCloudCover`,
`Pressure`, `WindU`, `WindV`, and `WindGust`. Older examples and the official
variable CSV also show short GRIB abbreviations such as `TMP`; configuration
matches the current filenames, while ecCodes remains authoritative inside GRIB.

## Configured fields

All ten configured fields are enabled: temperature, humidity, cloud cover,
surface/MSL pressure, U/V wind, gust, one-hour precipitation, and one-hour
snowfall.

Representative metadata inventory:

```bash
uv run weather-ingest --config-root config inspect-source \
  --product rdps \
  --run 2026-07-16T12:00:00Z \
  --forecast-hour 0 \
  --forecast-hour 1 \
  --forecast-hour 84 \
  --format json \
  --summary-only
```

The three sampled directories contained 1,193 objects. All three temperature
frames were found, with zero parser errors and no missing enabled field-hours.
The projected temperature estimate is about 55 MiB/run and 220 MiB/day, but it
is based on rounded sizes from only three hours and is not a capacity benchmark.

## Verification boundary

The current path, filename grammar, run cadence, first/last lead time, and selected
field names are live-verified, and all configured fields now have catalogue and
display-style records that preserve their YAML enablement flags, and the
generated `eccc_rdps_ingest` route is implemented. A complete 85-directory
inventory, representative real GRIB/COG run, COG benchmark, and visual
acceptance test have not been performed, so RDPS remains conservatively limited
to 2 m temperature.
