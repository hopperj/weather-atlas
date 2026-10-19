# Astronomy / Clear sky — total-cloud preview

Implemented on 2026-10-19. API/web deployment status is recorded in the
[release notes](release-2026-10-19.md); native changes require a new app build and
have not been distributed through either app store in this task. This is the first usable slice of the
[observing-conditions roadmap](weather-atlas-experience-roadmap.md), not completion
of its layered-cloud / seeing / transparency data gates.

## User experience

- Web: `/astronomy`, linked from Forecast and the map. First entry uses the
  selected forecast/map coordinates; subsequent visits restore the observing
  site independently. With no previous selection or seed, it uses an identified
  Halifax default.
- iOS: Astronomy / Clear sky has its own primary tab immediately after Golf,
  and can also open from Saved places or the map's point-sample panel. With six
  sections, a native More navigation menu retains Saved and Settings; Forecast
  stays first and the redundant button above its content is removed. An explicit
  Saved place or map point overrides the last observing site for that entry only.
- Android: a native Astronomy tab uses the Forecast pin/location on first entry
  and restores its own site afterward.
- All three clients support exact coordinates, a clean map picker, named saved
  sites, foreground approximate GPS, model selection, deep-sky vs lunar/planetary
  modes, cloud/wind limits, seven dated noon-to-noon sessions, night filtering,
  native-time weather tables, selected-time details, and an optional dim red view.
  Map panning alone does not select a new site. Cancel leaves the site unchanged.
  Manual selection stops GPS following; late location responses cannot move it.
- Site coordinates are not snapped to an ECCC forecast area. Sun/Moon events
  and the timezone are computed for that point. The model's actual sampled cell,
  grid spacing/CRS and footprint are separate metadata, never a replacement pin.
- Saved sites, the last selected point and observing preferences remain on the
  device/browser. They are separate from regional Forecast settings. There is
  no account, GPS movement history, background location, notification permission,
  course-booking integration, or new weather source contacted by a client.

## Shared server contract

`GET /api/v1/astronomy/forecast?latitude=44.65&longitude=-63.57`

Optional parameters: `product=gdps|rdps|hrdps`, `nights=1..7`,
`mode=deep_sky|lunar_planetary`, `max_cloud_percent=0..100` (default 30),
`max_wind_kmh=0..150` (25), `max_rain_mm=0..20` (0), and
`minimum_minutes=30..240` (60). Clients currently expose cloud/wind limits and
keep the default dry-weather/minimum-duration rules. Coordinates must be finite
and in geographic bounds; no area ID or registered observing site is required.

Schema version 1 returns requested coordinates, site timezone, model/run,
generation time, stale state, actual sample-cell metadata, method/rule/ephemeris
versions, limitations, native weather frames and dated night sessions. Sessions
include rise/set and three twilight levels, astronomical-dark and moonless-dark
intervals, qualifying windows, state and explanation. Absence of an event is
`null`, not a guessed sunrise/moonrise. Missing weather is `null`, never zero.

The endpoint reads **already registered ETL COGs** through the existing catalogue.
It does not fetch weather providers, start an Airflow DAG, or copy production
data to development. Total cloud, temperature, humidity, wind/gusts and native
precipitation totals reuse the existing deterministic ingestion. For RDPS/HRDPS,
wind magnitude can be derived from both collected u/v components; one missing
component is not calm wind. No database migration or new subscriber is needed.

One explicit model cycle is selected: prefer a recent complete cloud cycle while
a new one arrives, otherwise show the newest available cloud cycle. Runs are
not spliced. Sampling is nearest native cell, with four concurrent reads and at
most 190 frames per field, a 50-second request timeout, the existing point-query
rate limiter, and optional 120-second Redis caching keyed by exact coordinate,
model, mode, night count, criteria and a two-minute time bucket. Weather and
astronomical calculations stay on the server. A separate 120-second grid-sample
cache excludes observing criteria, so changing thresholds can reuse the same
collected point weather. Client limit changes are debounced. Responses use
private/no-store; clients refresh while visible and retain data only for matching
selections.

## Interpretation and safeguards

- Initial weather support is **total cloud only**. Low/middle/high layers,
  seeing, transparency and visibility are explicitly unavailable. The live GDPS
  listing checked on 2026-10-19 exposes TotalCloudCover and CloudWater, not a
  verified layered-cloud forecast. Cloud water must not be relabelled as cloud
  fractions; website colours are not ingested as numerical astronomy forecasts.
- A cloud percentage is sky fraction, not a probability of successful observing.
  The layer fractions, when eventually integrated, must not be added together.
  Clear skies and surface winds do not establish good astronomical seeing.
- Native valid times stay native, including three-hourly later forecasts. The
  clients do not invent hourly values or seven nights of weather coverage.
  Sun/Moon events remain available when the chosen model horizon or coverage ends.
- Precipitation is a complete native accumulation **ending** at a displayed time.
  Its start is supplied in details; a three-hour total is not divided into three
  invented hourly amounts. Window checks use conservative complete-interval
  bounds from the existing precipitation planner.
- A window must satisfy the worse adjacent present cloud and wind values across
  a gap of no more than three hours, complete precipitation coverage, freshness
  (run at most 24 hours old), the chosen limits and minimum duration. Missing
  inputs or unobserved horizon gaps cannot create a favourable window.
- Deep-sky mode requires the Sun below −18° and Moon centre below the geometric
  horizon. Lunar/planetary mode permits moonlight and uses Sun below −6°. The
  window is explainable planning guidance, not a success score or guarantee.
- Solar/lunar calculations use pinned Astronomy Engine 2.1.19, a sea-level
  observer and unobstructed horizon. Rise/set includes its standard refraction
  and upper-limb convention; twilight and dark intervals use airless altitude.
  Moon-centre geometric horizon crossing therefore differs from apparent moonset.
  Local trees, hills, buildings and equipment temperature are not modelled.
- Dew point uses the Magnus surface approximation. A temperature/dew-point
  spread ≤2°C is only a labelled dew-risk heuristic, not measured optics cooling.
- Timezones use pinned tzfpy 2.1.1 geographic boundaries. Its simplified borders
  are approximate; dates are formatted in the returned IANA zone and DST nights
  may contain 23 or 25 hours. No-rise/set and polar-darkness cases are supported.

## Development verification

New server tests cover exact site timezones and event ordering/altitude,
cross-midnight sessions, polar and 25-hour DST nights, native three-hour steps,
missing/stale/out-of-horizon weather, conservative cloud limits, null rain,
regional vector wind, actual raster-cell coordinates/footprints and finite API
bounds. Existing catalogue, rate-limit, Forecast and Golf regressions are rerun.

Web tests exercise the typed contract, null values, exact site requests, saved
sites, cancellation, and clearing old windows after changed criteria. Local
headless-browser checks cover desktop and 390px layouts, map/coordinate selection,
save/reload and Escape dismissal, with no page errors or horizontal document
overflow. Screenshots use explicitly synthetic weather, not production claims.

iOS adds persistence/server-isolation/null-contract tests and a local-fixture
interface test for entry, observing results and the clean coordinate picker.
Android adds exact-coordinate/same-server and mismatched-response tests. Release
builds are unsigned and were not installed on a phone or submitted to a store.

Verified: 65 focused server/API regressions passed (nine new astronomy tests);
all 157 web tests plus lint and the production web build passed; all 222 iOS
unit tests passed (seven opt-in checks skipped), the astronomy interface test
passed and was visually reviewed, and the unsigned iOS Release build passed as
1.3 (26). Android's 60 unit tests, Debug/unsigned minified Release builds and
lint passed. Android was not visually verified on a device/emulator in this task.

Navigation revision (2026-10-19): the iOS bar is Forecast, Map, Golf, Astronomy,
More. Saved and Settings share a single More navigation stack without duplicate
back buttons; the old Forecast Astronomy button is removed. Eight navigation/Golf
interface regressions passed, followed by four focused reruns after consolidating
the More stack. The unsigned Release build and formatting/diff checks passed.
Astronomy is created lazily and only refreshes/listens for GPS while visible.

## Release and remaining work

1. On an explicitly authorized deployment, build/restart the **API and frontend**
   on sparky. The API image installs the two pinned dependencies from pyproject;
   the lockfile also records them for development. The existing SPA configuration
   already serves `/astronomy`. No database migration or collector restart is
   required for the preview. Verify registered cloud/rain/wind coverage and a real
   point response for each model before declaring production readiness.
2. Distribute new iOS/Android builds after that API is available. Existing released
   clients are unaffected by the additive endpoint; a new client against an old
   server shows an unavailable/error state, not fabricated observing conditions.
3. Complete the original data gates: verify/licence supported numerical layered
   cloud, seeing and transparency feeds; add bounded scheduled ETL and quality
   checks; validate definitions, units, cadence, coverage and storage cost. Do not
   market this preview as completion of those products.
4. Further rollout QA: real devices/TalkBack/VoiceOver, large text, denied/stale
   GPS, polar locations, real NAS-backed sample latency and observing feedback on
   thresholds. Alerts, target planning and light-pollution products remain later
   optional work, as in the roadmap.

References: [ECCC GDPS data](https://eccc-msc.github.io/open-data/msc-data/nwp_gdps/readme_gdps-datamart_en/),
[Astronomy Engine API and MIT licence](https://github.com/cosinekitty/astronomy),
[tzfpy API, boundary accuracy and licence notices](https://github.com/ringsaturn/tzfpy).
Astronomy Engine and tzfpy are server dependencies, not code bundled in the phone
apps. Preserve their upstream MIT notices and tzfpy's timezone-boundary dataset
acknowledgements/licensing when distributing the server image.
