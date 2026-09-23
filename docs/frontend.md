# Frontend

The browser application is React/TypeScript built by Vite. MapLibre is loaded as
an asynchronous vendor chunk after the application shell, keeping initial UI
code separate from the WebGL renderer.

## Data and state

TanStack Query owns remote catalogue, run, field, timeline, layer, and sample
responses. Zustand owns transient selections only:

```text
product / domain / valid-time range / active valid time
up to three selected fields
visibility / opacity / colour range
playback state and speed
```

Changing a product clears dependent time/layer selections. The UI chooses
only API-returned products and fields; it has no hard-coded weather-variable
inventory or legend values.

## Animation

The timeline advances through the server's available valid times rather than an
assumed hourly sequence or a single model run. For each valid time, the server
selects the available frame with the shortest forecast lead. The active frame
therefore carries its own run time and can cross model-run boundaries without a
gap or duplicate valid time.

The default window starts at the closest available valid time at or before now
and ends 24 hours later, capped at the latest available frame. UTC start/end
controls and a past-seven-days shortcut allow historical playback. For every
visible layer, the client resolves and prefetches the next two frames using each
frame's selected run. When a token changes, MapLibre mounts the next raster
source at zero opacity, waits for source data, cross-fades it over the previous
frame, then removes the old layer. This bounds active GPU sources while avoiding
a blank flash between frames.

Playback supports step forward/back, looping, and 0.5/1/2/4 frames per second.
Forecast lead and analysis interval labels remain distinct.

## Layer controls

Each of the three possible layers has:

- a catalogue-backed field/level selector;
- visibility and opacity controls;
- a canonical-unit cutoff that makes lower raster values fully transparent;
- optional minimum/maximum colour scale overrides;
- explicit layer reordering;
- removal from the stack.

Scale overrides are passed to the API and signed into the layer token; the
browser never sends an arbitrary raster expression. The opacity cutoff is also
signed and applied by the renderer before MapLibre applies the whole-layer
opacity. Legends always come from the resolved server style and range.

Clicking the map places one marker and requests values for visible fields in one
sample request. Results include the run and valid time context already shown by
the timeline.

## Official seven-day forecast view

The map header also links to the dedicated **Daily & hourly forecast** page at
`/forecast`. Nova Scotia regions are directly selectable in the first dropdown;
**Other province or territory…** reveals a province/territory selector followed
by that province/territory's regions. Both the seven-day outlook and all 72
hourly forecast slots update for the selected location. All locations use
explicitly labelled Atlantic times (not each location's local time) and explicit
missing-data indicators. The page is scrollable independently of the map's
fixed-height layout. See [the forecast page guide](forecast-page-2026-09-06.md).

The **7-day forecast** view is separate from scientific raster overlays. It
removes all colour contours and wind arrows, initially frames Nova Scotia, and
sets MapLibre's maximum zoom to level 6 so a user cannot zoom closer than
approximately a whole-province view. Returning to **Map overlays** restores the
normal maximum zoom.

The view requests only ECCC Nova Scotia forecast regions so labels from New
Brunswick, Prince Edward Island, and Newfoundland cannot obscure Nova Scotia
at that zoom. The regional labels are packed into collision-free map callouts
with leader lines back to their source coordinates. Each visible official ECCC
forecast region is represented by a compact label containing:

```text
Temp:          °C
Hum:           %
POP:           %
Precip Amount: mm or cm
```

Temperature is the ECCC period high or low, humidity is the forecast relative
humidity, and POP is the official probability of precipitation. Precipitation
amount is shown only when ECCC issues a numeric amount; `—` means no amount was
issued, not zero. The half-day footer steps through the common forecast horizon
without requesting or rendering a raster.

## Interactive FLEXPART runs

The smoke-run builder submits bounded, research-only CFFEPS/FLEXPART jobs when
`SIMULATION_WRITES_ENABLED=true`. Interactive runs may use the
`validation_only` emissions-factor registry while its independent review is
pending, but the run is prominently labelled with that warning. Operational
runs remain blocked until the registry is independently approved.

Completed runs publish their Cloud-Optimized GeoTIFF outputs into the
`flexpart_smoke` catalogue. Choosing **View results on map** pins the timeline to
that exact run and exposes its PM2.5, CO, black-carbon, deposition, column, and
injection-height fields. Choosing **Now**, **Past 7 days**, or a custom date
range leaves the pinned run and returns to the catalogue's best-available frame
selection.

## Basemap and attribution

The map uses a neutral OpenFreeMap/OpenMapTiles vector basemap with separate
shoreline, border and place-label layers above the weather. Attribution for
OpenFreeMap, OpenMapTiles, OpenStreetMap and ECCC remains visible. Weather
defaults to 62% opacity; the opacity control remains adjustable.

For self-hosted geography, set `VITE_BASEMAP_VECTOR_URL` (an OpenMapTiles-compatible
TileJSON URL) and `VITE_BASEMAP_GLYPH_URL` (including `{fontstack}/{range}`) at
frontend build time. The glyph service must include Noto Sans Regular. The optional
legacy `VITE_BASEMAP_TILE_URL` now supplies only a muted raster backdrop; it does
not replace the vector reference layers. Provider attribution must be kept accurate
when changing providers. See [map readability](map-readability.md) for layering,
wind styling, server boundaries and verification.

## Commands

```bash
npm --prefix frontend ci
npm --prefix frontend run lint
npm --prefix frontend run test
npm --prefix frontend run build
```

The production image serves immutable hashed JS/CSS assets through Nginx and
falls back to `index.html` for client-side routes.
