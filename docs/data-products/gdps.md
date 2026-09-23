# GDPS global data contract

**Verification date:** 2026-07-28  
**Sampled runs:** 2026-07-16 12Z and 2026-07-27 12Z  
**Implementation state:** operational ingestion, catalogue, and map overlays

## Authoritative references

- [GDPS overview](https://eccc-msc.github.io/open-data/msc-data/nwp_gdps/readme_gdps_en/)
- [GDPS on the MSC Datamart](https://eccc-msc.github.io/open-data/msc-data/nwp_gdps/readme_gdps-datamart_en/)
- [Official GDPS variable table](https://eccc-msc.github.io/open-data/assets/csv/GDPS_Variables-List_en.csv)

## Current source contract

| Property | Value |
|---|---|
| Product kind | Deterministic global forecast |
| Runs | 00 and 12 UTC |
| Lead times | Hourly 000–084, then every 3 hours 087–240 |
| Grid | Regular latitude/longitude, `LatLon0.15` |
| Dimensions | 2400 by 1201 |
| Nominal resolution | 0.15 degrees, approximately 15 km |

The forecast schedule is represented as two validated, non-overlapping segments.
Hours 085 and 086 are intentionally absent.

```text
https://dd.weather.gc.ca/today/model_gdps/15km/{HH}/{hhh}/
https://dd.weather.gc.ca/{YYYYMMDD}/WXO-DD/model_gdps/15km/{HH}/{hhh}/
```

```text
{YYYYMMDD}T{HH}Z_MSC_GDPS_{VAR}_{LEVEL}_LatLon0.15_PT{hhh}H.{format}
```

Current operational files use descriptive names such as `AirTemp`,
`RelativeHumidity`, `TotalCloudCover`, `Pressure`, `WindSpeed`, `WindU`,
`WindV`, and `WindGust`. The following 12 configured fields are downloaded,
processed, and exposed as map overlays:

| Overlay | ECCC source | Forecast availability |
|---|---|---|
| Air temperature, 2 m | `AirTemp_AGL-2m` | 000–240 |
| Relative humidity, 2 m | `RelativeHumidity_AGL-2m` | 000–240 |
| Wind speed, 10 m | `WindSpeed_AGL-10m` | 000–240 |
| Eastward wind, 10 m | `WindU_AGL-10m` | 000–240 |
| Northward wind, 10 m | `WindV_AGL-10m` | 000–240 |
| Wind gust, 10 m | `WindGust_AGL-10m` | 000–240 |
| Mean sea-level pressure | `Pressure_MSL` | 000–240 |
| Surface pressure | `Pressure_Sfc` | 000–240 |
| Total cloud cover | `TotalCloudCover_Sfc` | 000–240 |
| Total precipitation, 1 hour | `Precip-Accum1h_Sfc` | 001–144 |
| Total precipitation, 3 hours | `Precip-Accum3h_Sfc` | 003–168, every 3 h |
| Snowfall, 1 hour | `Snowfall-Accum1h_Sfc` | 001–84 |

The direct 10 m wind-speed field avoids requiring the browser to derive speed
from U/V rasters. The 3-hour precipitation field extends mapped precipitation
through the full seven-day window while preserving the accumulation period in
the variable label.

Representative metadata inventory:

```bash
uv run weather-ingest --config-root config inspect-source \
  --product gdps \
  --run 2026-07-16T12:00:00Z \
  --forecast-hour 0 \
  --forecast-hour 1 \
  --forecast-hour 84 \
  --forecast-hour 87 \
  --forecast-hour 240 \
  --format json \
  --summary-only
```

The five 2026-07-16 directories contained 1,683 objects. Temperature was found
at all sampled hours, including both sides of the cadence transition and the
final 240-hour lead. On 2026-07-27, live Datamart inventory also confirmed
`WindSpeed_AGL-10m` through hour 240, one-hour precipitation through hour 144,
and three-hour precipitation on three-hour boundaries through hour 168.

## Collection cadence and recovery

ECCC initializes GDPS at 00 and 12 UTC and publishes individual files
progressively. Sarracenia AMQP delivery is the low-latency path. The
`eccc_gdps_ingest` inventory reconciliation DAG runs every 15 minutes
(`*/15 * * * *`) rather than only twice daily, so it can process each tranche
soon after publication and repair missed AMQP notifications.

Each reconciliation run is bounded to 128 objects and reserves 25% of that
capacity for new discovery. The remaining 75% can recover incomplete
registrations. This prevents either a large historical backlog or a long
publication cycle from starving newly available forecast fields.

Raw sources and processed COGs are retained in the historical archive. Paths,
checksums, GRIB metadata, forecast times, raster geometry, and conversion keys
are recorded in PostgreSQL. A run is safe to repeat: available current-version
COGs are skipped, while missing or obsolete outputs are rebuilt.

## Verification boundary

The source paths, filename grammar, mixed forecast cadence, first/final lead
times, global grid, all 12 configured field identities, and the three extended
availability windows are live-verified. Catalogue migration 0026 registers the
two new field mappings and their field-specific styles. The application exposes
only forecast frames that have completed GRIB validation and COG registration;
an uncollected lead time is never represented as an available overlay.
