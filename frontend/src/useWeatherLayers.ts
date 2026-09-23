import type { Map as MapLibreMap } from 'maplibre-gl'
import {
  type MutableRefObject,
  useCallback,
  useEffect,
  useRef,
  useState,
} from 'react'
import type { ResolvedLayer } from './api'
import { weatherInsertionPoint } from './mapPresentation'

export type DisplayLayer = {
  selectionId: string
  layer: ResolvedLayer
  opacity: number
  visible: boolean
}

export type BufferedWeatherFrame = {
  frameId: string
  expectedLayerCount: number
  layers: DisplayLayer[]
}

export type WeatherLayerBufferState = {
  activeFrameReady: boolean
  readyFrameIds: ReadonlySet<string>
}

type MountedLayer = {
  frameId: string
  layerId: string
  selectionId: string
  sourceId: string
  token: string
}

type BufferedLayer = MountedLayer & {
  checkReady?: () => void
  opacity: number
  ready: boolean
  readyChecks: number
  readyTimer?: number
  visible: boolean
}

const READY_CHECK_DELAY_MS = 60
const READY_CONFIRMATION_DELAY_MS = 40
const FRAME_TRANSITION_MS = 110
const LAYER_REMOVAL_DELAY_MS = FRAME_TRANSITION_MS + 30

function layerKey(frameId: string, selectionId: string) {
  return `${frameId}\u0000${selectionId}`
}

function sameSet(left: ReadonlySet<string>, right: ReadonlySet<string>) {
  return (
    left.size === right.size && [...left].every((value) => right.has(value))
  )
}

function removeMountedLayer(map: MapLibreMap, mounted: MountedLayer) {
  if (map.getLayer(mounted.layerId)) map.removeLayer(mounted.layerId)
  if (map.getSource(mounted.sourceId)) map.removeSource(mounted.sourceId)
}

export function useWeatherLayers(
  mapRef: MutableRefObject<MapLibreMap | null>,
  mapReady: boolean,
  frames: BufferedWeatherFrame[],
  activeFrameId: string,
): WeatherLayerBufferState {
  const entriesRef = useRef(new Map<string, BufferedLayer>())
  const heldLayersRef = useRef(new Set<MountedLayer>())
  const removalTimersRef = useRef(new Set<number>())
  const serialRef = useRef(0)
  const framesRef = useRef(frames)
  const activeFrameIdRef = useRef(activeFrameId)
  const desiredKeysRef = useRef(new Set<string>())
  const visibleFrameIdRef = useRef('')
  const [readyFrameIds, setReadyFrameIds] = useState<ReadonlySet<string>>(
    () => new Set(),
  )

  const scheduleRemoval = useCallback(
    (mounted: MountedLayer) => {
      const map = mapRef.current
      if (!map?.getStyle()) return
      if (map.getLayer(mounted.layerId)) {
        map.setPaintProperty(mounted.layerId, 'raster-opacity', 0)
      }
      const timer = window.setTimeout(() => {
        removalTimersRef.current.delete(timer)
        const currentMap = mapRef.current
        if (currentMap?.getStyle()) removeMountedLayer(currentMap, mounted)
      }, LAYER_REMOVAL_DELAY_MS)
      removalTimersRef.current.add(timer)
    },
    [mapRef],
  )

  const refreshReadyFrames = useCallback(() => {
    const map = mapRef.current
    if (!mapReady || !map?.getStyle()) return

    const nextReadyFrameIds = new Set<string>()
    for (const frame of framesRef.current) {
      if (
        frame.expectedLayerCount < 1 ||
        frame.layers.length !== frame.expectedLayerCount
      ) {
        continue
      }
      const ready = frame.layers.every((item) => {
        const entry = entriesRef.current.get(
          layerKey(frame.frameId, item.selectionId),
        )
        return entry?.token === item.layer.token && entry.ready
      })
      if (ready) nextReadyFrameIds.add(frame.frameId)
    }

    setReadyFrameIds((current) =>
      sameSet(current, nextReadyFrameIds) ? current : nextReadyFrameIds,
    )

    const nextVisibleFrameId = activeFrameIdRef.current
    if (!nextReadyFrameIds.has(nextVisibleFrameId)) return

    for (const entry of entriesRef.current.values()) {
      if (!map.getLayer(entry.layerId)) continue
      const shouldShow = entry.frameId === nextVisibleFrameId && entry.visible
      map.setPaintProperty(
        entry.layerId,
        'raster-opacity',
        shouldShow ? entry.opacity : 0,
      )
    }

    const activeFrame = framesRef.current.find(
      (frame) => frame.frameId === nextVisibleFrameId,
    )
    for (const item of activeFrame?.layers ?? []) {
      const entry = entriesRef.current.get(
        layerKey(nextVisibleFrameId, item.selectionId),
      )
      if (entry && map.getLayer(entry.layerId))
        map.moveLayer(entry.layerId, weatherInsertionPoint(map))
    }

    visibleFrameIdRef.current = nextVisibleFrameId
    for (const held of heldLayersRef.current) scheduleRemoval(held)
    heldLayersRef.current.clear()

    for (const [key, entry] of entriesRef.current) {
      if (
        !desiredKeysRef.current.has(key) &&
        entry.frameId !== nextVisibleFrameId
      ) {
        if (entry.readyTimer !== undefined) {
          window.clearTimeout(entry.readyTimer)
        }
        entriesRef.current.delete(key)
        scheduleRemoval(entry)
      }
    }
  }, [mapReady, mapRef, scheduleRemoval])

  const startReadyCheck = useCallback(
    (entry: BufferedLayer) => {
      const checkReady = () => {
        if (
          entriesRef.current.get(layerKey(entry.frameId, entry.selectionId)) !==
          entry
        ) {
          return
        }
        const map = mapRef.current
        if (!map?.getStyle()) return

        let loaded = false
        try {
          loaded =
            Boolean(map.getLayer(entry.layerId)) &&
            Boolean(map.getSource(entry.sourceId)) &&
            map.isSourceLoaded(entry.sourceId)
        } catch {
          loaded = false
        }

        entry.readyChecks = loaded ? entry.readyChecks + 1 : 0
        if (entry.readyChecks >= 2) {
          entry.ready = true
          entry.readyTimer = undefined
          refreshReadyFrames()
          return
        }
        entry.ready = false
        entry.readyTimer = window.setTimeout(
          checkReady,
          loaded ? READY_CONFIRMATION_DELAY_MS : READY_CHECK_DELAY_MS,
        )
      }
      entry.checkReady = checkReady
      if (entry.readyTimer !== undefined) window.clearTimeout(entry.readyTimer)
      entry.readyTimer = window.setTimeout(checkReady, 0)
    },
    [mapRef, refreshReadyFrames],
  )

  useEffect(() => {
    framesRef.current = frames
    activeFrameIdRef.current = activeFrameId
    const map = mapRef.current
    if (!map || !mapReady) return

    const desiredKeys = new Set<string>()
    for (const frame of frames) {
      for (const item of frame.layers) {
        desiredKeys.add(layerKey(frame.frameId, item.selectionId))
      }
    }
    desiredKeysRef.current = desiredKeys

    for (const [key, entry] of entriesRef.current) {
      if (desiredKeys.has(key)) continue
      const retainVisibleFrame =
        activeFrameId.length > 0 &&
        frames.length > 0 &&
        entry.frameId === visibleFrameIdRef.current
      if (retainVisibleFrame) continue
      if (entry.readyTimer !== undefined) window.clearTimeout(entry.readyTimer)
      entriesRef.current.delete(key)
      scheduleRemoval(entry)
    }

    frames.forEach((frame) => {
      frame.layers.forEach((item, order) => {
        const key = layerKey(frame.frameId, item.selectionId)
        const existing = entriesRef.current.get(key)
        if (existing?.token === item.layer.token) {
          existing.opacity = item.opacity
          existing.visible = item.visible
          return
        }

        if (existing) {
          if (existing.readyTimer !== undefined) {
            window.clearTimeout(existing.readyTimer)
          }
          entriesRef.current.delete(key)
          if (existing.frameId === visibleFrameIdRef.current) {
            heldLayersRef.current.add(existing)
          } else {
            removeMountedLayer(map, existing)
          }
        }

        const serial = serialRef.current++
        const safeSelection = item.selectionId.replace(/[^A-Za-z0-9_-]/g, '')
        const sourceId = `weather-source-${safeSelection}-${serial}`
        const layerId = `weather-layer-${safeSelection}-${serial}`

        map.addSource(sourceId, {
          type: 'raster',
          tiles: [item.layer.tileUrl],
          tileSize: 256,
          bounds: item.layer.bounds ?? undefined,
          attribution: 'Environment and Climate Change Canada',
        })
        map.addLayer(
          {
            id: layerId,
            type: 'raster',
            source: sourceId,
            paint: {
              'raster-fade-duration': 0,
              'raster-opacity': 0,
              'raster-opacity-transition': {
                duration: FRAME_TRANSITION_MS,
                delay: order * 8,
              },
              'raster-resampling': 'linear',
            },
          },
          weatherInsertionPoint(map),
        )

        const entry: BufferedLayer = {
          frameId: frame.frameId,
          layerId,
          opacity: item.opacity,
          ready: false,
          readyChecks: 0,
          selectionId: item.selectionId,
          sourceId,
          token: item.layer.token,
          visible: item.visible,
        }
        entriesRef.current.set(key, entry)
        startReadyCheck(entry)
      })
    })

    const refreshTimer = window.setTimeout(refreshReadyFrames, 0)
    return () => window.clearTimeout(refreshTimer)
  }, [
    activeFrameId,
    frames,
    mapReady,
    mapRef,
    refreshReadyFrames,
    scheduleRemoval,
    startReadyCheck,
  ])

  useEffect(() => {
    const map = mapRef.current
    if (!map || !mapReady) return

    const invalidate = () => {
      for (const entry of entriesRef.current.values()) {
        if (entry.readyTimer !== undefined) {
          window.clearTimeout(entry.readyTimer)
          entry.readyTimer = undefined
        }
        entry.ready = false
        entry.readyChecks = 0
      }
      setReadyFrameIds(new Set())
    }
    const resume = () => {
      invalidate()
      for (const entry of entriesRef.current.values()) entry.checkReady?.()
    }

    map.on('movestart', invalidate)
    map.on('moveend', resume)
    return () => {
      map.off('movestart', invalidate)
      map.off('moveend', resume)
    }
  }, [mapReady, mapRef])

  useEffect(
    () => () => {
      const map = mapRef.current
      for (const timer of removalTimersRef.current) window.clearTimeout(timer)
      removalTimersRef.current.clear()
      for (const entry of entriesRef.current.values()) {
        if (entry.readyTimer !== undefined)
          window.clearTimeout(entry.readyTimer)
      }
      if (map?.getStyle()) {
        for (const entry of entriesRef.current.values()) {
          removeMountedLayer(map, entry)
        }
        for (const held of heldLayersRef.current) removeMountedLayer(map, held)
      }
      entriesRef.current.clear()
      heldLayersRef.current.clear()
    },
    [mapRef],
  )

  return {
    activeFrameReady: mapReady && readyFrameIds.has(activeFrameId),
    readyFrameIds,
  }
}
