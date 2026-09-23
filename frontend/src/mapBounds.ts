export type MapBounds = [number, number, number, number]

// MapLibre's default Web Mercator camera cannot represent the poles. Global
// rasters often include a half-cell envelope just outside geographic bounds,
// so their scientific bounds must be normalized before they are used only for
// camera fitting.
const WEB_MERCATOR_MAX_LATITUDE = 85.051129

export function cameraBounds(bounds: MapBounds): MapBounds | null {
  if (!bounds.every(Number.isFinite)) return null

  const normalized: MapBounds = [
    Math.max(-180, Math.min(180, bounds[0])),
    Math.max(
      -WEB_MERCATOR_MAX_LATITUDE,
      Math.min(WEB_MERCATOR_MAX_LATITUDE, bounds[1]),
    ),
    Math.max(-180, Math.min(180, bounds[2])),
    Math.max(
      -WEB_MERCATOR_MAX_LATITUDE,
      Math.min(WEB_MERCATOR_MAX_LATITUDE, bounds[3]),
    ),
  ]

  return normalized[0] < normalized[2] && normalized[1] < normalized[3]
    ? normalized
    : null
}
