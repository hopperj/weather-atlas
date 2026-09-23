# Weather Model Atlas iOS icon

## Current icon

The user selected **Crimson Sky** on 2026-09-07. It supersedes the original
navy icon below for all active app-icon uses. See
[Crimson Sky integration and exports](app-icon-crimson-sky.md) for the current
assets, reproduction instructions, browser caching, and verification.

## Original concept (historical; no longer referenced by the app)

Created 2026-09-07 using the built-in image-generation tool, following the
imagegen skill. No CLI/API fallback or hand-drawn replacement was used.

## Asset and integration

- Asset: `frontend/public/icons/weather-model-atlas-ios.png`
- Actual output: 1254 × 1254 PNG, fully opaque. The generator returned this
  size despite the 1024 × 1024 prompt request; the original output is preserved.
- Artwork: pearl-white cloud, warm sun, teal airflow contours, midnight navy.
- Square artwork, with no baked-in rounded-corner mask or text.
- `frontend/index.html` originally registered the asset using
  `rel="apple-touch-icon"`, applying to the map and the forecast page. This was a web Home Screen
  icon integration, not a native iOS application or an App Store submission.
- Safari chooses an available larger icon when an exact device-size match is
  absent. See [Apple's Web Clip icon documentation](https://developer.apple.com/library/archive/documentation/AppleApplications/Reference/SafariWebContent/ConfiguringWebApplications/ConfiguringWebApplications.html).

To use it, open the app's local-network address in Safari on an iPhone, then
use Share → Add to Home Screen. Previously saved Home Screen shortcuts may
retain an older icon until removed and added again. No device-level installation
or cache behaviour has been tested on a physical iPhone.

Verification: the production frontend build and HTML formatting check passed.
The rebuilt frontend container reported healthy. Live `/forecast` HTML contains
the icon link and the image endpoint returns HTTP 200 with `image/png`.
The served image matches the saved asset (SHA-256
`fce7c61301d6cc882296fc50f62e4a2a7b474be0d29a19adc4d26bd314c7a33a`).

## Final generation prompt

```text
Use case: logo-brand
Asset type: iOS home-screen app icon master, 1024 x 1024 square PNG.
Primary request: Create one original, polished icon for Weather Model Atlas, a weather forecast and atmospheric-model mapping app with a dark navy and teal interface.
Scene/backdrop: Fully opaque edge-to-edge deep midnight navy (#07111d) background, with a very subtle atmospheric blue lift behind the mark. The whole canvas is the icon artwork.
Subject: One unified, immediately readable weather emblem: a sculpted pearl-white cloud with a small warm golden sun partly visible behind it, cradled by two bold, flowing teal/cyan air-current ribbons. The ribbons suggest wind circulation and weather-map contours, integrating into the cloud silhouette instead of becoming separate decorations.
Style/medium: Premium contemporary iOS icon, restrained dimensional depth, silky surfaces, crisp geometry, soft luminous edges, sophisticated and calm. Strong simple silhouette with excellent legibility at tiny home-screen sizes. Not a busy illustration.
Composition/framing: Center the emblem, occupying roughly 72 percent of the width with generous safe space. Balanced visual weight and clean negative space.
Color palette: Deep midnight navy, luminous teal and cyan, pearl white, one restrained warm golden accent.
Constraints: One finished icon only. Full square canvas with square outer corners, fully opaque, no transparency. Do not bake in an iOS rounded-corner mask. No text, initials, numbers, map labels, border, outer frame, device mockup, presentation sheet, watermarks, or unrelated objects. Do not copy an existing app logo.
```
