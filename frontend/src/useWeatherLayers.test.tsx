// @vitest-environment jsdom

import { act, renderHook } from '@testing-library/react'
import type { Map as MapLibreMap } from 'maplibre-gl'
import type { MutableRefObject } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { ResolvedLayer } from './api'
import { type DisplayLayer, useWeatherLayers } from './useWeatherLayers'
import {
  WEATHER_REFERENCE_ANCHOR,
  MAP_LABEL_ANCHOR,
  WIND_VECTOR_LAYER_ID,
} from './mapPresentation'

class MapStub {
  layerOrder: string[] = []
  readonly layers = new Map<
    string,
    { paint: Record<string, unknown>; source: string }
  >()
  readonly loadedSources = new Set<string>()
  readonly sources = new Map<string, unknown>()
  private readonly listeners = new Map<string, Set<() => void>>()
  tilesLoaded = false

  addSource(id: string, source: unknown) {
    this.sources.set(id, source)
    this.tilesLoaded = false
    this.emit('dataloading')
  }

  addLayer(
    layer: {
      id: string
      source: string
      paint?: Record<string, unknown>
    },
    beforeId?: string,
  ) {
    this.layers.set(layer.id, {
      paint: { ...layer.paint },
      source: layer.source,
    })
    this.moveLayer(layer.id, beforeId)
  }

  areTilesLoaded() {
    return this.tilesLoaded
  }

  getLayer(id: string) {
    return this.layers.get(id)
  }

  getSource(id: string) {
    return this.sources.get(id)
  }

  getStyle() {
    return {}
  }

  isSourceLoaded(id: string) {
    return this.loadedSources.has(id)
  }

  moveLayer(id: string, beforeId?: string) {
    this.layerOrder = this.layerOrder.filter((current) => current !== id)
    const index = beforeId ? this.layerOrder.indexOf(beforeId) : -1
    this.layerOrder.splice(index < 0 ? this.layerOrder.length : index, 0, id)
  }

  off(event: string, listener: () => void) {
    this.listeners.get(event)?.delete(listener)
  }

  on(event: string, listener: () => void) {
    const listeners = this.listeners.get(event) ?? new Set()
    listeners.add(listener)
    this.listeners.set(event, listeners)
  }

  removeLayer(id: string) {
    this.layers.delete(id)
    this.layerOrder = this.layerOrder.filter((current) => current !== id)
  }

  removeSource(id: string) {
    this.loadedSources.delete(id)
    this.sources.delete(id)
  }

  setPaintProperty(layerId: string, property: string, value: unknown) {
    const layer = this.layers.get(layerId)
    if (layer) layer.paint[property] = value
  }

  emit(event: string) {
    for (const listener of this.listeners.get(event) ?? []) listener()
  }
}

function displayLayer(token: string, validTime: string): DisplayLayer {
  return {
    selectionId: 'temperature-layer',
    opacity: 0.8,
    visible: true,
    layer: {
      product: 'hrdps',
      domain: 'continental',
      runTime: '2026-07-21T18:00:00Z',
      validTime,
      forecastHour: 5,
      field: 'air_temperature_2m',
      variable: 'air_temperature',
      level: '2m',
      unit: 'degC',
      tileUrl: `/tiles/${token}/{z}/{x}/{y}.webp`,
      token,
      bounds: [-141, 39, -42, 84],
      legend: {
        minimum: -40,
        maximum: 40,
        palette: [{ value: -40, color: '#000040' }],
      },
    } satisfies ResolvedLayer,
  }
}

describe('weather layer frame swaps', () => {
  beforeEach(() => vi.useFakeTimers())

  afterEach(() => {
    vi.runOnlyPendingTimers()
    vi.useRealTimers()
  })

  it('keeps prefetched and reordered weather below coastlines, arrows and labels during swaps', () => {
    const map = new MapStub()
    const references = [
      WEATHER_REFERENCE_ANCHOR,
      'reference-shore',
      WIND_VECTOR_LAYER_ID,
      MAP_LABEL_ANCHOR,
      'reference-city',
    ]
    for (const id of references) map.addLayer({ id, source: 'reference' })
    const a = displayLayer('a', '2026-09-08T12:00:00Z')
    const b = displayLayer('b', '2026-09-08T13:00:00Z')
    const frames = [a, b].map((layer) => ({
      frameId: layer.layer.validTime,
      expectedLayerCount: 1,
      layers: [layer],
    }))
    const mapRef = { current: map as unknown as MapLibreMap }
    const { rerender, unmount } = renderHook(
      ({ activeFrameId }) =>
        useWeatherLayers(
          mapRef,
          true,
          frames,
          activeFrameId,
        ),
      { initialProps: { activeFrameId: a.layer.validTime } },
    )
    const assertOrder = () => {
      const weather = map.layerOrder.filter((id) =>
        id.startsWith('weather-layer-'),
      )
      expect(weather.length).toBeGreaterThan(0)
      for (const id of weather)
        expect(map.layerOrder.indexOf(id)).toBeLessThan(
          map.layerOrder.indexOf(WEATHER_REFERENCE_ANCHOR),
        )
      expect(map.layerOrder.filter((id) => references.includes(id))).toEqual(
        references,
      )
    }
    assertOrder()
    act(() => {
      for (const source of map.sources.keys()) map.loadedSources.add(source)
      vi.advanceTimersByTime(100)
    })
    assertOrder()
    rerender({ activeFrameId: b.layer.validTime })
    act(() => vi.advanceTimersByTime(150))
    assertOrder()
    rerender({ activeFrameId: a.layer.validTime })
    act(() => vi.advanceTimersByTime(150))
    assertOrder()
    unmount()
  })

  it('preloads future frames and holds the current frame until the next one is ready', () => {
    const map = new MapStub()
    const mapRef = {
      current: map as unknown as MapLibreMap,
    } as MutableRefObject<MapLibreMap>
    const frameA = displayLayer('frame-a', '2026-07-21T23:00:00Z')
    const frameB = displayLayer('frame-b', '2026-07-22T00:00:00Z')
    const frameC = displayLayer('frame-c', '2026-07-22T01:00:00Z')
    const { result, rerender, unmount } = renderHook(
      ({ activeFrameId, frames }) =>
        useWeatherLayers(mapRef, true, frames, activeFrameId),
      {
        initialProps: {
          activeFrameId: frameA.layer.validTime,
          frames: [
            {
              frameId: frameA.layer.validTime,
              expectedLayerCount: 1,
              layers: [frameA],
            },
            {
              frameId: frameB.layer.validTime,
              expectedLayerCount: 1,
              layers: [frameB],
            },
            {
              frameId: frameC.layer.validTime,
              expectedLayerCount: 1,
              layers: [frameC],
            },
          ],
        },
      },
    )

    const sourceA = 'weather-source-temperature-layer-0'
    const sourceB = 'weather-source-temperature-layer-1'
    const sourceC = 'weather-source-temperature-layer-2'
    const layerA = 'weather-layer-temperature-layer-0'
    const layerB = 'weather-layer-temperature-layer-1'
    const layerC = 'weather-layer-temperature-layer-2'
    expect(map.getSource(sourceA)).toBeTruthy()
    expect(map.getSource(sourceB)).toBeTruthy()
    expect(map.getSource(sourceC)).toBeTruthy()

    act(() => {
      map.loadedSources.add(sourceA)
      map.loadedSources.add(sourceC)
      vi.advanceTimersByTime(100)
    })
    expect(result.current.activeFrameReady).toBe(true)
    expect(result.current.readyFrameIds.has(frameA.layer.validTime)).toBe(true)
    expect(result.current.readyFrameIds.has(frameB.layer.validTime)).toBe(false)
    expect(result.current.readyFrameIds.has(frameC.layer.validTime)).toBe(true)
    expect(map.layers.get(layerA)?.paint['raster-fade-duration']).toBe(0)
    expect(map.layers.get(layerA)?.paint['raster-opacity']).toBe(0.8)
    expect(map.layers.get(layerC)?.paint['raster-opacity']).toBe(0)

    rerender({
      activeFrameId: frameB.layer.validTime,
      frames: [
        {
          frameId: frameB.layer.validTime,
          expectedLayerCount: 1,
          layers: [frameB],
        },
        {
          frameId: frameC.layer.validTime,
          expectedLayerCount: 1,
          layers: [frameC],
        },
      ],
    })
    expect(map.getSource(sourceA)).toBeTruthy()
    expect(map.layers.get(layerA)?.paint['raster-opacity']).toBe(0.8)
    expect(map.layers.get(layerB)?.paint['raster-opacity']).toBe(0)
    expect(result.current.activeFrameReady).toBe(false)

    act(() => {
      map.loadedSources.add(sourceB)
      vi.advanceTimersByTime(100)
    })
    expect(result.current.activeFrameReady).toBe(true)
    expect(map.layers.get(layerB)?.paint['raster-opacity']).toBe(0.8)
    expect(map.layers.get(layerA)?.paint['raster-opacity']).toBe(0)

    act(() => vi.advanceTimersByTime(140))
    expect(map.getSource(sourceA)).toBeUndefined()
    expect(map.getSource(sourceB)).toBeTruthy()
    expect(map.getSource(sourceC)).toBeTruthy()

    unmount()
  })
})
