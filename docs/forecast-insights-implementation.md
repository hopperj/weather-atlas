# Forecast changes, stations, and widgets — implementation

## September 13, 2026: on-device important-change paragraphs (iPhone build 17)

The iPhone now opts into `include_forecasts=true` on the changes endpoint. This
adds a `bulletins` object with `state`, `current`, `previous`, `assessment`, and
`importantFacts`. The two source bulletins come from the existing ETL-owned
`catalogue.forecast_revision` history; the API reads at most 24 revisions and
returns at most 16 periods per bulletin. It skips duplicate metadata deliveries
and refuses comparisons across changed coordinates. There is no client-triggered
ingestion, database migration, or new upstream dependency.

The API computes a bounded relevance check on those stored facts: matched
day/night intervals, changed conditions, temperature changes ≥3°C, PoP changes
≥30 percentage points, and comparable amount changes ≥5 mm/2 cm and ≥25%.
The model may omit condition rewording. Unknowns remain unknown, amount ranges
and units are retained, and expired/new periods are not compared. Responses
without candidates are labeled `no_important_changes`; insufficient comparable
data is `incomplete`, not “unchanged.” The history/assessment participates in the
ETag independently of the scheduled numeric comparison record. Existing web
and Android response shapes are unchanged unless those clients explicitly opt in.

The iPhone gives both bulletins and candidate facts to Apple's local model,
validates the short paragraph, and retains the normal availability/retry path.
A no-candidate result uses a plainly labeled no-important-change sentence without
asking the model to embellish it. See the [iPhone implementation notes](../../weatheratlas-ios/docs/on-device-forecast-changes.md).

The weather API alone was rebuilt/relaunched and is healthy. A live read from
`https://weatheratlas.ioresearch.ca` returned the Halifax September 13 14:00Z
and 08:00Z bulletins, `ready`, `stale: false`, and `no_important_changes`.
The focused backend suite passed 73 tests; the opt-in database integration test
was skipped. The notes below describe earlier releases and their original LAN
deployment, not the current public endpoint.

## Original rollout

Implemented and deployed 2026-09-07 (Halifax local time; deployment checks continued on 2026-09-08 UTC). iOS version 1.0, build 4 is installed on the connected iPhone. Physical Home/Lock Screen widget rendering, permission, and suspended-app refresh verification remains a user-assisted acceptance check; it has not been claimed as passed.

### Build 7 locality metadata update — 2026-09-08 UTC

The city forecast ETL now preserves an official covered city/site name as optional `locality` metadata. It prefers a locality explicitly named in the region title, with validated service-town preferences for several ambiguous Nova Scotia counties and a deterministic official-site fallback. Region `name`, IDs, coordinates, coverage and source bulletin selection are unchanged. The regional/nearest API and prepared widget payload expose `locality`; old snapshots without it remain readable. The iPhone uses the town label, for example Halifax, while retaining full region titles for search. Actual observation station identities are not renamed.

The weather API and all four Airflow runtime services were rebuilt/relaunched, between active jobs. `eccc_city_forecasts_ingest` manual run `2026-09-08T02:33:45.684423+00:00` and `weather_forecast_prepare` manual run `2026-09-08T02:34:41.027774+00:00` both succeeded. Live regional and widget requests return `locality: Halifax`; the API and Airflow services report healthy. All 44 focused city ingestion, forecast API and forecast-insights tests passed. No database migration or destructive data operation was needed. Collection remains entirely server-owned; automatic on-device narrative wording in iOS build 7 does not collect or calculate weather.

The same release subsequently adds optional `briefing` metadata to the normalized city snapshot and regional API. ETL prepares three short source-backed facts: the sky pattern, possible/expected precipitation timing, and daytime/overnight temperature ranges. Missing values are excluded, zero is retained, and the metadata expires at the next covered period boundary. API reads never trigger preparation. The native summary uses these facts and falls back to the server paragraph if generation alters the precipitation/temperature sentences. This avoids delegating weather calculations to the phone. The extended focused backend suite passes all 46 tests. The city ingestion run `2026-09-08T02:59:29.736125+00:00` published the new Halifax briefing successfully; temperature ranges are 18–21°C for daytime highs and 9–14°C for overnight lows in the checked bulletin.

## Delivered

- **What changed?** An expandable Forecast section with server-generated, source-separated highlights, prior/current issue times, matching-period coverage, and detailed old/new values. No previous bulletin is fabricated: a single version displays “Building forecast history.”
- **Nearby observations.** Three nearby stations on Forecast; a standalone Weather stations map selection with temperature, wind, gusts, precipitation, humidity, and pressure; station detail and a 48-hour point chart. Model/Radar/Satellite tabs remain in place. Missing and rejected values are not zero, trace precipitation is explicit, and stale reports retain their actual observation time.
- **Widgets.** Small and medium Home Screen widgets plus inline, circular, and rectangular Lock Screen variants. Configurable app default, last foreground app location, or a saved location. Forecast-only values, dated hourly timelines, offline shared cache, expiry states, and same-server deep links that do not change the saved default. No background GPS.

The address remains **http://wolf359.iolan:18080**. No public hosting, HTTPS conversion, push service, or new third-party weather service was added. All upstream collection, normalization, comparisons, and widget weather selection are server-side. New feature endpoints only read prepared or indexed database records.

## Initial coverage and limits

- Official regional bulletin history and widget daily ranges: the current 641-region ECCC catalogue.
- Explicit-run GDPS point preparation: 83 configured Atlantic regions in NS, NB, PE, and NL, capped at 128 regions. `config/forecast_insights.json` controls provinces, maximum regions, and highlight thresholds. Regions outside model preparation can have a daily range without an invented hourly/current temperature.
- Stations: 12 allowlisted Atlantic land stations in `config/stations.json`: CAAW, CABB, CABR, CACP, CACQ, CADN, CYHZ, CWSS, CYYG, CYFC, CYQM, CYYT. These are an initial rollout, not Canada-wide observation coverage. Update both this file and the explicit Sarracenia allowlist before expanding, then rebuild the subscriber.
- Station recovery scans current/relevant previous-day directories with up to six recent hourly reports per date/station; minute streams are excluded. Metadata catalogue retrieval is daily. Reports are capped at 256 KiB, inbox processing at 500 files per run, and collection requires at least 1 GiB free storage.
- Station map requests return at most 500 rows/page, with an offset cap of 1,500 and a 2,000-candidate bound. The app stops at 1,000 markers. Nearby requests return at most five within 100 km by default (maximum radius 200 km). History requests are capped at 48 hours/3,000 reports. Spatial predicates support antimeridian crossing.
- Forecast preparation loads the last three visible GDPS runs within 36 hours and at most 1,500 assets. It samples each raster across all configured points. A model revision needs at least 60 temperature hours before becoming eligible; comparisons use matching valid times from distinct explicit runs, not an advancing mixed-run window.
- The existing hourly endpoint uses the prepared result when its region coordinates, current whole-hour start, expiry, and minimum coverage match. The previous server-side hourly path remains the compatibility fallback elsewhere and while preparation catches up at the hour boundary. No client-triggered ETL was introduced.

## Operation

| Airflow job | Schedule (UTC) | Purpose |
| --- | --- | --- |
| `weather_forecast_prepare` | Every 15 minutes | Archive/import bulletins, batch-sample retained runs, publish hourly/comparison/widget records |
| `weather_stations_ingest` | Every 5 minutes | Consume allowlisted hourly reports and bounded Datamart recovery; publish observations |
| `weather_insights_retention` | Daily 05:27 | Bound new feature archives/history; preserve latest rows for stale display |

All three jobs are enabled. Collection/preparation succeeded with no clients open. Latest explicitly checked runs completed in about 16 seconds for forecast preparation and 7 seconds for stations; station collection reported 131 accepted report deliveries and zero rejected reports. Acceptance counts include repeated deliveries; database uniqueness prevents duplicate observations. AMQP reception of new hourly reports was separately verified.

Prepared comparisons expire after an hour without preparation. Widgets expire at the earliest relevant source-age/horizon bound (normally at most 24 hours from bulletin/model issue), even if the server is unreachable. Station freshness uses twice the report's declared cadence plus 15 minutes, with a conservative hourly default when cadence metadata is absent. Quality/provenance/measurement intervals remain available in stored payloads.

Retention applies only to newly introduced feature data:

- Raw content-addressed station and historical bulletin archives: seven days.
- Normalized historical bulletin files and database forecast/observation revisions: 30 days, preserving the latest database revision of a stopped source/station.
- At most 5,000 archive files and 5,000 rows per database category per maintenance call. Symlinks and paths outside the exact archive roots are excluded. Existing models, imagery, latest bulletin files, and original data are not cleanup targets. Small station metadata revisions and the subscriber inbox are not deleted by this job.

The dry-run found zero eligible files/rows, so no material data was deleted during deployment. Early storage checks showed approximately 1.6 MiB forecast history, 2.3 MiB prepared records, and under 1 MiB station data, with about 2.8 TiB available on the data volume. These are rollout measurements, not long-term capacity guarantees. Check job success/durations, station `processed/eccc/stations/status.json`, freshest observation time, comparison readiness, queue lag, and storage before increasing coverage.

Safe maintenance inspection:

```sh
docker compose exec -T airflow-scheduler python -c 'from weather_ingest.insight_retention import maintain_insights; from weather_common.settings import Settings; print(maintain_insights(Settings.from_environment()))'
```

This defaults to dry-run. Applying retention requires explicitly passing `dry_run=False`; the scheduled maintenance job does so.

## API contracts

- `GET /api/v1/forecast/changes?area_id=<16-hex-id>&baseline=previous`
- `GET /api/v1/widgets/forecast?area_id=<16-hex-id>`
- `GET /api/v1/observations/stations?bbox=west,south,east,north&field=temperatureC&limit=200&offset=0`
- `GET /api/v1/observations/nearby?latitude=…&longitude=…&radius=100&field=temperatureC`
- `GET /api/v1/observations/stations/<id>`
- `GET /api/v1/observations/stations/<id>/history?field=temperatureC&start=<ISO8601>&end=<ISO8601>`

Changes/widget records include content/schema identity, original source times, generation time, and freshness. Weak ETags are stable across generation-only polling and change at expiry. Station payloads include public metadata, source attribution, observed/expiry times, quality flags, original units and accumulation intervals. Optional unavailable/missing preparation returns 404/503 without disabling the main app forecast. All queries are parameterized SQL files; no schema creation happens at API startup.

Coordinate query fields and Referer headers are removed from new reverse-proxy access logs; existing logs were not rewritten. API timing logs use endpoint paths only, never precise location queries. No device-coordinate history table was introduced. Station coordinates are public metadata.

## Database and deployment

Applied explicitly and verified against the database migration ledger:

- `0028_forecast_history_and_stations.sql` — SHA-256 `3d79f0e97abe7d09c08b47934543de7b0ed1392753e6352f1be155a36a14fa81`.
- `0029_insight_retention_and_map_index.sql` — SHA-256 `a42d86611dcca4b4cd1401d3402c53e79f8b01a4cc3ef925eb43b5f7c291f094`.

The API role only receives SELECT access to the new tables; the ingestion role owns preparation and bounded maintenance privileges. Migration tests include a rollback-only live-database check of deduplication, correction ordering, geography queries, and role permissions.

A verified custom-format pre-migration backup is at `/Volumes/BigMrStorage/weatherapp_data/backups/postgres/weather-before-insights-20260908.dump` (281 TOC entries). The ordinary backup command encountered a pre-existing backup-role permission error on `model_build_id_seq`; an explicit local PostgreSQL-admin backup was used instead without changing that role. Repair of the ordinary backup role remains separate work.

The API, Airflow API/scheduler/DAG processor/triggerer, subscriber, and reverse proxy were rebuilt or restarted as required. Airflow components were restarted between active jobs; unrelated services were preserved.

To disable a feature's collection while investigating, pause only its named DAG. To disable the UI rollout, use the previous app build; optional endpoint failures do not replace the core forecast. A server-code rollback must retain migrations and collected history. Do not drop tables or delete archives as a rollback shortcut.

## iPhone integration and verification

App identity remains `com.ior.weatheratlas`, signing team `QYPZ33246P`. The new extension is `com.ior.weatheratlas.widgets`; both share `group.com.ior.weatheratlas`. `project.yml` was reconciled with the actual app identity before regenerating the project. The app has the local-network usage description; both targets retain the scoped HTTP exception for `wolf359.iolan`.

Widget settings contain public forecast-region IDs/names and the configured server, not GPS history. Cache files are bounded, per-server/per-region, atomically coordinated across processes, protected until first device unlock, and reject older responses. No daily/hourly weather totals are computed in the extension. iOS decides refresh scheduling; the requested 45-minute interval is advisory. Off the LAN, widgets retain dated usable forecasts and expire them honestly.

Verified:

- 94 focused backend tests passed; the default suite intentionally skips the opt-in database case.
- The opt-in rollback-only live PostgreSQL test passed separately.
- 105 iOS unit tests passed.
- Five focused UI/regression scenarios passed: forecast changes/nearby detail, station map tab roundtrip, silent daily/hourly refresh layout, hourly header plot selection, and existing map navigation. The two new feature scenarios were rerun against the final app sources.
- Signed device build and installation of version 1.0 (4) succeeded with the widget extension and App Group. The existing interface-orientation warning remains unrelated.
- Real HTTP changes/widgets/stations and a complete 72-hour Halifax prepared forecast returned successfully. All 12 initial stations had fresh observations. Source/provider retrieval occurs in ETL, not new API reads.
- Example warm LAN reads completed in 12 ms for changes (2.4 kB), 8 ms for widgets (16.5 kB), and 9 ms for nearby stations (6.8 kB). These are single-request smoke measurements, not load-test or service-level guarantees.

Still requires physical-device acceptance: add each widget family, verify chosen/default/saved location, tap-through, larger text/tint/privacy, first setup/denied local permission, Wi-Fi changes/offline expiry, and a refresh while the main app is suspended. The phone was locked during the attempted automated launch, so no unlock was attempted. Open Weather Atlas once, then add **Weather Atlas Forecast** to the Home Screen to begin this check.

Primary references: [ECCC SWOB-ML](https://eccc-msc.github.io/open-data/msc-data/obs_station/readme_obs_insitu_swobdatamart_en/), [SWOB product guide](https://collaboration.cmc.ec.gc.ca/cmc/cmos/public_doc/msc-data/obs_station/SWOB-ML_Product_User_Guide_e.pdf), [Apple widget refresh](https://developer.apple.com/documentation/widgetkit/keeping-a-widget-up-to-date/), [local-network privacy](https://developer.apple.com/documentation/technotes/tn3179-understanding-local-network-privacy), [App Groups](https://developer.apple.com/documentation/xcode/configuring-app-groups).
