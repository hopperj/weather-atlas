// @vitest-environment jsdom
import { validateStyleMin } from '@maplibre/maplibre-gl-style-spec'
import { describe, expect, it, vi } from 'vitest'
import {
  createWindArrowImage,
  weatherBasemapStyle,
  WEATHER_OPACITY,
  WEATHER_REFERENCE_ANCHOR,
  MAP_LABEL_ANCHOR,
  weatherInsertionPoint,
  windInsertionPoint,
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

  it('draws an actual white-edged dark arrow instead of relying on an invalid SDF halo', () => {
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
      expect(createWindArrowImage()).not.toBeNull()
      expect(context.strokeStyle).toBe('#ffffff')
      expect(context.fillStyle).toBe('#243746')
      expect(context.lineWidth).toBe(4)
      expect(context.stroke).toHaveBeenCalledOnce()
      expect(context.fill).toHaveBeenCalledOnce()
      expect(context.getImageData).toHaveBeenCalledWith(0, 0, 48, 48)
    } finally {
      spy.mockRestore()
    }
  })
})
