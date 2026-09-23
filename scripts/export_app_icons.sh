#!/usr/bin/env bash
# Deterministic size/format exports only; never redraw the selected artwork.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ICON_DIR="$ROOT/frontend/public/icons"
SOURCE="$ICON_DIR/crimson-sky-v1-source.png"

if ! command -v sips >/dev/null 2>&1; then
  echo "Icon export requires macOS sips. Existing exported icons are portable."
  exit 1
fi
if [[ ! -f "$SOURCE" ]]; then
  echo "Missing selected icon master: $SOURCE"
  exit 1
fi

for size in 16 32 48 96 152 167 180 192 512 1024; do
  sips --resampleHeightWidth "$size" "$size" "$SOURCE" \
    --out "$ICON_DIR/crimson-sky-v1-$size.png" >/dev/null
done
sips --setProperty format ico "$ICON_DIR/crimson-sky-v1-32.png" \
  --out "$ROOT/frontend/public/favicon.ico" >/dev/null
cp "$ICON_DIR/crimson-sky-v1-180.png" "$ROOT/frontend/public/apple-touch-icon.png"
echo "Exported Crimson Sky icons; the original master is unchanged."
