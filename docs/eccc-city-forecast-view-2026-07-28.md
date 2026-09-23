# ECCC official seven-day forecast view implementation record

**Implemented:** 2026-07-28  
**Provider:** Environment and Climate Change Canada, Meteorological Service of
Canada  
**Product:** City Page Weather XML

## Objective

Add a plain-language forecast mode for people who want a conventional
seven-day weather map rather than meteorological colour contours. Each
available official forecast region is labelled with temperature, relative
humidity, probability of precipitation (POP), and an issued precipitation
amount. The view starts with a Nova-Scotia-wide overview and supports close-up
zooming to focus on just a few towns (updated 2026-09-08).

## Source and cadence

ECCC's City Page Weather feed is the source used to produce public city forecast
pages. The official Datamart documentation says XML files are updated hourly at
a minimum, with earlier updates possible for warnings and amendments:

<https://eccc-msc.github.io/open-data/msc-data/citypage-weather/readme_citypageweather-datamart_en/>

The parameterless `eccc_city_forecasts_ingest` Airflow DAG runs every 15 minutes.
It inventories the current and recent UTC issue directories for all 13 province
and territory codes, chooses the newest English issue per SiteNameCode, and
downloads only filenames that differ from the local manifest.

## Normalization

The XML parser retains the official location, region, UTC issue time, local UTC
offset, period name, temperature class/value, relative humidity, POP,
condition, and precipitation wording. Period validity is represented as the
issue-to-boundary partial period followed by 12-hour day/night periods. The
provider's UTC offset is used so validity remains tied to each area's local
forecast day.

Several city sites can share one forecast region. They are collapsed by
`(province, region)`, the named town's official site supplies the map coordinates,
and the newest source bulletin supplies the values. Coordinates are not averaged
across coastal and inland sites. This avoids duplicating an identical regional
forecast around Halifax, Digby, Antigonish, and other multi-site regions.

Precipitation amount is not inferred from POP. A numeric amount is extracted
only when ECCC issues wording such as `Rainfall amount 10 to 20 mm` or
`Snowfall amount 5 cm`. An absent amount is displayed as `—`; when the issued
POP is exactly zero, the amount is displayed as `0 mm`.

## Storage and API

Only the latest raw XML per site is retained, bounding this convenience
product's storage:

```text
raw/eccc/citypage_weather/latest/{PROVINCE}/{SITE_CODE}.xml
processed/eccc/citypage_weather/latest.json
processed/eccc/citypage_weather/manifest.json
```

`GET /api/v1/city-forecasts?valid_time=...` selects the valid regional period
for a UTC instant and returns map-ready GeoJSON. The response includes source
and validity metadata and supports ETag revalidation.

## User interface

The control panel now switches between **Map overlays** and **7-day forecast**.
The dedicated forecast view requests Nova Scotia (`province=NS`) so adjacent
provinces do not obscure the province's 23 official forecast-region labels at
the initial whole-province overview.
In seven-day mode:

- raster layers and wind arrows are unmounted;
- the map initially fits `[-66.7, 43.2, -59.5, 47.2]`;
- the initial bounds fit is capped at MapLibre level 6, but interactive zoom
  retains the map's normal level-14 maximum;
- only regions whose town coordinates lie inside the current map viewport are
  labelled; there is no fixed-degree margin retaining offscreen towns at close zoom;
- each visible region is an HTML map marker with `Temp`, `Hum`, `POP`, and
  `Precip Amount`;
- cards sit on their towns when space allows. Crowded cards move to nearby free
  space, avoiding other cards and the map controls, rather than using a fixed
  screen grid. Layout uses measured card dimensions and updates after panning,
  zooming, resizing, or changing forecast periods;
- displaced cards have leader lines to their exact town coordinates. Cards
  containing their own town do not draw a pointer over the forecast text;
- crowded overview layouts compact their spacing and improve card assignments
  to keep displacement small. If a very small viewport cannot fit every card,
  all forecasts remain available with minimum-overlap placement;
- the UTC time banner becomes `FORECAST PERIOD`;
- the footer steps through 12-hour periods in the common forecast horizon.

Returning to map overlays restores the catalogue-backed raster controls. Both
modes use the same level-14 maximum zoom.

## First collection

The initial live collection discovered 844 official sites. Four documents had
current observations but no active forecast bulletin and were explicitly
recorded as unavailable. The remaining 840 sites normalized to 641 official
province/region combinations, including 23 Nova Scotia regions.

## Verification

Automated coverage checks:

- provider listing deduplication and English-file selection;
- XML identity, values, coordinates, and local day/night validity;
- precipitation-amount extraction without invented totals;
- regional deduplication;
- API period selection and ETag behavior;
- frontend seven-day timeline and missing-value display;
- location-first card layout, measured heights, map-edge/control avoidance,
  deterministic placement, dense provincial overview, and pointer geometry;
- UI switching that removes variable and overlay controls;
- DAG schedule and bounded pool use.

Live acceptance must confirm that the official forecast labels render over Nova
Scotia, no colour contour remains, the timestamp changes with the footer, and
the user can zoom past level 6 into a view with only a few town labels.
