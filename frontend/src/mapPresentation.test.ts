// @vitest-environment jsdom
import {
  createExpression,
  validateStyleMin,
} from '@maplibre/maplibre-gl-style-spec'
import { describe, expect, it, vi } from 'vitest'
import {
  createWindArrowImage,
  weatherBasemapStyle,
  WEATHER_OPACITY,
  WEATHER_REFERENCE_ANCHOR,
  MAP_LABEL_ANCHOR,
  weatherInsertionPoint,
  windInsertionPoint,
  windArrowImage,
  windColour,
  WIND_ARROW_SPRITES,
  WIND_SPEED_COLOURS,
  WIND_SPEED_GRADIENT,
  WIND_UNKNOWN_COLOUR,
  WIND_UNKNOWN_IMAGE_ID,
} from './mapPresentation'

describe('weather map presentation', () => {
  it('builds a valid neutral vector style with full-contrast reference layers above weather', () => {
    const style = weatherBasemapStyle()
    expect(validateStyleMin(style)).toEqual([])
    const ids = style.layers.map((layer) => layer.id)
    const anchor = ids.indexOf(WEATHER_REFERENCE_ANCHOR)
    expect(ids.indexOf('base-water')).toBeLessThan(anchor)
    for (const id of [
      'reference-shore',
      'reference-country',
      'reference-province',
      'reference-city',
    ]) {
      expect(ids.indexOf(id)).toBeGreaterThan(anchor)
    }
    expect(ids.indexOf('reference-city')).toBeGreaterThan(
      ids.indexOf(MAP_LABEL_ANCHOR),
    )
    const labels = style.layers.filter((layer) => layer.type === 'symbol')
    expect(
      labels.every((layer) => layer.paint?.['text-halo-color'] === '#ffffff'),
    ).toBe(true)
    expect(
      style.layers.some(
        (layer) =>
          layer.type === 'hillshade' || layer.type === 'fill-extrusion',
      ),
    ).toBe(false)
    expect(WEATHER_OPACITY).toBe(0.62)
  })

  it('allows self-hosted vector tiles and glyphs and preserves an optional custom raster backdrop', () => {
    const style = weatherBasemapStyle({
      vectorURL: '/maps/tiles.json',
      glyphURL: '/maps/fonts/{fontstack}/{range}.pbf',
      rasterURL: '/maps/{z}/{x}/{y}.png',
    })
    expect(validateStyleMin(style)).toEqual([])
    expect(style.sources.reference).toMatchObject({
      type: 'vector',
      url: '/maps/tiles.json',
    })
    expect(style.glyphs).toBe('/maps/fonts/{fontstack}/{range}.pbf')
    expect(style.sources.basemap).toMatchObject({
      tiles: ['/maps/{z}/{x}/{y}.png'],
    })
  })

  it('uses fixed insertion anchors with safe fallback before the style is installed', () => {
    const style = weatherBasemapStyle()
    const map = {
      getLayer: (id: string) => style.layers.find((layer) => layer.id === id),
    }
    expect(weatherInsertionPoint(map as never)).toBe(WEATHER_REFERENCE_ANCHOR)
    expect(windInsertionPoint(map as never)).toBe(MAP_LABEL_ANCHOR)
    expect(weatherInsertionPoint({ getLayer: () => undefined })).toBeUndefined()
  })

  it('matches the legend colours, interpolates speeds and caps the highest colour', () => {
    for (const { speed, color } of WIND_SPEED_COLOURS) {
      expect(windColour(speed)).toBe(color)
      expect(WIND_SPEED_GRADIENT).toContain(`${color} ${(speed / 40) * 100}%`)
    }
    expect(windColour(2)).toBe('#1b77c3')
    expect(windColour(2.9)).toBe(windColour(2))
    expect(windColour(300)).toBe(windColour(40))
    for (const speed of [null, undefined, -1, NaN, Infinity, -Infinity]) {
      expect(windColour(speed)).toBe(WIND_UNKNOWN_COLOUR)
    }
  })

  it('selects a cached colour sprite from each frame’s speed, not bearing', () => {
    const expression = createExpression(windArrowImage('m/s'))
    expect(expression.result).toBe('success')
    if (expression.result !== 'success')
      throw new Error('Invalid wind expression')
    const spriteIDs = WIND_ARROW_SPRITES.map(({ id }) => id)
    expect(new Set(spriteIDs).size).toBe(42)
    for (const speed of [0, 0.9, 3, 5, 10.7, 20, 40, 45, 1000]) {
      const expected = `wind-arrow-${Math.floor(Math.min(speed, 40))}`
      for (const bearing of [0, 90, 270]) {
        const id = expression.value.evaluate(
          { zoom: 6 },
          { type: 'Point', properties: { speed, bearing } },
        )
        expect(id).toBe(expected)
        expect(spriteIDs).toContain(id)
      }
    }
    for (const speed of [null, undefined, -1, 'fast']) {
      expect(
        expression.value.evaluate(
          { zoom: 6 },
          { type: 'Point', properties: { speed } },
        ),
      ).toBe(WIND_UNKNOWN_IMAGE_ID)
    }
    expect(windArrowImage('km/h')).toBe(WIND_UNKNOWN_IMAGE_ID)
    const style = weatherBasemapStyle()
    style.sources.wind = {
      type: 'geojson',
      data: { type: 'FeatureCollection', features: [] },
    }
    style.layers.push({
      id: 'wind',
      type: 'symbol',
      source: 'wind',
      layout: { 'icon-image': windArrowImage('m/s') },
    })
    expect(validateStyleMin(style)).toEqual([])
  })

  it('draws coloured RGBA arrows with actual white edges instead of an invalid SDF halo', () => {
    const context = {
      beginPath: vi.fn(),
      moveTo: vi.fn(),
      lineTo: vi.fn(),
      closePath: vi.fn(),
      stroke: vi.fn(),
      fill: vi.fn(),
      getImageData: vi.fn(() => ({ data: new Uint8ClampedArray() })),
      strokeStyle: '',
      fillStyle: '',
      lineWidth: 0,
      lineJoin: '',
    }
    const spy = vi
      .spyOn(HTMLCanvasElement.prototype, 'getContext')
      .mockReturnValue(context as never)
    try {
      expect(createWindArrowImage(windColour(20))).not.toBeNull()
      expect(context.strokeStyle).toBe('#ffffff')
      expect(context.fillStyle).toBe('#ea580c')
      expect(context.lineWidth).toBe(4)
      expect(context.stroke).toHaveBeenCalledOnce()
      expect(context.fill).toHaveBeenCalledOnce()
      expect(context.getImageData).toHaveBeenCalledWith(0, 0, 48, 48)
    } finally {
      spy.mockRestore()
    }
  })

  it('does not create a sprite when a canvas context is unavailable', () => {
    const spy = vi
      .spyOn(HTMLCanvasElement.prototype, 'getContext')
      .mockReturnValue(null)
    try {
      expect(createWindArrowImage(windColour(0))).toBeNull()
    } finally {
      spy.mockRestore()
    }
  })
})
