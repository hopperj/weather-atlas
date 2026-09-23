# Selected app icon — Crimson Sky

Date: 2026-09-07. The user selected the red-and-white maple leaf, cloud, and
airflow artwork from the Canadian icon concepts (option 04, Crimson Sky).
This change integrates that exact artwork; it does not generate, redraw,
recolor, or crop a new logo. The application name remains Weather Model Atlas.

## Source and exports

The selected master is preserved byte-for-byte at
`frontend/public/icons/crimson-sky-v1-source.png` (1254 × 1254, opaque PNG).
Its SHA-256 is
`63033f7cc811c4c51bcf32aafa7c71bca53391d2f663b415193365ee6da0c285`.
It was supplied as
`exec-bf70c73f-4c7e-4a9b-8fb0-fd981e0f0093.png` and is also preserved among
the historical concepts at `docs/assets/ios-icon-maple-flow-variants/04-crimson-sky.png`.

![Selected artwork](../frontend/public/icons/crimson-sky-v1-180.png)

All numbered exports use the prefix
`frontend/public/icons/crimson-sky-v1-`:

| Export | Use |
| --- | --- |
| `16.png`, `32.png`, `48.png` | Browser favicon PNG alternatives |
| `96.png` | Shared icon in both page headers, displayed at 36 CSS pixels |
| `152.png`, `167.png`, `180.png` | iPad and iPhone Home Screen icons |
| `192.png`, `512.png` | Web app manifest icons |
| `1024.png` | High-resolution export also used by the native iOS app |
| `source.png` | Unmodified selected master |

Conventional discovery paths are also supplied:
`frontend/public/favicon.ico` is a 32-pixel ICO, and
`frontend/public/apple-touch-icon.png` is an exact copy of the 180-pixel PNG.
The assets remain square and opaque; rounded corners in the website header
are presentation-only CSS.

To reproduce the exports on macOS, run from the repository root:

```sh
bash scripts/export_app_icons.sh
```

The script uses macOS `sips` for deterministic resizing/format conversion.
The exported files are included in the frontend's public assets; Linux/Docker
builds do not need `sips` or an image-generation service. A future change of
artwork should use a new versioned basename and update the metadata, header
component, and regression-test checksum together.

## Integration and scope

- `frontend/index.html` registers the favicon variants, size-specific
  `apple-touch-icon` links, an Apple Home Screen title, and `site.webmanifest`.
  Both `/` and `/forecast` use this shared HTML entry point.
- `frontend/public/site.webmanifest` declares 192- and 512-pixel icons with
  `purpose: "any"`. There is no maskable claim, new service worker, offline
  support, or change to launch destination/display behavior.
- `frontend/src/AppIcon.tsx` provides the same decorative header image to both
  pages. The map icon still toggles layer controls; the forecast brand remains
  a named link to the map. Empty alternative text avoids duplicating the
  containing button/link's accessible name.
- Weather-condition symbols, map controls, and scientific data markers are
  functional symbols, not app branding, and remain unchanged.
- The old navy master and previous concept documents are retained as history
  but are not referenced by active HTML or React components.

This `weatherapp` project is a web application; its Apple icon links configure
Safari Home Screen/Web Clip icons, not a native application. The separate
native client is in the sibling `weatheratlas-ios` folder. Once the user
identified that project, the same 1024-pixel export was copied into its
`WeatherAtlas/Resources/Assets.xcassets/AppIcon.appiconset`, included in the
target's Resources phase, and selected as `AppIcon` for Debug and Release.
See [the native app README](../../weatheratlas-ios/README.md). The phone must
receive a newly built native app for that change to appear; refreshing this
website does not replace a native app's icon.

The Home Screen mechanism and size selection follow
[Apple's Web Clip documentation](https://developer.apple.com/library/archive/documentation/AppleApplications/Reference/SafariWebContent/ConfiguringWebApplications/ConfiguringWebApplications.html).
The manifest icon metadata follows the
[web app manifest icons reference](https://developer.mozilla.org/en-US/docs/Web/Progressive_web_apps/Manifest/Reference/icons).

## Caching and use

Versioned PNG filenames work with the existing one-year immutable static
cache policy. The conventional `/favicon.ico`, `/apple-touch-icon.png`, and
`/site.webmanifest` paths instead use a one-hour cache with revalidation.
The HTML links to the ICO and manifest also carry `?v=crimson-sky-v1`.
The manifest is served as `application/manifest+json`.

Refresh the website to load the new header and metadata. On an iPhone, open
the app's local-network address in Safari and choose Share → Add to Home
Screen. An existing Home Screen shortcut may retain its older icon; removing
and adding the shortcut again may be necessary. Physical iPhone installation
and OS-level icon caching have not been tested.

## Verification

Regression coverage in `frontend/src/AppIcon.test.tsx` checks the exact source
hash, PNG dimensions, discovery assets, HTML metadata, manifest references,
and decorative-image accessibility. Page tests additionally check that the
map's layer toggle still opens/closes and the forecast brand still links to
the map using the same icon.

`@types/node` is a development-only dependency used to type-check the asset
tests' filesystem and checksum imports; it adds no browser runtime dependency.

Run the checks with:

```sh
bash -n scripts/export_app_icons.sh
npm --prefix frontend test
npm --prefix frontend run lint
npm --prefix frontend run build
```

Only the frontend service needs rebuilding/restarting for this change. The
forecast services, data pipelines, stored weather data, and FLEXPART system
are unchanged.

Verified on 2026-09-07:

- 77 frontend tests passed across 14 files, including 17 added icon and header
  checks. Lint, formatting checks, script syntax, local production build, and
  Docker frontend build passed.
- The deployed frontend container is healthy and its Nginx configuration
  passes validation.
- Live `/` and `/forecast` responses contain the new metadata. The ICO, Apple
  discovery icon, manifest, and all ten numbered PNG exports return HTTP 200
  and match their checked local files byte-for-byte. MIME types and cache
  headers match the policies above.
- Both headers display the selected icon in the in-app browser at desktop
  and 390-pixel phone widths. The phone-width map icon closes and reopens the
  layer panel; the forecast navigation remains usable. This is responsive
  browser verification, not testing on a physical iPhone or iPad.

Separate maintenance note: the dependency audit reports six transitive
findings (five high, one moderate: `brace-expansion`, `browserslist`,
`js-yaml`, `nanoid`, `postcss`, and `undici`). No automatic audit fix or
unrelated dependency upgrade was applied as part of the icon integration.
