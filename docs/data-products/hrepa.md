# HREPA ensemble precipitation-analysis data contract

**Verification date:** 2026-07-19  
**Verified valid time:** 2026-07-19 06Z  
**Implementation state:** operational NetCDF ingestion, COG publication, and display verified

## Authoritative references

- [HREPA overview](https://eccc-msc.github.io/open-data/msc-data/nwp_hrepa/readme_hrepa_en/)
- [HREPA on the MSC Datamart](https://eccc-msc.github.io/open-data/msc-data/nwp_hrepa/readme_hrepa-datamart_en/)
- [MSC Open Data usage policy](https://eccc-msc.github.io/open-data/usage-policy/readme_en/)

## Product semantics

HREPA is a 6-hour ensemble analysis valid at 00, 06, 12, and 18 UTC. It is not a
forecast and it is not distributed as GRIB2. The timestamp is the valid/end time
of the preceding six-hour accumulation and `PT0H` marks an analysis.

Three NetCDF files are published at each valid time:

| File parameter | Meaning |
|---|---|
| `Precip-Accum06h` | 25 members: one control and 24 perturbed analyses |
| `Precip-Accum06h-Pct25` | 25th-percentile analysis |
| `Precip-Accum06h-Pct75` | 75th-percentile analysis |

The full-member file also contains the confidence index (`CFIA`). The percentile
files are distinct remote assets; individual ensemble members and CFIA are
variables/dimensions inside the full NetCDF asset.

## Source layout and grid

```text
https://dd.weather.gc.ca/today/model_hrepa/2.5km/{HH}/
https://dd.weather.gc.ca/{YYYYMMDD}/WXO-DD/model_hrepa/2.5km/{HH}/
```

```text
{YYYYMMDD}T{HH}Z_MSC_HREPA_
  Precip-Accum06h[-Pct25|-Pct75]_Sfc_RLatLon0.0225_PT0H.nc
```

| Property | Value |
|---|---|
| Format | NetCDF (`.nc`) |
| Grid | `RLatLon0.0225` |
| Dimensions | 2438 by 1188 |
| Nominal resolution | 2.5 km |
| Coverage | Canada and the northern United States |

The HREPA grid dimensions differ from both HRDPA and HRDPS even though all three
use a `RLatLon0.0225` label.

## Live metadata inventory

```bash
uv run weather-ingest --config-root config inspect-source \
  --product hrepa \
  --reference-time 2026-07-16T12:00:00Z \
  --format json \
  --summary-only
```

The dated archive listing contained all three expected NetCDF files. They mapped
as ensemble members, 25th percentile, and 75th percentile with no unknown
objects, parser errors, or missing fields. Rounded listing sizes totalled
398,458,880 bytes; 332 MiB of that listing was the multi-member file.

During the check shortly after 2026-07-17 00Z, the documented rolling
`/today/model_hrepa/` directory existed but was temporarily empty while the dated
2026-07-16 archive was complete. The adapter supports both paths, but operational
availability must come from AMQPS notifications rather than polling `/today`.

## Operational processing

`eccc_hrepa_ingest` runs hourly at minute 15 with no parameters. The NetCDF
validator selects `Precip-Accum06h`, `q025`, or `q075` explicitly and verifies
valid time, `kg.m-2` units, CRS, dimensions, and expected band count before COG
creation.

The complete 25-member file, including its embedded confidence-index variable,
is retained as the raw source. The map-ready output uses band 1, the control
member, while the percentile files are published as independent 25th- and
75th-percentile layers. This keeps the full source available for future
member-by-member or confidence-index tooling without presenting an arbitrary
perturbed member as a deterministic analysis.

The verified 2026-07-19 06Z cycle completed with three discovered, downloaded,
processed, and available assets and no failed objects.
