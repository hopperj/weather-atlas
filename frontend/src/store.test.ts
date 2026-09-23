import { beforeEach, describe, expect, it } from 'vitest'
import { useMapSelection } from './store'

describe('map layer state', () => {
  beforeEach(() => {
    useMapSelection.setState({
      variable: '',
      product: '',
      domain: '',
      runTime: '',
      validTime: '',
      layers: [],
    })
  })

  it('enforces the three-layer limit and supports deterministic reordering', () => {
    const actions = useMapSelection.getState()
    actions.ensureLayer('temperature')
    actions.addLayer('humidity')
    actions.addLayer('cloud')
    actions.addLayer('pressure')

    const initial = useMapSelection.getState().layers
    expect(initial.map((layer) => layer.field)).toEqual([
      'temperature',
      'humidity',
      'cloud',
    ])

    useMapSelection.getState().moveLayer(initial[0].id, 1)
    expect(
      useMapSelection.getState().layers.map((layer) => layer.field),
    ).toEqual(['humidity', 'temperature', 'cloud'])
  })

  it('stores and clears a custom colour range without changing opacity', () => {
    useMapSelection.getState().ensureLayer('temperature')
    const layer = useMapSelection.getState().layers[0]

    useMapSelection.getState().updateLayer(layer.id, {
      displayMinimum: -15,
      displayMaximum: 25,
    })
    expect(useMapSelection.getState().layers[0]).toMatchObject({
      opacity: 0.62,
      displayMinimum: -15,
      displayMaximum: 25,
    })

    useMapSelection.getState().updateLayer(layer.id, {
      displayMinimum: undefined,
      displayMaximum: undefined,
    })
    expect(useMapSelection.getState().layers[0].displayMinimum).toBeUndefined()
  })

  it('stores a per-layer opacity cutoff independently from layer opacity', () => {
    useMapSelection.getState().ensureLayer('pm10')
    const layer = useMapSelection.getState().layers[0]

    useMapSelection.getState().updateLayer(layer.id, {
      opacity: 0.5,
      opacityCutoff: 20,
    })

    expect(useMapSelection.getState().layers[0]).toMatchObject({
      opacity: 0.5,
      opacityCutoff: 20,
    })
  })

  it('clears product-specific choices when the primary variable changes', () => {
    useMapSelection.setState({
      product: 'hrdps',
      domain: 'continental',
      runTime: '2026-07-19T06:00:00Z',
      validTime: '2026-07-19T12:00:00Z',
      layers: [
        { id: 'old-layer', field: 'temperature', opacity: 1, visible: true },
      ],
    })

    useMapSelection.getState().setVariable('pm25_surface')

    expect(useMapSelection.getState()).toMatchObject({
      variable: 'pm25_surface',
      product: '',
      domain: '',
      runTime: '',
      validTime: '',
      layers: [],
    })
  })
})
