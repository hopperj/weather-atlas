# Weather Atlas experience roadmap

Updated 2026-09-13. Planning only: this document does not activate ingestion,
change clients, deploy services, or request device permissions.

This records the Windy-inspired recommendations discussed with the user and adds
the requested astronomy observing-conditions screen. It complements, rather than
replaces, the existing platform implementation and operations plans.

## Principles

- Weather acquisition, normalization, databases, derived forecasts, astronomical
  calculations, and observing-window assessment stay on the server. Web, iPhone,
  and Android render and cache server results; they never collect provider data.
- Keep Forecast-first startup, compact forecast headers, the clean location
  picker, explicit location-following controls, and silent routine updates.
- Preserve official regional bulletins separately from point-model forecasts.
  Missing data is not zero; model agreement is not a calibrated probability.
- New sources require availability, format, coverage, licensing, and resource
  checks. Public demonstration pages are not automatically usable data APIs.

## Existing proposed workstreams

1. **More usable map space:** compact Model / Radar / Satellite controls, a slim
   legend/time/playback bar, expandable advanced settings, and a draggable
   location panel on phones or resizable panel on desktop.
2. **Linked weather timeline:** optional aligned multi-variable meteogram,
   synchronized map time, and a geographically fixed inspection pin.
3. **Point forecasts and model comparison:** server-sampled coordinate forecasts
   and aligned HRDPS/RDPS/GDPS series, preserving each model's horizon and cadence.
4. **Storm view:** satellite beneath radar, independently controlled layers,
   warning boundaries, coverage masks, and honest source timestamps. Validated
   nowcasting is separate future work, not an extension of historical playback.
5. **Warnings and notifications:** official ECCC warning lifecycle first;
   optional saved-place notifications and custom thresholds later. No background
   GPS is needed for fixed-place subscriptions.
6. **Verification and uncertainty:** forecast-versus-station comparisons and
   model-agreement ranges before any calibrated confidence product.
7. **Presentation improvements:** wind streamlines as rendering, a locked colour
   scale option, favourite layers/presets, practical local weather details, and
   shareable views.
8. **Shared service quality:** consistent product metadata and product-specific
   completeness/freshness checks, building on the existing catalogue and ETL.
9. **Later planning tools:** activity windows, weather along routes, and coastal
   forecasts, subject to source and operational scope checks.

These are recommendations for Weather Atlas, not a commitment to reproduce
Windy's implementation. Relevant references include Windy's
[location forecast and comparison update](https://www.windy.com/articles/43908),
[alerts overview](https://www.windy.com/articles/43906), and
[planning and station tools](https://www.windy.com/articles/43434).

## New workstream: Astronomy — observing conditions

### Purpose and entry points

Answer: **When is the next useful observing window at this site, and what might
limit it?** This is a dedicated screen on iPhone and Android and a dedicated
page/panel on the web, not another large widget in the regular forecast.

Add an Astronomy entry from Forecast, Saved locations, and the map's selected
location panel. Restore the last astronomy site/mode; on first entry, seed it from
the selected map pin or current forecast location without changing the regular
Forecast screen's location or following mode. Use the configured default location,
initially Halifax, if neither a selected site nor a usable GPS fix is available.
The example UK coordinate is a design reference, not a new app default or a
promise of global weather coverage.

[Clear Outside](https://clearoutside.com/forecast/50.7/-3.52) is a useful reference
for its time-aligned cloud layers and environmental details. Our design should
emphasize readable nights and explanations rather than copying its layout or
scraping its forecasts.

### Exact-coordinate location selection — required for the first release

The cloud-cover forecast is a **point forecast**, independent of ECCC forecast
areas. A user must be able to select any valid coordinate, including a remote
observing site with no nearby town. Forecast-area IDs and nearest-town lookups
are not prerequisites for selecting a site or requesting its cloud forecast.

- **Use GPS:** an obvious location button in the compact header enables location
  following while the screen is active, using the existing foreground permission
  flow. Tapping it again disables following and retains the last chosen point.
  A late location callback must not move the site after following is disabled.
  Accept the device's available accuracy, expose approximate/stale-fix status,
  and do not add a requirement for precise or background location permission.
- **Choose on map:** open a clean, overlay-free picker, visually consistent with
  the regular Forecast picker. Tap/hold to drop a pin, move it to refine the
  coordinate, or select a city/town as a convenient starting point. Provide
  latitude/longitude entry for a known observing site. Panning does not change
  the active site; **Use this location** confirms it and disables GPS following.
  Cancelling leaves the existing site and following mode untouched.
- **Do not reuse regional snapping:** the current iOS
  `ForecastLocationMapModel.dropPin` calls `nearestForecast` and confirms a
  `ForecastRegion`. Reuse its map presentation and interaction patterns, but add
  a point-selection mode/model that returns coordinates directly. Cloud forecasts
  must never replace a dropped pin with a region's representative coordinate.
  Equivalent point selection is required on web and Android.
- **Independent saved sites:** persist the astronomy coordinate, optional name,
  and GPS/manual mode separately from the regular regional forecast selection.
  Saved observing sites store their coordinates, not only a forecast-area ID.
  Use a place/site name when known and coordinates otherwise; naming a pin after
  a nearby town must not move it. Do not store a history of GPS movements.
- **Failures and refreshes:** denied/unavailable GPS keeps the current site and
  offers map selection; with no site, use the configured default, initially
  Halifax, and identify it as a default rather than a GPS fix. Throttle/debounce
  movement-driven requests to avoid GPS-jitter refreshes. Cancel superseded work
  and reject late responses so another location's forecast is never displayed
  under the new site's name. Ordinary same-site refreshes remain silent.

The app sends the selected latitude/longitude to the server; **the server computes
the cloud forecast at that point from already-collected model data**. The phone
does not download or interpolate weather grids, collect upstream data, or run
astronomical/weather calculations. This satisfies arbitrary-location forecasts
while preserving the server-owned ETL architecture.

Selecting an exact coordinate does not imply GPS-scale weather precision. The
server samples/interpolates the native model grid using a documented method and
returns the requested point, effective sample location/footprint, model resolution,
source/run and valid times. Keep the pin at the requested point even when the
model uses a nearby cell. Show explicit per-field coverage/missing-data states
outside collected coverage, never silently substitute a forecast town or fabricate
fine-resolution cloud information.

### Screen structure

- **Compact header:** site, forecast issue time, model, and site-local timezone,
  with prominent **Use GPS** and **Choose on map** controls. Indicate GPS versus
  fixed-site mode. Put accuracy, resolution, sampling location, and provenance in
  expandable details.
- **Night selector:** Tonight, Tomorrow night, and subsequent dated nights. Label
  a session with both dates when it crosses midnight. An optional noon-to-noon
  view keeps an entire observing night together; midnight remains explicitly
  marked with weekday/date, including on the existing 72-hour chart.
- **Observing-window summary:** automatically show the server's best qualifying
  interval and limiting factors. For example, a fixture might read “Clearest
  window 23:00–02:00; high cloud increases later.” This is illustrative text, not
  an actual forecast. Show “No qualifying window” or “Insufficient data” honestly.
- **Time-aligned grid:** fixed row labels, horizontal time scrolling, readable
  values, and consistent metric-specific colour scales. Tapping an interval opens
  its details and explanation. Support a night-only filter and a full-day view.
- **Map link:** inspect the chosen cloud layer at the selected time while
  retaining the observing-site marker. Manual satellite selection must remain
  explicit; label optical limitations at night and offer infrared separately.
- **Field use:** optional dim/red presentation, accessible text and symbols in
  addition to colours, large-text support, and no bright loading flashes during
  background updates. Do not alter system brightness without an explicit control.

### Information to present

| Group | Fields and interpretation |
| --- | --- |
| Clouds | Total, low, middle, and high cloud fractions; display actual published intervals. Layer percentages are not additive and total cover is not a probability of a clear night. |
| Darkness | Sunset/sunrise, twilight transitions, and astronomical-dark intervals. |
| Moon | Phase/illuminated fraction, rise/set, and altitude over the night; identify moonless dark intervals instead of judging moonlight from phase alone. |
| Equipment/weather | Temperature, humidity, dew point and temperature–dew-point spread, wind/gusts, precipitation, and published visibility/fog information where supported. |
| Astronomy-specific | Separate seeing and transparency rows when a verified source is integrated; explain missing coverage rather than creating substitute scores. |
| Confidence/context | Source/run age, forecast cadence, missing fields, and cross-model cloud disagreement when comparable products exist. |

Use Sun altitude thresholds of −6°, −12°, and −18° for the twilight boundaries,
with astronomical darkness below −18°. Calculations must handle dates without a
rise/set event or astronomical darkness, as well as site-local daylight-saving
changes. Predicted horizon events assume a documented horizon/refraction model,
not knowledge of local trees and buildings.
[USNO definitions](https://aa.usno.navy.mil/faq/RST_defs)

Keep seeing (image steadiness affected by atmospheric turbulence), transparency
(astronomical clarity), horizontal visibility, and cloud cover distinct. A clear
sky or low surface wind is not sufficient evidence of good seeing. ECCC has
dedicated [seeing](https://weather.gc.ca/astro/seeing_e.html) and
[transparency](https://weather.gc.ca/astro/transparence_e.html) products; inspect
their documented assumptions before exposing classifications or units.

Dew assessment must be labelled as a heuristic, not a measured telescope-optics
temperature or a guarantee against condensation. Surface weather alone does not
describe the temperature of radiatively cooled equipment.

### Observing windows, not an opaque overall score

Initially provide an explainable “cloud/darkness window” using documented,
configurable cloud, darkness, precipitation, and wind criteria. Return start/end,
qualifying duration, limiting factors, missing inputs, and rule version. Missing
required fields must never create a favourable rating. Thresholds require fixture
review and observing feedback before release; they are not scientific constants.

Allow separate preferences for deep-sky work and lunar/planetary observing: do
not universally mark moonlit hours as bad. Until seeing/transparency are
available, explicitly say that a cloud/darkness window does not assess those
conditions. Do not display a numeric probability of success without validation.

### Server/data prerequisites

Repository inspection on 2026-09-13 found total cloud cover, temperature,
humidity, winds and precipitation configured in the deterministic products, plus
HRDPS visibility. It did not find low/middle/high cloud, seeing, or transparency
configured in those catalogues. Configuration is not proof of complete live data.
Relevant files are `config/variables/atmospheric.yaml`,
`config/variables/deterministic_atmospheric.yaml`, and `config/models/*.yaml`.

1. **Inventory and verify sources.** Find supported machine-readable layered-cloud
   fields and astronomy products; verify units, cloud-layer definitions, grids,
   publication cadence, availability, retrieval terms, and storage cost. Never
   decompose total cover into invented low/middle/high values or infer numeric
   forecasts from website colours. ECCC publicly documents North American
   astronomy forecasts through 84 hours, with hourly cloud/transparency and
   three-hourly seeing. Their existence is promising, but a supported ingestible
   numerical feed has not been verified by this planning task.
   [ECCC astronomy overview](https://weather.gc.ca/astro/)
2. **Extend existing ETL.** Add reviewed adapters/configuration, normalized fields,
   coverage and quality flags, and bounded scheduled preparation. Keep collection
   independent of whether any client screen is open. Use the existing database,
   registered raster storage, caching, and API rather than a new weather backend.
3. **Prepare astronomy results on the server.** Calculate solar/lunar events and
   observing windows using a tested ephemeris implementation. Batch/cache results
   for saved/popular observing sites, but do not require a site to be preregistered:
   any valid coordinate can use bounded server-side point sampling of collected
   grids. Reuse the point-forecast infrastructure, preserving cloud-layer units
   and missing masks. Cache by model/run, fields, valid intervals and documented
   spatial sampling key; return the user's original requested coordinate even
   when sharing a grid-cell cache entry. A request must not trigger upstream
   collection or an ETL job. Compute timezone and Sun/Moon events for the observing
   point, not a nearby forecast area's centre. Store calculation versions and
   distinguish ephemeris dates from weather run times.
4. **Publish one shared contract.** Proposed endpoint:
   `GET /api/v1/astronomy/forecast?latitude=…&longitude=…`.
   No forecast-area ID is required. Validate finite latitude/longitude and bounds.
   Include requested/sample coordinates, sampling method/resolution, site timezone,
   per-field source/run, native valid intervals, units, missing reasons, freshness,
   night events, observing-window explanations, and available map-layer references.
   This is a proposed API, not an endpoint implemented by this document.
5. **Respect horizon changes.** Current configuration has HRDPS through 48 hours,
   RDPS through 84, and GDPS hourly through 84 then three-hourly. Target detailed
   first nights and a seven-night outlook only where collected data supports it.
   Preserve three-hour blocks; do not invent seven days of hourly precision or
   silently splice models. Longer-range astronomy-specific rows may remain empty.

Manual/map selection needs no location permission; GPS reuses the existing
foreground location consent flow. No additional permission category is needed.
Optional saved-site notifications belong to the separate opt-in notification
workstream. No account, background
location, camera, compass, or augmented-reality feature is required.

### Delivery and acceptance

**A — Core observing screen:** shared point-forecast/time infrastructure; source
validation and ETL for layered clouds; GPS/manual exact-coordinate location
controls and independent saved sites; cloud grid, dark/Moon intervals, equipment
weather, explainable cloud/darkness windows, and web/iOS/Android parity. If layered
clouds are unavailable, label a total-cloud-only preview as incomplete rather than
claiming the full feature is delivered.

**B — Astronomy depth:** verified seeing/transparency feeds, model cloud comparison,
and assessment validation. If no suitable source exists, retain explicit
unavailability and revisit scope with the user.

**C — Optional extensions:** suitable-window alerts, annual darkness planning,
target-specific Moon separation/altitude, and a licensed light-pollution baseline.
Any sky-brightness/Bortle estimate must show source and vintage, not masquerade as
a live measurement. ISS passes and a full planetarium are not core scope.

Acceptance checks:

- A chosen site is sampled at its coordinate, not silently moved to a forecast
  town; test pins both inside and outside official forecast areas and away from
  named places. Out-of-coverage locations are explicit and the pin stays put.
- GPS enable/disable, approximate accuracy, permission denial, unavailable/stale
  fixes, map confirmation/cancellation and default fallback behave consistently.
  Disabling GPS retains the site; selecting a pin turns following off; neither
  action changes the regular Forecast screen's location.
- Moving a pin within the same forecast area changes the requested coordinates.
  Cached samples disclose grid resolution; nearby pins sharing a grid cell may
  legitimately return the same model values without being relabelled as a town.
- Race tests reject late GPS callbacks and old point-query responses. Saved sites
  restore exact coordinates, and silent refreshes do not reset location mode.
- Reference tests validate events for Halifax, the example UK location, DST
  transitions, polar conditions, and Moon events absent from a calendar day.
- Cloud fractions, overlapping layers, missing data, stale runs, and differing
  cadences are rendered honestly. No missing field yields a favourable window.
- Window calculations cross midnight correctly and expose their rules; changing
  observing preferences does not reinterpret raw forecast values.
- All three clients display equivalent source values, preserve selection while
  refreshing, support accessible navigation, and clearly date cached results.
- Provider collection and derived preparation run on the server with no app open.

## Revised rollout order

1. Compact map, linked timeline, stable colours, and data-availability improvements.
2. Point forecasts and model comparison; astronomy source discovery can begin
   alongside these shared foundations.
3. Core Astronomy screen after its data gates pass, plus the previously proposed
   official warnings/storm-view workstream; neither requires completing the other.
4. Astronomy-specific seeing/transparency, broader forecast verification and
   uncertainty, then optional notifications.
5. Route/coastal/activity tools and optional astronomy extensions.

The original recommendations remain in scope as proposals. This addition makes
astronomy a named cross-platform workstream, rather than deferring it to generic
activity-planning features.
