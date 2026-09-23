import { create } from 'zustand'
import { WEATHER_OPACITY } from './mapPresentation'

export type WeatherLayerSelection = {
  id: string
  field: string
  opacity: number
  visible: boolean
  displayMinimum?: number
  displayMaximum?: number
  opacityCutoff?: number
}

type MapSelectionState = {
  variable: string
  product: string
  domain: string
  runTime: string
  validTime: string
  layers: WeatherLayerSelection[]
  playing: boolean
  playbackRate: number
  setVariable: (variable: string) => void
  setProduct: (product: string) => void
  setDomain: (domain: string) => void
  setRunTime: (runTime: string) => void
  setValidTime: (validTime: string) => void
  setPlaying: (playing: boolean) => void
  setPlaybackRate: (playbackRate: number) => void
  ensureLayer: (field: string) => void
  addLayer: (field: string) => void
  updateLayer: (
    id: string,
    change: Partial<Omit<WeatherLayerSelection, 'id'>>,
  ) => void
  moveLayer: (id: string, direction: -1 | 1) => void
  removeLayer: (id: string) => void
}

let nextLayerId = 1

export const useMapSelection = create<MapSelectionState>((set) => ({
  variable: '',
  product: '',
  domain: '',
  runTime: '',
  validTime: '',
  layers: [],
  playing: false,
  playbackRate: 1,
  setVariable: (variable) =>
    set({
      variable,
      product: '',
      domain: '',
      runTime: '',
      validTime: '',
      layers: [],
      playing: false,
    }),
  setProduct: (product) =>
    set({
      product,
      domain: '',
      runTime: '',
      validTime: '',
      layers: [],
      playing: false,
    }),
  setDomain: (domain) => set({ domain }),
  setRunTime: (runTime) => set({ runTime, validTime: '', playing: false }),
  setValidTime: (validTime) => set({ validTime }),
  setPlaying: (playing) => set({ playing }),
  setPlaybackRate: (playbackRate) => set({ playbackRate }),
  ensureLayer: (field) =>
    set((state) =>
      state.layers.length > 0
        ? state
        : {
            layers: [
              {
                id: `layer-${nextLayerId++}`,
                field,
                opacity: WEATHER_OPACITY,
                visible: true,
              },
            ],
          },
    ),
  addLayer: (field) =>
    set((state) =>
      state.layers.length >= 3
        ? state
        : {
            layers: [
              ...state.layers,
              {
                id: `layer-${nextLayerId++}`,
                field,
                opacity: WEATHER_OPACITY,
                visible: true,
              },
            ],
          },
    ),
  updateLayer: (id, change) =>
    set((state) => ({
      layers: state.layers.map((layer) =>
        layer.id === id ? { ...layer, ...change } : layer,
      ),
    })),
  moveLayer: (id, direction) =>
    set((state) => {
      const index = state.layers.findIndex((layer) => layer.id === id)
      const destination = index + direction
      if (index < 0 || destination < 0 || destination >= state.layers.length)
        return state
      const layers = [...state.layers]
      const [layer] = layers.splice(index, 1)
      layers.splice(destination, 0, layer)
      return { layers }
    }),
  removeLayer: (id) =>
    set((state) => ({
      layers: state.layers.filter((layer) => layer.id !== id),
    })),
}))
