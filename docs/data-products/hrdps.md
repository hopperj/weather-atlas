# HRDPS continental data contract

**Verification date:** 2026-07-16  
**Verified run:** 2026-07-16 12Z  
**Implementation state:** inventory, catalogue, and full config-driven forecast DAG

This page records the source assumptions implemented by the `hrdps` adapter. It
is not a permanent copy of ECCC's catalogue. Re-run the inventory command and
review ECCC announcements before enabling another field or changing the parser.

## Authoritative references

- [HRDPS overview](https://eccc-msc.github.io/open-data/msc-data/nwp_hrdps/readme_hrdps_en/)
- [HRDPS data on the MSC Datamart](https://eccc-msc.github.io/open-data/msc-data/nwp_hrdps/readme_hrdps-datamart_en/)
- [MSC Open Data usage policy](https://eccc-msc.github.io/open-data/usage-policy/readme_en/)
- [MSC Datamart AMQP access](https://eccc-msc.github.io/open-data/msc-datamart/amqp_en/)

The AMQPS availability feed is the primary real-time path. The parameterless
`eccc_hrdps_ingest` DAG runs hourly at minute 15, consumes matching Sarracenia
deliveries, and reconciles only missing field/hour slots against the recent
immutable Datamart archive.

## Product timing and grid

| Property | Current value |
|---|---|
| Product | High Resolution Deterministic Prediction System (HRDPS) |
| Domain | Pan-Canadian continental |
| Product kind | Deterministic forecast |
| Run hours | 00, 06, 12, and 18 UTC |
| Forecast hours | 000 through 048 hourly |
| Nominal resolution | 2.5 km at 60 degrees north |
| Grid | Rotated latitude/longitude, `RLatLon0.0225` |
| Grid dimensions | 2540 by 1290 |
| First grid point | 39 degrees north, 134 degrees west |

Some post-processed weather elements (`HRDPS-WEonG`) begin at forecast hour 001
because their algorithms require the previous hour.

## Source paths

The documented rolling alias is:

```text
https://dd.weather.gc.ca/today/model_hrdps/continental/2.5km/{HH}/{hhh}/
```

The dated archive observed on 2026-07-16 contains an additional origin segment:

```text
https://dd.weather.gc.ca/{YYYYMMDD}/WXO-DD/model_hrdps/
  continental/2.5km/{HH}/{hhh}/
```

The adapter supports both forms. Explicit run inventory defaults to the dated
archive. Canonical object keys are derived from parsed product, domain, run,
forecast hour, and filename; they never depend on the `/today` alias or the
`WXO-DD` transport segment. This also avoids rollover windows in which the
`/today/model_hrdps` directory exists but is temporarily empty.

## Filename grammar

Current files use:

```text
{YYYYMMDD}T{HH}Z_MSC_HRDPS_{VAR}_{LEVEL}_RLatLon0.0225_PT{hhh}H.{format}
{YYYYMMDD}T{HH}Z_MSC_HRDPS-WEonG_{VAR}_{LEVEL}_RLatLon0.0225_PT{hhh}H.grib2
```

Verified examples include:

```text
20260716T12Z_MSC_HRDPS_TMP_AGL-2m_RLatLon0.0225_PT000H.grib2
20260716T12Z_MSC_HRDPS_RH_AGL-2m_RLatLon0.0225_PT000H.grib2
20260716T12Z_MSC_HRDPS_PRMSL_MSL_RLatLon0.0225_PT000H.grib2
20260716T12Z_MSC_HRDPS-WEonG_VISIFG_Sfc_RLatLon0.0225_PT001H.grib2
```

The parser treats an unrecognized filename as an explicit parser error. A valid
filename whose producer/parameter/level tuple is absent from configuration is
reported as unknown. It is never silently discarded.

## Reviewed field mappings

All reviewed rows are enabled for download, processing, and display.

| Field code | Source selector | Source unit | Canonical unit | State |
|---|---|---|---|---|
| `air_temperature_2m` | `HRDPS / TMP / AGL-2m` | K | degC | enabled |
| `relative_humidity_2m` | `HRDPS / RH / AGL-2m` | percent | percent | enabled |
| `total_cloud_cover` | `HRDPS / TCDC / Sfc` | percent | percent | enabled |
| `surface_pressure` | `HRDPS / PRES / Sfc` | Pa | hPa | enabled |
| `mean_sea_level_pressure` | `HRDPS / PRMSL / MSL` | Pa | hPa | enabled |
| `wind_u_10m` | `HRDPS / UGRD / AGL-10m` | m/s | m/s | enabled |
| `wind_v_10m` | `HRDPS / VGRD / AGL-10m` | m/s | m/s | enabled |
| `wind_gust_10m` | `HRDPS / GUST / AGL-10m` | m/s | m/s | enabled |
| `visibility_surface` | `HRDPS-WEonG / VISIFG / Sfc` | m | km | enabled |
| `total_precipitation_1h` | `HRDPS / APCP-Accum1h / Sfc` | kg/m2 | mm | enabled |

Source-unit values above are expectations that must be checked against ecCodes
metadata during processing. The source filename itself does not encode units.

## Storage inventory

This metadata-only command was run once against the completed 2026-07-16 12Z
archive. It retrieved 49 HTML directory listings and no GRIB files:

```bash
uv run weather-ingest --config-root config inspect-source \
  --product hrdps \
  --run 2026-07-16T12:00:00Z \
  --format json \
  --summary-only
```

Observed result:

| Measurement | Value |
|---|---:|
| Listed objects, all fields | 20,070 |
| Listed bytes, all fields | 34,324,802,709 bytes (about 32.0 GiB/run) |
| Enabled temperature objects | 49 |
| Enabled temperature raw bytes | 178,782,194 bytes (about 170.5 MiB/run) |
| Temperature raw bytes at four runs/day | about 682 MiB/day |
| Estimated processed bytes at configured 1.15 ratio | about 784 MiB/day |
| Parser errors | 0 |
| Missing enabled field-hours | 0 |

Apache directory sizes are rounded, and the processed ratio is a planning
assumption until real COG output is benchmarked. Do not use these numbers as a
capacity guarantee. A hypothetical 30-day raw archive would require roughly
20 GiB for temperature alone before filesystem overhead. Historical retention
therefore requires active disk-capacity monitoring and backups. Expanding to
every listed field would still be inappropriate on the initial server.

## Offline inventory fixtures

Saved, synthetic listings under `tests/fixtures/hrdps/listings` exercise known,
disabled, unknown, and malformed objects without network access:

```bash
uv run weather-ingest --config-root config inspect-source \
  --product hrdps \
  --run 2026-07-16T12:00:00Z \
  --forecast-hour 0 \
  --forecast-hour 1 \
  --listing-fixture tests/fixtures/hrdps/listings
```

When a real GRIB fixture is needed for local integration testing, first run a
single-hour inventory, copy the exact enabled URL from JSON output, and download
only that one object into an ignored local fixture directory. Record its source
URL, byte size, and SHA-256 alongside the test invocation. Do not commit large
operational GRIB files or mirror a whole run into the repository.

## Processing contract

The implemented temperature path performs:

1. filename/run/grid validation;
2. streaming HTTPS download to a deterministic `.part` path;
3. declared-size and SHA-256 checks;
4. atomic raw-file publication;
5. GRIB2 message-envelope validation;
6. ecCodes metadata enumeration;
7. Kelvin-to-Celsius normalization with `gdal_calc.py`;
8. bounded `gdal_translate -of COG` conversion;
9. `gdalinfo -json` validation of COG layout, CRS, dimensions, band count, and nodata;
10. atomic processed-file publication.

Raw and processed paths are semantic and contain no database IDs, for example:

```text
raw/eccc/hrdps/continental/2026/07/16/12/f006/{source-filename}
processed/eccc/hrdps/continental/2026/07/16/12/
  air_temperature_2m/2m_agl/f006.tif
```

The Airflow DAG registers the source object, product time, processed COG,
statistics, bounds, checksum, and provenance through handwritten SQL. A run is
visible to the application only after its configured required fields have an
available asset; retries upsert the same semantic identities rather than
creating duplicates.
