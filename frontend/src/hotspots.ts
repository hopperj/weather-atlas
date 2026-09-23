import type { HotspotCollection } from './api'

export type MapBounds = [number, number, number, number]

function validBounds(bounds: MapBounds): boolean {
  return (
    bounds.every(Number.isFinite) &&
    bounds[2] > bounds[0] &&
    bounds[3] > bounds[1]
  )
}

/** Return the published hotspot extent, with a feature-derived fallback. */
export function hotspotCollectionBounds(
  collection: HotspotCollection,
): MapBounds | null {
  if (collection.bbox && validBounds(collection.bbox)) {
    return collection.bbox
  }

  const coordinates = collection.features
    .map((feature) => feature.geometry.coordinates)
    .filter(([longitude, latitude]) =>
      [longitude, latitude].every(Number.isFinite),
    )
  if (coordinates.length === 0) return null

  const longitudes = coordinates.map(([longitude]) => longitude)
  const latitudes = coordinates.map(([, latitude]) => latitude)
  let west = Math.min(...longitudes)
  let south = Math.min(...latitudes)
  let east = Math.max(...longitudes)
  let north = Math.max(...latitudes)

  // MapLibre needs a non-zero extent to frame a one-point snapshot.
  if (west === east) {
    west -= 0.1
    east += 0.1
  }
  if (south === north) {
    south -= 0.1
    north += 0.1
  }
  return [west, south, east, north]
}
