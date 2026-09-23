import type {
  ExpressionSpecification,
  Map,
  StyleSpecification,
  SymbolLayerSpecification,
} from 'maplibre-gl'

export const WEATHER_OPACITY = 0.62
// Permanent insertion points: buffered frames must never cover reference features.
export const WEATHER_REFERENCE_ANCHOR = 'weather-reference-anchor'
export const MAP_LABEL_ANCHOR = 'map-label-anchor'
export const WIND_VECTOR_LAYER_ID = 'wind-vector-arrows'

export function weatherInsertionPoint(map: Pick<Map, 'getLayer'>) {
  return map.getLayer(WEATHER_REFERENCE_ANCHOR)
    ? WEATHER_REFERENCE_ANCHOR
    : undefined
}

export function windInsertionPoint(map: Pick<Map, 'getLayer'>) {
  return map.getLayer(MAP_LABEL_ANCHOR) ? MAP_LABEL_ANCHOR : undefined
}

/** Geography only; weather requests continue to use the configured Weather Atlas server. */
export function weatherBasemapStyle(
  options: {
    vectorURL?: string
    glyphURL?: string
    rasterURL?: string
  } = {},
): StyleSpecification {
  const place = (
    id: string,
    classes: string[],
    minzoom: number,
    size: number,
  ): SymbolLayerSpecification => ({
    id,
    type: 'symbol',
    source: 'reference',
    'source-layer': 'place',
    minzoom,
    filter: ['match', ['get', 'class'], classes, true, false],
    layout: {
      'text-field': [
        'coalesce',
        ['get', 'name:en'],
        ['get', 'name_en'],
        ['get', 'name:latin'],
        ['get', 'name'],
      ],
      'text-font': ['Noto Sans Regular'],
      'text-size': [
        'interpolate',
        ['linear'],
        ['zoom'],
        minzoom,
        size,
        14,
        size + 3,
      ],
      'text-max-width': 9,
      'text-padding': 5,
      'text-allow-overlap': false,
      'symbol-sort-key': ['coalesce', ['get', 'rank'], 100],
    },
    paint: {
      'text-color': '#25313d',
      'text-halo-color': '#ffffff',
      'text-halo-width': 1.6,
      'text-halo-blur': 0.2,
    },
  })
  return {
    version: 8,
    glyphs:
      options.glyphURL ??
      'https://tiles.openfreemap.org/fonts/{fontstack}/{range}.pbf',
    sources: {
      reference: {
        type: 'vector',
        url: options.vectorURL ?? 'https://tiles.openfreemap.org/planet',
        attribution:
          '<a href="https://openfreemap.org/">OpenFreeMap</a> © <a href="https://openmaptiles.org/">OpenMapTiles</a> Data from <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
      },
      ...(options.rasterURL
        ? {
            basemap: {
              type: 'raster' as const,
              tiles: [options.rasterURL],
              tileSize: 256,
              maxzoom: 19,
              attribution: '© OpenStreetMap contributors',
            },
          }
        : {}),
    },
    layers: [
      {
        id: 'background',
        type: 'background',
        paint: { 'background-color': '#f2f3f1' },
      },
      {
        id: 'base-water',
        type: 'fill',
        source: 'reference',
        'source-layer': 'water',
        paint: { 'fill-color': '#dbe5e8' },
      },
      ...(options.rasterURL
        ? [
            {
              id: 'basemap',
              type: 'raster' as const,
              source: 'basemap',
              paint: { 'raster-saturation': -1, 'raster-opacity': 0.45 },
            },
          ]
        : []),
      {
        id: 'base-major-roads',
        type: 'line',
        source: 'reference',
        'source-layer': 'transportation',
        minzoom: 7,
        filter: [
          'match',
          ['get', 'class'],
          ['motorway', 'trunk', 'primary', 'secondary'],
          true,
          false,
        ],
        paint: {
          'line-color': '#bdc3c6',
          'line-width': ['interpolate', ['linear'], ['zoom'], 7, 0.5, 14, 2],
        },
      },
      {
        id: 'base-local-roads',
        type: 'line',
        source: 'reference',
        'source-layer': 'transportation',
        minzoom: 12,
        filter: [
          'match',
          ['get', 'class'],
          ['minor', 'tertiary', 'service'],
          true,
          false,
        ],
        paint: { 'line-color': '#d2d6d7', 'line-width': 0.7 },
      },
      {
        id: WEATHER_REFERENCE_ANCHOR,
        type: 'background',
        paint: { 'background-opacity': 0 },
      },
      // Water polygons include lakes and the coastline. Their buffer keeps tile clipping edges offscreen.
      {
        id: 'reference-shore-halo',
        type: 'line',
        source: 'reference',
        'source-layer': 'water',
        paint: {
          'line-color': '#ffffff',
          'line-opacity': 0.85,
          'line-width': 2.4,
        },
      },
      {
        id: 'reference-shore',
        type: 'line',
        source: 'reference',
        'source-layer': 'water',
        paint: {
          'line-color': '#526570',
          'line-opacity': 0.9,
          'line-width': 0.8,
        },
      },
      {
        id: 'reference-boundary-halo',
        type: 'line',
        source: 'reference',
        'source-layer': 'boundary',
        filter: [
          'all',
          ['<=', ['get', 'admin_level'], 4],
          ['!=', ['get', 'maritime'], 1],
        ],
        paint: {
          'line-color': '#ffffff',
          'line-opacity': 0.8,
          'line-width': 2.6,
        },
      },
      {
        id: 'reference-country',
        type: 'line',
        source: 'reference',
        'source-layer': 'boundary',
        filter: [
          'all',
          ['==', ['get', 'admin_level'], 2],
          ['!=', ['get', 'maritime'], 1],
          ['!=', ['get', 'disputed'], 1],
        ],
        paint: { 'line-color': '#5c6070', 'line-width': 1.1 },
      },
      {
        id: 'reference-province',
        type: 'line',
        source: 'reference',
        'source-layer': 'boundary',
        minzoom: 3,
        filter: [
          'all',
          ['>', ['get', 'admin_level'], 2],
          ['<=', ['get', 'admin_level'], 4],
          ['!=', ['get', 'maritime'], 1],
        ],
        paint: {
          'line-color': '#626779',
          'line-width': 0.9,
          'line-dasharray': [3, 2],
        },
      },
      {
        id: 'reference-disputed',
        type: 'line',
        source: 'reference',
        'source-layer': 'boundary',
        filter: [
          'all',
          ['==', ['get', 'admin_level'], 2],
          ['==', ['get', 'disputed'], 1],
        ],
        paint: {
          'line-color': '#626779',
          'line-width': 0.9,
          'line-dasharray': [2, 2],
        },
      },
      {
        id: MAP_LABEL_ANCHOR,
        type: 'background',
        paint: { 'background-opacity': 0 },
      },
      place('reference-city', ['city'], 3, 13),
      place('reference-town', ['town'], 6, 12),
      place('reference-village', ['village', 'hamlet', 'suburb'], 9, 11),
      { ...place('reference-state', ['state', 'province'], 4, 12), maxzoom: 9 },
      { ...place('reference-country-label', ['country'], 0, 12), maxzoom: 6 },
    ],
  }
}

export const windSize: ExpressionSpecification = [
  'interpolate',
  ['linear'],
  ['get', 'speed'],
  0,
  0.72,
  10,
  0.9,
  25,
  1.08,
  45,
  1.22,
]

/** A real RGBA outline, not a bitmap falsely declared to be a signed-distance-field sprite. */
export function createWindArrowImage() {
  const canvas = document.createElement('canvas')
  canvas.width = 48
  canvas.height = 48
  const context = canvas.getContext('2d')
  if (!context) return null
  context.beginPath()
  context.moveTo(24, 4)
  context.lineTo(38, 18)
  context.lineTo(29, 18)
  context.lineTo(29, 44)
  context.lineTo(19, 44)
  context.lineTo(19, 18)
  context.lineTo(10, 18)
  context.closePath()
  context.strokeStyle = '#ffffff'
  context.lineWidth = 4
  context.lineJoin = 'round'
  context.stroke()
  context.fillStyle = '#243746'
  context.fill()
  return context.getImageData(0, 0, 48, 48)
}
