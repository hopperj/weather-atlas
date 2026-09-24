# Daily and hourly forecast page

Implemented 2026-09-06 and redesigned 2026-09-24. Open `/forecast` using
**Forecast** in the site header. The responsive page presents current conditions,
a swipeable 24-hour forecast, a compact seven-day outlook, current weather
details, and an expandable 72-hour model table. The existing map and its
forecast mode remain available.

## Forecast experience

The information order follows a general-purpose forecast workflow:

1. The selected locality, nearest fresh station temperature, current regional
   condition, and today's high/low appear first.
2. The next 24 model hours are presented as horizontally scrollable cards with
   temperature, precipitation amount, humidity, and the applicable regional
   condition icon. A coverage warning appears only when one of these visible
   24 hours is partial or missing.
3. The official seven-day bulletin is condensed into day rows containing day
   and night conditions, POP or conservative wet-weather wording, high/low, and
   official or starred model precipitation amounts.
4. Humidity, wind/gust, pressure, and recent precipitation use the nearest fresh
   collected station when available. A missing observation service does not
   disable the page; model values fill only supported fields and are labelled.
5. The exact 72-hour values, status, and model-run metadata remain available in
   the expandable **72-hour forecast** section for technical inspection.

The interface uses condition-specific, code-native weather symbols and adapts
to phone and desktop widths. It does not claim unavailable UV, visibility,
sunrise/sunset, alerts, or feels-like values.

## Selecting a location

- The first **Forecast region** dropdown contains all collected Nova Scotia
  forecast regions directly. Halifax Metro remains the default.
- Select **Other province or territory…** for the rest of Canada. Choose a
  **Province or territory**, then a **Region** belonging to it. The province
  list covers all other provinces and territories present in the collected feed.
- Both forecast sections use the selected region. Entering Other or changing
  province clears the previous region and its forecasts; an hourly request
  starts only once a new region is selected. No unrelated region is silently
  selected while the user is choosing.
- Select any Nova Scotia region directly in the first dropdown to return; the
  secondary controls collapse.
- Completed selections persist as `/forecast?region={area_id}`. Opening a link
  for another province restores the full selector hierarchy. Incomplete choices
  persist as `?scope=other` or `?scope=other&province=ON`.
- **Use my location** requests browser location only when selected, resolves it
  through `/api/v1/forecast/nearest`, and stores the matched forecast region in
  the same URL format. Denied or unavailable location access leaves manual
  selection usable.

This expands the dedicated forecast page, not the separate NS-only forecast
labels on the map. Region choices are derived from the existing national ECCC
snapshot; they do not trigger new downloads or require a new collection DAG.

## Sources and interpretation

The seven-day section uses the existing ECCC City Page Weather regional snapshot
collected by `eccc_city_forecasts_ingest`. Each region's remaining forecast
periods are retained separately, including day/night conditions, high or low
temperature, humidity, POP and explicitly issued precipitation amounts. Day
and night are grouped under their Atlantic calendar date. Missing values are
displayed as a dash; zero remains zero. Since 2026-09-07, missing precipitation
amounts can be supplemented by starred model estimates as described below.
The API does not discard late forecast
periods just because a different region has a shorter horizon.

Since 2026-09-23, an omitted numeric POP is no longer displayed as an unexplained
dash: recognized wet bulletin descriptions show "Rain expected", "Rain possible"
or equivalent snow/mixed-precipitation wording. Explicit percentages, including
0%, are preserved. Dry or unrecognized descriptions with no percentage omit that
row; the original condition remains visible. No percentage is inferred from
wording or rainfall amounts. This presentation applies to the local forecast and
map labels. Model totals on the local forecast remain independent of POP.

The hourly section samples the already configured GDPS processed rasters at the
selected region's representative coordinate (the mean of its city sites). This
is a model forecast at a point, not a region-wide average or an official hourly
text bulletin. Fields are:

| Display | Catalogue field | Source unit | Display unit |
| --- | --- | --- | --- |
| Temperature | `air_temperature_2m` | degC | °C |
| Humidity | `relative_humidity_2m` | percent | % |
| Precipitation | `total_precipitation_1h` | mm | mm / 1 h |
| Wind | `wind_speed_10m` | m/s | km/h (multiply by 3.6) |
| Gust | `wind_gust_10m` | m/s | km/h (multiply by 3.6) |

GDPS publishes hourly time steps through lead hour 84. The page uses the latest
available GDPS temperature frame for each valid hour and requires companion
fields to match that frame's run and valid time. It never silently combines
different run cycles within one row. A run may change between rows and is
displayed in UTC on every row. Unknown units, non-finite/nodata samples,
out-of-range humidity, and negative precipitation/wind speeds are treated as
missing. Forecast temperature may legitimately be negative.

The window is anchored to the current UTC hour and contains that hour plus the
following 71 hours. Every slot is returned, including gaps. No hourly values are
interpolated from the model's three-hour tail. If a suitable cycle has not been
fully ingested, the page reports partial or missing coverage rather than
repeating values or moving the window into the past. Precipitation is the
one-hour accumulation **ending** at the displayed time, not starting then.
GDPS does not supply hourly POP in this configured feed; official daily POP
remains in the seven-day cards and is not copied into hourly slots.

Current conditions use `GET /api/v1/observations/nearby` at the forecast
region's representative coordinate. The closest fresh station with a
temperature is preferred. Its actual station name, observation time, distance,
and attribution are displayed. The regional bulletin remains the source of the
condition text and high/low; observed and forecast values are not presented as
though they came from one source.

All valid-time displays use `America/Halifax` (Atlantic time, including daylight
saving) with a 24-hour clock, **including regions outside Nova Scotia**. The
page explicitly labels this choice; these are not province-local times. API
times are UTC. The 72 slots represent elapsed
hours, including over clock changes. Region selection is saved in the URL as
`/forecast?region={area_id}`. Halifax Metro is the default when available.

Provider references:

- [ECCC City Page Weather](https://eccc-msc.github.io/open-data/msc-data/citypage-weather/readme_citypageweather-datamart_en/)
- [ECCC GDPS temporal resolution](https://eccc-msc.github.io/open-data/msc-data/nwp_gdps/readme_gdps-datamart_en/)

## API and operational behaviour

- `GET /api/v1/forecast/regions`: all normalized Canadian regions and each
  region's remaining periods within seven days. Includes `province` (two-letter
  code), `provinceName`, region issue time and
  a stale flag if the issue is older than 24 hours or all periods have expired.
  Expired periods are omitted, but the location remains selectable for hourly
  model forecasts. This endpoint requires the snapshot, not the database.
  Nova Scotia regions sort first; remaining regions sort by province/territory
  name and then region name. All 13 province/territory codes are supported.
- `GET /api/v1/forecast/hourly?area_id={16-character-hex-id}`: exactly 72 rows,
  per-row `complete`/`partial`/`missing` status, per-row model run, one-hour
  precipitation start, available-hour and complete-hour counts. Uses existing
  catalogue queries, path validation and point sampling. Four concurrent
  sample operations per request, a 90-second timeout, the existing sample
  request rate limit, and a five-minute Redis cache bound the work.
- Regions and hourly results refresh every five minutes; the hourly query also
  changes when the current UTC hour changes. Refresh is available manually.
- An hourly service failure does not hide an independently loaded daily
  outlook. Changing region clears the previous hourly view while the next one
  loads. Errors and missing coverage are visible.

No new download source, schema migration, credential, or DAG is required.
Existing City Page Weather and GDPS ingestion must be operating. The snapshot
is `processed/eccc/citypage_weather/latest.json` under `WEATHER_DATA_ROOT`.

## Model precipitation fallback — 2026-09-07

The dedicated `/forecast` page now supplements missing seven-day precipitation
amounts from the collected GDPS rasters. Existing normalized bulletin amounts
(including zero, ranges in mm, and snow depths in cm) are preserved verbatim and
have no asterisk. An estimate appears as, for example, `6.2 mm*` or `0.0 mm*`.
Positive estimates below 0.1 mm display as `<0.1 mm*`. The explanation below
the cards identifies GDPS and the units; hovering on a starred amount shows
its forecast period and model initialization. This change does not alter the
hourly table or the separate map-label forecast mode.

### Calculation and provenance

- Sample total precipitation at the selected region's representative
  coordinate, using the existing catalogue/path-validated raster sampling
  helper. This is a point estimate, not a spatial average over the region.
- Select up to four most recent available GDPS precipitation cycles initialized
  within the last 48 hours. Each period uses the newest cycle that supplies a
  complete, valid total; an older complete cycle can fill a gap in a newer one.
  Never combine different initializations inside a period. Adjacent periods
  may use different cycles; the run is retained on each result.
- The model initialization must be no later than the period's start and no
  later than the request time. The total covers the **entire bulletin day/night
  period**, including elapsed hours of today's period, not just hours after
  the user opens the page. It remains a forecast estimate, not a measured total.
- Treat `total_precipitation_1h` as the accumulation over `(valid_time - 1 h,
  valid_time]` and `total_precipitation_3h` over `(valid_time - 3 h, valid_time]`.
  These are rolling field-specific accumulations, not running totals from
  initialization. Generic catalogue product-time interval metadata is shared
  by fields and does not define either field's accumulation duration.
- Tile the period exactly with nonoverlapping intervals, preferring hourly
  intervals where they can cover it. The three-hour field supplies the later
  forecast tail or a complete alternative to missing hourly data. A backwards
  path search ensures a short interval does not strand the rest of the period.
  The amount is the sum of these increments: `P(period) = sum(P(interval))`.
  No double-counting, interpolation, prorating, or POP scaling is used.
- Respect the configured horizons (1-hour field through lead 144, 3-hour field
  through lead 168 at multiples of three). Sparse hourly data after lead 84
  cannot be treated as a continuous series. A period is at most 48 hours.
- Require matching field/run/valid time, units `mm`, finite nonnegative values,
  and no nodata for every sampled interval. If sampling invalidates a planned
  interval, try another exact partition, then another eligible cycle. If none
  fully covers the period, retain null and display a dash. In particular,
  half-hour boundaries or amended non-hour issue times are **not** rounded;
  their periods may remain unavailable despite nearby model data.
- Sum unrounded samples before rounding the API total to two decimal places;
  display one decimal place, with trace handling as above. These are **mm of
  water equivalent**, including rain and melted frozen precipitation, not
  snowfall depth. They are not necessarily consistent with the forecaster's
  text or POP, and are explicitly marked as model-derived.

### Endpoint and UI behaviour

`GET /api/v1/forecast/precipitation?area_id={16-character-hex-id}` returns the
region, bulletin issue, generation time, sample coordinates, source, and a
row for each remaining period. Each row includes exact start/end, status
(`official`, `complete`, or `missing`), nullable `precipitationMm` and `runTime`,
and the exact contributing intervals with field codes for auditability.
`official` means the existing normalized bulletin amount is retained; the
estimate endpoint does not copy or reinterpret that amount.

The request is made only for the selected region and only if it has missing
amounts. It does not sample the entire national region list or start downloads.
Work is limited to four concurrent samples per request and a 90-second timeout,
with the existing point-sampling request limit. Redis caches results for five
minutes, keyed by region, coordinates, issue, complete remaining-period content,
and current UTC hour; bulletin amendments therefore invalidate the cache.
The client refreshes every five minutes and with **Refresh forecasts**.

The client matches region ID, bulletin issue, and both period boundaries before
using a complete estimate. Changing location or bulletin clears the old query's
values. Loading/failure messages do not hide the ECCC bulletin. Missing model
data remains missing, never a fabricated zero. Existing ingestion provides all
required fields; no ETL or collection schedule changes are needed.

### Regression checks

Tests cover full-period totals including elapsed hours, nonoverlapping hourly
and three-hour transitions, invalid samples/units, complete alternative
partitions, gaps, half-hour boundaries, zero/trace amounts, lead horizons,
future/too-old initialization, no mixed-cycle totals, older complete-cycle
fallback, official zero/ranges/snow preservation, bulletin-keyed caching,
malformed/unknown regions, source marking, failed model requests, and clearing
or rejecting mismatched region/issue/period data.

Verification: 50 targeted Python API/catalogue/ingestion tests and all 60
frontend tests passed. Changed-file Python lint, frontend lint, and the
production TypeScript/Vite build passed. The weather API and frontend Docker
images were rebuilt and redeployed; both containers reported healthy. No
collection services were restarted.

Live check at 2026-09-07 12:10 UTC: Halifax's bulletin issued at 08:00 UTC had
13 remaining day/night periods, from September 7 at 08:00 UTC through September
13 at 21:00 UTC. All 13 missing amounts received complete estimates from the
September 7 00:00 UTC GDPS cycle. Monday's API total was 0.61 mm and the page
displayed `0.6 mm*`; Thursday's 1.35 mm displayed `1.4 mm*`. Browser inspection
confirmed starred zero and trace amounts, the source/unit explanation, and
unchanged forecast card layout. This is a live snapshot of availability, not
a guarantee that every future bulletin period will have full model coverage.

## Verification and rollout

Automated coverage includes expired regional bulletins, preserving zero versus
missing values, 72-slot continuity, invalid future runs, exclusion of the
three-hour tail, correct precipitation intervals, exact matching of run/time
for companion fields, unit conversion, malformed/unknown region requests,
changing regions without showing previous values, simultaneous daily/hourly
views, hourly errors, and Atlantic calendar/day-night grouping.

Initial page implementation checks: 288 Python tests passed (19 PostgreSQL integration tests
skipped because `WEATHER_TEST_DATABASE_URL` is not configured); 43 frontend
tests passed. The production TypeScript/Vite build, frontend lint, changed-file
Python lint and frontend formatting checks passed.

The Canada-wide selector extension adds tests for NS-only first-level choices,
province-filtered regions, territories, clearing previous data when switching
province, restoring deep links, incomplete selections, and a catalogue without
NS entries. Backend tests cover all 13 province/territory codes and verify hourly
coordinate sampling for NS, BC and NU.

Selector-extension checks: all 49 frontend tests passed; the targeted forecast
API and health suite passed all 12 tests. Frontend lint, the production build,
changed-file Python lint and formatting checks passed. Docker was checked again
and its daemon socket was still absent, so this extension has not been verified
in a running browser or deployed to the Docker stack.

Local inspection on 2026-09-06 found 641 regions across all 13 provinces and
territories in the real stored snapshot, last generated 2026-07-30T14:00Z:
AB 66, BC 69, MB 57, NB 21, NL 36, NS 23, NT 21, NU 24, ON 133, PE 3,
QC 119, SK 56, YT 13. These are collected ECCC forecast regions, not every
municipality. All expired bulletins are marked stale, with no expired periods
returned as current forecasts. Availability and region counts follow the feed.

The initial editing session could not reach Docker; the later rollout records
below supersede that limitation. To rebuild the page, run from the project
directory:

```bash
docker compose build weather-api frontend
docker compose up -d
```

Open `http://localhost:18080/forecast`. Confirm the two sections load, switching
regions updates both, the main selector lists only NS regions plus Other, and
Other → Province or territory → Region supports a location outside NS. Confirm
its direct URL restores the selections. Check hourly rows span 72 consecutive times, source/run times
are current, and any missing fields remain marked. Check that
`eccc_city_forecasts_ingest` and GDPS ingestion are unpaused if fresh data does
not appear. Existing ingestion schedules supply the data; this page does not
trigger large downloads on demand.

### Subsequent live rollout — 2026-09-06 (Atlantic time)

Docker became available and `./run.sh` completed successfully. All 26 database
migrations were unchanged and verified. The frontend and service images were
rebuilt, all long-running services started, and the configured container health
checks and both API readiness checks passed. Airflow's database, scheduler,
triggerer and DAG processor also reported healthy through its health endpoint.

The gateway publishes `0.0.0.0:18080`. HTTP checks from the host through both
LAN addresses (`10.0.0.146` and `10.0.0.27`) returned 200 for `/forecast`; the
weather readiness endpoint confirmed PostgreSQL, Redis and data-root access.
An independent client device was not tested. The live regions API returned
641 regions across 13 provinces/territories. The Halifax hourly endpoint
returned all 72 slots, with zero currently available hours at verification.

Service startup does not make the archived data current: the regional snapshot
was still dated 2026-07-30 and correctly marked stale. Both city-forecast and
GDPS DAGs were unpaused; a new GDPS run was running. The city-forecast DAG still
had a pre-restart running record from July 30. No runs were manually cleared,
backfilled, or marked successful during this startup verification.

### Forecast experience redesign rollout — 2026-09-24

The redesigned frontend image was built and deployed to the running Compose
stack; the frontend container reported healthy. The public HTTPS page loaded
641 selectable Canadian regions, a fresh Halifax bulletin, all seven daily rows,
24 visible hourly cards, and the expandable 72-hour table. At verification the
hourly response had 71 available and complete hours; the visible first 24 were
complete, so the page correctly kept the coverage warning out of the primary
view.

Live browser acceptance confirmed the nearest fresh station reading from
Bedford Basin, station name/time/attribution, humidity, wind/gust, pressure,
hourly model values, and model precipitation fallbacks. The page was visually
checked at its normal desktop width and at a 390 by 844 phone viewport. No
browser console errors or warnings were present. The frontend production build,
lint, and all 124 tests across 17 files passed. This change required no backend
schema migration, new package, credential, or ingestion change.
