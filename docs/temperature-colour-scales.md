# Automatic temperature colour scales

Implemented 2026-09-07 for the web map and the separate `weatheratlas-ios`
native client. This changes display styling, not the weather values, point
samples, daily/hourly forecasts, or scientific model inputs/outputs.

## Range rule

For the selected air-temperature field, model run, domain, and valid time, use
the processed raster's stored valid-data minimum and maximum. These are already
registered by ingestion in `catalogue.asset.minimum_value` and `maximum_value`.
No new raster scan or weather download is required during playback.

Round the lower bound down and the upper bound up to multiples of 5°C:

```text
lower = 5 × floor(data_minimum / 5)
upper = 5 × ceil(data_maximum / 5)
```

Examples: 3.3–22.1°C → 0–25°C; −18.8–−3.3°C → −20–0°C. Already rounded
endpoints are retained. A constant field on an exact boundary, such as 5–5°C,
uses 5–10°C so the colour range is never zero-width. Missing, nonfinite, or
reversed statistics fall back to the field's configured display range.

The range covers the **whole selected raster**, not the current screen extent.
Panning and zooming therefore do not change the meaning of a colour. Each
forecast frame has its own range; it changes when rounded extrema cross a
5-degree boundary. Consult the displayed legend during animation. This is not
a percentile stretch, local-area statistic, or fixed seasonal scale.

## Palette and cross-platform consistency

Changing endpoint labels alone would not improve contrast: the old palette
anchors were fixed to absolute temperatures. For air temperature, the server
now also maps the full colour ramp onto the chosen range. An original anchor
`p` in a palette running from `a` to `b` maps to:

```text
new_anchor = lower + (p − a) / (b − a) × (upper − lower)
```

Colour order and relative anchor spacing remain unchanged. Old numeric anchor
labels are cleared because they no longer describe the shifted values. A blue
colour means the cold end of the current range, not necessarily below freezing.
Actual data are not rounded, clipped out of the dataset, or otherwise modified.

The shared implementation is `python/weather_common/display_scales.py`.
The layer resolver uses it for the legend, and the tile renderer uses the same
transformation for pixels. The signed layer token binds both endpoints and
`palette_mode="relative"`, giving this style a separate tile cache key.
Existing tokens without the new field retain their original absolute palette
mapping. Non-temperature variables keep their existing palettes and defaults.

Both clients consume `/api/v1/layers/resolve` without duplicating range selection:

- The web editor, colour swatch, cutoff slider, and legend show the resolved
  bounds. Manual scale overrides still take priority and can use arbitrary
  values; Reset colour scale restores automatic bounds. Existing explicit
  transparency cutoffs remain user-controlled.
- The native map displays the returned endpoints and positions its gradient
  stops using their actual numeric values rather than equal spacing. The
  colour range is identified as automatic in both clients.

## Deployment and verification

No database migration or ETL restart is needed. Rebuild `weather-api`,
`tile-api`, and `frontend`; update the tile service first so it understands
the signed palette mode before the API starts issuing relative-style tokens.
Then update the API and frontend. Refresh the web page; build and Run the
native project in Xcode to install its updated legend display on the phone.

Regression coverage includes:

- Positive/negative/exact-boundary/constant temperatures and invalid statistics.
- API automatic bounds, preserved explicit overrides, and unchanged styling
  for non-temperature variables.
- Identical transformed legend/tile colour ramps with uneven anchor spacing.
- Signed palette mode, distinct cache keys, and old-token compatibility.
- Web editor/reset behavior and the native legend's server-provided positions.

The existing forecast, sampling, SQL, raster ingestion, and tile-security checks
are also included in the verification run. Native UI automation is not required
to calculate the range: all weather-range decisions remain on the server.

Verified on 2026-09-07: 115 targeted server tests, all 78 web tests, and all 44
native unit tests passed. Web lint/build and the native simulator and unsigned
Release device builds passed. The API, tile service, and frontend containers
are healthy after deployment. Physical-phone installation remains a user step.

Live API responses were checked against the stored extrema and signed tokens
for `air_temperature_2m` at valid time 2026-09-07 18:00 UTC. Each returned PNG
tile rendered successfully:

| Product | Raster minimum / maximum (°C) | Automatic scale (°C) |
| --- | --- | --- |
| HRDPS | −17.503 / 35.391 | −20 / 40 |
| RDPS | −15.858 / 40.067 | −20 / 45 |
| GDPS | −73.86 / 45.989 | −75 / 50 |

The web map visually displayed the revised HRDPS colours, −20/40 controls and
legend, and the automatic-scale note. Its next buffered frame advanced to
19:00 UTC without losing the matching scale. At the metadata audit snapshot,
all 3,912 GDPS, 2,745 HRDPS, and 4,819 RDPS available temperature rasters had
usable minimum/maximum pairs; these counts grow as normal ingestion continues.
