# Golf: iPhone and server implementation

## Experience

Build 1.0 (18) adds a Golf tab to `weatheratlas-ios`. Its pin and preferences are
independent of the normal forecast location. The clean map accepts a tap or hold
at an arbitrary coordinate, without snapping to a forecast region. The location
name is optional. Map changes are committed only with **Use pin**.

Build 1.0 (19) suppresses provisional description text and introduces the
initial limited-coverage score. An unpublished numeric rain probability no longer
invalidates otherwise usable point-model temperature, wind and rainfall.

Build 1.0 (20) removes the limited-score treatment and repeated probability
caveats. An unpublished regional percentage is normal optional context, not
missing core weather. The point forecast is assessed normally against the
saved temperature, wind and precipitation-amount preferences.

**Limits** opens the same editor as Settings → Golf. Defaults: 8–30°C, sustained
wind at most 25 km/h, precipitation at most 1 mm per window, regional PoP at most
40%. Values persist on-device after Save. Gusts are displayed separately, not
silently compared against a sustained-wind limit.

The schedule sets the first day, tee time, and an explicit course time zone
(initially the device's zone). Seven days use the same local tee time. A round is
four elapsed hours, preceded by two hours and followed by one. Spring clock-gap
tee times are marked invalid; fall repeated times use the first occurrence.
Passed tee times and stale data are not scored. No extra location permission is
requested for the manual golf pin.

## Server-owned data and calculations

`GET /api/v1/golf/outlook` takes longitude, latitude, local_date, tee_time,
time_zone, days (1–7), min_temperature_c, max_temperature_c, max_wind_kmh,
max_rain_mm and max_pop_percent. The first date must be today or the next six
days in the selected zone. Limits and coordinates are validated, including
finite numbers and an ordered temperature range.

- All sampling uses already-ingested, registered local GDPS rasters. No request
  downloads weather, triggers ETL, or writes weather database records.
- One explicit recent complete model cycle is preferred while a newer cycle is
  still being ingested; otherwise the latest non-future cycle is used. No mixing
  cycles to hide missing fields. Each field is bounded to 110 samples; four reads at a time;
  50-second collection timeout and existing API rate limits.
- Temperature, sustained wind and gusts are interpolated in time only between
  present adjacent steps at most three hours apart. Explicit missing values
  break coverage. The map pin is a grid sample, not a fairway-scale prediction.
- Precipitation fields define one-/three-hour liquid-equivalent accumulation
  intervals. GDPS shared product-time rows are not field-specific accumulation
  metadata. Field, lead, cadence and units are validated using the same contract
  as the existing regional precipitation endpoint.
- Whole native precipitation intervals tile each requested window. They are
  never prorated or double counted. Unaligned windows have lower and upper
  bounds; a tolerance between those bounds cannot be assessed.
- PoP is nearby regional context, from a representative location within 50 km,
  with complete overlapping-period coverage and nonmissing published values.
  This is not a polygon membership test, point/hourly probability, or the chance
  of finishing golf. Missing PoP is never inferred from amounts or condition text.
- Raw samples are cached for five minutes independently of tolerances. Responses
  use private/no-store. Preferences are stored in the app, not a server profile;
  request parameters can still appear in normal service access logs.

## Score contract: golf-fit-v3

The score is a **weather-fit index**, not a calibrated probability or safety
assessment. The app and LLM do not calculate or override it.

Each before/round/after window checks the temperature range, peak sustained
wind, precipitation total and maximum overlapping regional PoP. A score is
withheld if temperature, sustained wind or precipitation amount/timing cannot
be checked. Unpublished regional PoP alone is excluded from scoring, never assumed
to be zero or a passed preference. Published PoP still participates and can fail
the user's limit, even if another window has no PoP. The rain-chance preference
applies only when a percentage is published. Unpublished percentages have a
`not_provided` check and a null fit, with no warning paragraph. A scored day has
`scoreCoverage: complete` under this optional-PoP contract and `probabilityNote:
null`; its state is `within` or `outside`, never `partial` solely due to PoP.
Actual core gaps still use `incomplete` and coverage `none`. The iPhone also
normalizes legacy v2 partial days for presentation without repeating the old
probability warning. Version 1 withheld every score when any PoP was absent;
version 2 introduced the now-superseded limited-score presentation.

For example, 0.5 mm in the modelled round is a precipitation amount, not an
estimated probability. The regional bulletin can independently say “Rain”
without publishing a numeric percentage. [ECCC's forecast guidance](https://www.canada.ca/en/environment-climate-change/services/types-weather-forecasts-use/public/guide/elements.html)
describes when chance percentages versus precipitation terms are used. Golf
retains null percentages and displays the regional condition and its own
time window in Round details; it never converts the amount or wording to a
fabricated percentage.

For a maximum threshold, fit = clamp(50 + 50 × (limit − value)/scale, 0, 100).
The scales are max(10, wind limit), max(2, rain limit), max(20, PoP limit).
Temperature uses the smallest headroom from either range boundary, scaled by
5°C. Zero precipitation/PoP/wind exactly meeting a zero limit receives 100.
Each window uses its lowest criterion fit. Before/round/after weights are
15/70/15%. Any during-round limit breach caps the final score at 49. Thus a high
score is not a guarantee that every buffer-period limit is met; the status and
checks accompany the number.

## On-device wording

Apple Foundation Models receives the limits, raw point model rows, native rain
intervals, overlapping regional forecast periods, source context, and server
checks. The concise paragraph combines a fixed, server-state verdict with an
on-device sentence explaining forecast weather against the preferences across the round and
before/after windows. Automatic sequential generation starts after loading;
cancelled work stops when leaving the foreground/tab. Polling unchanged data
does not regenerate a completed explanation. Queued/running/cancelled analyses
show no filler paragraph or provisional "rules-based" label. A paragraph appears
only for a completed current response, or a terminal unavailable/error/timeout
outcome with its clearly labelled server-derived fallback. Old responses and
old failure messages are not reused for changed forecast inputs.

The structured output must preserve the server score and pass prose/consistency
checks. Unsupported numbers, hazards, safety/course-opening promises, and
contradictory states are rejected. Unpublished-PoP disclaimers are rejected too,
including the reported “regional rain likelihood cannot be fully assessed”
wording. The prompt omits unknown PoP checks and legacy probability warnings;
the terminal fallback describes the actual forecast, not percentage availability.
This is a guardrail, not proof that model
wording is infallible. Unsupported devices, unavailable Apple Intelligence,
model errors or rejected output use a labelled rules-based description. No
cloud-model fallback or new permissions. Initial loading has a spinner; routine
refreshes retain the current layout and values until replacements arrive.

## Verification

Backend: `tests/test_golf.py`, existing forecast page and precipitation suites.
iOS: `GolfTests`, `GolfUITests`, existing unit suite, simulator and unsigned
generic-device Release builds. Native wording acceptance is opt-in with
`TEST_RUNNER_WEATHERATLAS_NATIVE_GOLF=1` on an explicitly selected simulator.
The loopback-only UI fixture is synthetic and is never included in the app.

Verified September 16, 2026: 65 backend tests, 165 iOS unit tests, Golf's UI flow,
three native-model fixture cases (within/outside/incomplete), two real forecast
days through the production endpoint and on-device model, and an unsigned
iPhone Release build. API service rebuilt/restarted and readiness confirmed.
No physical phone was installed or automated. Live verification can be repeated
with `TEST_RUNNER_WEATHERATLAS_LIVE_GOLF=1` and the opt-in
`GolfTests/testLiveGolfForecastAndNativeExplanation` simulator test.

September 17 build 19 regression checks: 69 backend tests, 169 passing iOS
unit/native-model tests (five unrelated opt-in tests skipped), the Golf UI flow,
and an unsigned iPhone Release build. Controlled delayed-generation tests check
that queued, running, cancelled and superseded analyses render no provisional
paragraph; failure fallback appears only after a terminal result. Live API
verification reproduced a 0.53 mm round with absent PoP and at that version returned a
limited score with an explicit unchecked rain-chance preference, not an
unscored generic missing-data verdict. The live-server/native-model test also
passed on the first two upcoming forecast days using the new partial coverage.

September 17 build 20: 69 backend tests and 170 iOS unit/native-model tests
passed (five unrelated opt-in tests skipped), with an unsigned iPhone Release
build. Tests cover 0.5 mm without PoP, normal preference-based scoring, rejection
of the reported disclaimer, legacy v2 payloads, and no premature description.
The updated, healthy production API returns `within`, 61/100 for the live
0.53 mm round with the default 1 mm limit, and `outside`, 43/100 when that limit
is 0.25 mm. Neither response has a probability warning. The percentage remains
null; the rain amount is assessed, not discarded or converted into a probability.
The Golf UI flow and live-production/native-model acceptance test also passed.
The native model described the 0.53 mm day as rainfall, temperature and wind
within the user's preferences, without an unpublished-probability caveat.

This change does not add Golf to Android or the webapp, does not alter collection
jobs, and does not infer soil drainage, course availability or lightning safety.
