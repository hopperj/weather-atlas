# Map readability — 2026-09-08

Both clients now start weather overlays at **62% opacity**, retaining their
existing controls for users to change it. Weather palettes, units, values,
timestamps, filtering and server collection/processing are unchanged.

## Web

`frontend/src/mapPresentation.ts` owns the neutral geography style and wind
symbols. The paint order is:

1. Neutral land, water and subdued roads (optional legacy raster backdrop).
2. All buffered weather rasters, in the user's chosen overlay order.
3. Coastlines/lake shores and administrative boundaries, with light outlines.
4. Dark wind arrows with actual white outlines.
5. Collision-aware town/city and regional labels, dark text with white halos.

Permanent insertion anchors keep every new/prefetched frame below reference
features. Frame swaps and layer reordering use the same anchors, so animation
does not cover labels again. National boundaries and dashed provincial/state
boundaries are distinct; disputed national borders are dashed too.

The previous raster basemap baked labels into the background, and moving a new
weather frame to the top covered them. Separating reference features fixes that
without washing all the weather colours away.

Wind arrows are RGBA images, not falsely marked as signed-distance-field images.
Their dark fill and white edge are drawn into the image so both are visible.
Size still reflects speed and rotation still reflects direction. The old wind
colour ramp was removed because it no longer described the symbols; exact
weather values remain available through the existing point inspection.

## iPhone

`MapAppearance.swift` configures native Apple Maps with muted, flat styling and
excludes unrelated points of interest and traffic. The weather raster remains
at MapKit's `aboveRoads` level, **below native labels**. A thin, white-edged
reference coastline is drawn immediately above it, independently of frame swaps.
This is bundled Natural Earth 1:10 million cartographic artwork (about 10 MB),
not a runtime download or mobile ETL job. Its source, public-domain licence and
checksum are recorded in the app's `CoastlineSource.txt`. MapKit decodes the
already-prepared line geometry once for display.

The reference line fades out between map zoom levels 7.5 and 8.5: it is generalised
for regional maps, not navigation or street-level precision. Apple's detailed
coastlines, roads and administrative boundaries remain underneath the weather;
the lighter fill helps them show through at closer zoom levels. The separate
forecast-location picker is unchanged and uses only its clean native basemap.

Wind annotation images have a dark fill and white outline, increasing from
20 to 30 logical points for server speeds between 0 and 45 m/s. Larger speeds
remain capped for legibility. Missing/invalid/unsupported-unit speeds use a
neutral 24-point symbol, not an invented speed. Existing bearings, map rotation
and speed callouts are retained. Icons are cached code-drawn presentation assets.

The single-data-selection model, None option, Model/Radar/Satellite controls,
complete-frame playback and clean forecast-location picker remain intact.
App/widget build numbers are 13; signing identities and permissions are unchanged.

## Geography provider and server boundary

The web default is [OpenFreeMap](https://openfreemap.org/quick_start/), serving
OpenMapTiles-compatible vector geography and fonts. It replaces direct public
OSM raster requests and requires no account or API key. Its visible attribution
links OpenFreeMap, OpenMapTiles and OpenStreetMap. Apple Maps remains the native
iPhone basemap provider. These geography providers require internet access.

For self-hosting, frontend build-time settings are:

| Setting | Purpose/default |
| --- | --- |
| `VITE_BASEMAP_VECTOR_URL` | TileJSON; `https://tiles.openfreemap.org/planet` |
| `VITE_BASEMAP_GLYPH_URL` | Font template; `https://tiles.openfreemap.org/fonts/{fontstack}/{range}.pbf` |
| `VITE_BASEMAP_TILE_URL` | Optional legacy raster backdrop; unset by default |

Custom vectors must use the OpenMapTiles `water`, `boundary`, `transportation`
and `place` schemas. Fonts must include Noto Sans Regular. Review attribution
when changing providers; a raster override alone still uses the default vector
and font services. The Docker frontend compiles these at image build time, so
runtime environment variables alone do not change an already-built image.

Weather is still collected, transformed, stored and served entirely by the
existing server. The browser and phone only display weather responses. The local
weather endpoint stays `http://wolf359.iolan:18080`; it is not upgraded to HTTPS.
Only the frontend container needs rebuilding for this web change. No weather
ETL jobs, API services or databases require a restart or migration.

## Verification

- Web: 83 tests, production build and lint. New tests validate the vector style,
  reference-layer ordering through buffered frame swaps, opacity defaults and
  correctly drawn arrow edges.
- iOS: 146 unit tests pass, covering muted map configuration, native label/reference ordering,
  the bundled coastline and its zoom cutoff, adjustable opacity and bounded
  speed-dependent arrow images/rotation/callouts.
- Five simulator interaction/live rendering tests pass, covering single-data selection,
  Model/Radar/Satellite, None, wind, point inspection and complete-frame playback.
  No physical-phone UI automation is required.

The frontend-only container rebuild is deployed at `http://wolf359.iolan:18080`.
Signed iPhone build 1.0 (13), including the detailed coastline resource, is
installed on the connected device. Live 1242 × 2688 simulator captures were
visually checked; the previously delivered screenshot files were left unchanged.
The finer coastline asset was rechecked with all 146 unit tests and the live
capture/playback tests. An earlier live check was interrupted by a connection
loss coinciding with a gateway restart; subsequent runs passed without networking
code or permission changes.
