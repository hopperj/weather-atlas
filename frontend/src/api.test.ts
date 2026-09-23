import { describe, expect, it } from 'vitest'
import {
  fieldSchema,
  hotspotCollectionSchema,
  hotspotDateCollectionSchema,
  layerSchema,
  productTimeSchema,
  timelineFrameSchema,
  variableSchema,
  windVectorCollectionSchema,
} from './api'

describe('weather API schemas', () => {
  it('accepts a forecast time and an analysis time', () => {
    expect(
      productTimeSchema.parse({
        validTime: '2026-07-16T18:00:00Z',
        forecastHour: 6,
        intervalStart: null,
        intervalEnd: null,
        timeKind: 'instant',
      }).forecastHour,
    ).toBe(6)

    expect(
      productTimeSchema.parse({
        validTime: '2026-07-16T18:00:00Z',
        forecastHour: null,
        intervalStart: '2026-07-16T12:00:00Z',
        intervalEnd: '2026-07-16T18:00:00Z',
        timeKind: 'accumulation',
      }).forecastHour,
    ).toBeNull()
  })

  it('parses a cross-run timeline frame with its selected model run', () => {
    const frame = timelineFrameSchema.parse({
      runTime: '2026-07-16T12:00:00Z',
      validTime: '2026-07-16T18:00:00Z',
      forecastHour: 6,
      intervalStart: null,
      intervalEnd: null,
      timeKind: 'instant',
    })

    expect(frame.runTime).toBe('2026-07-16T12:00:00Z')
    expect(frame.forecastHour).toBe(6)
  })

  it('rejects fields without display palette stops', () => {
    expect(() =>
      fieldSchema.parse({
        code: 'air_temperature_2m',
        variableCode: 'air_temperature',
        name: 'Air temperature',
        variableClass: 'atmosphere',
        levelCode: '2m_agl',
        levelName: '2 m above ground',
        unit: 'degC',
        palette: [],
        defaultMin: -40,
        defaultMax: 40,
      }),
    ).toThrow()
  })

  it('accepts unlabeled palette stops from the catalogue API', () => {
    const field = fieldSchema.parse({
      code: 'air_temperature_2m',
      variableCode: 'air_temperature',
      name: 'Air temperature',
      variableClass: 'atmosphere',
      levelCode: '2m_agl',
      levelName: '2 m above ground',
      unit: 'degC',
      palette: [{ value: -40, color: '#32215f', label: null }],
      defaultMin: -40,
      defaultMax: 40,
    })

    expect(field.palette[0]?.label).toBeNull()
  })

  it('accepts a variable with compatible source products', () => {
    const variable = variableSchema.parse({
      code: 'air_temperature_2m',
      variableCode: 'air_temperature',
      name: 'Air temperature',
      variableClass: 'atmosphere',
      levelCode: '2m_agl',
      levelName: '2 metres above ground',
      unit: 'degC',
      products: ['hrdps', 'rdps', 'gdps'],
    })

    expect(variable.products).toContain('gdps')
  })

  it('parses a map-ready wildfire hotspot snapshot', () => {
    const snapshot = hotspotCollectionSchema.parse({
      type: 'FeatureCollection',
      data_date: '2026-07-20',
      generated_at: '2026-07-21T07:15:07Z',
      sensor: 'VIIRS-I',
      nominal_resolution_metres: 375,
      feature_count: 1,
      features: [
        {
          type: 'Feature',
          id: 'detection-1',
          geometry: { type: 'Point', coordinates: [-79.67, 33.19] },
          properties: {
            observed_at: '2026-07-20T23:38:00Z',
            fwi: 19.5,
          },
        },
      ],
    })

    expect(snapshot.features[0]?.properties.observed_at).toBe(
      '2026-07-20T23:38:00Z',
    )
  })

  it('parses the available wildfire hotspot dates', () => {
    const dates = hotspotDateCollectionSchema.parse({
      items: [
        {
          dataDate: '2026-07-20',
          featureCount: 17131,
          firstObservation: '2026-07-20T00:01:00Z',
          lastObservation: '2026-07-20T23:59:00Z',
          bbox: [-146.473, 26.1375, -63.6525, 67.4497],
        },
      ],
      availableStart: '2026-07-20',
      availableEnd: '2026-07-20',
    })

    expect(dates.items[0]?.featureCount).toBe(17131)
  })

  it('parses a resolved tokenized layer without requiring a local path', () => {
    const layer = layerSchema.parse({
      product: 'hrdps',
      domain: 'continental',
      runTime: '2026-07-16T12:00:00Z',
      validTime: '2026-07-16T18:00:00Z',
      forecastHour: 6,
      field: 'air_temperature_2m',
      variable: 'air_temperature',
      level: '2m_agl',
      unit: 'degC',
      tileUrl: '/tiles/v1/signed-token/{z}/{x}/{y}.webp',
      token: 'signed-token',
      bounds: [-141, 39, -42, 84],
      legend: {
        minimum: -40,
        maximum: 40,
        palette: [{ value: -40, color: '#32215f' }],
      },
    })

    expect(layer.tileUrl).toContain('{z}')
    expect(layer).not.toHaveProperty('path')
  })

  it('parses map-ready wind vectors with speed and bearing', () => {
    const vectors = windVectorCollectionSchema.parse({
      type: 'FeatureCollection',
      product: 'hrdps',
      domain: 'continental',
      runTime: '2026-07-23T12:00:00Z',
      validTime: '2026-07-23T18:00:00Z',
      unit: 'm/s',
      bbox: [-70, 40, -55, 50],
      columns: 1,
      rows: 1,
      featureCount: 1,
      features: [
        {
          type: 'Feature',
          geometry: { type: 'Point', coordinates: [-62.5, 45] },
          properties: { u: 3, v: 4, speed: 5, bearing: 36.9 },
        },
      ],
    })

    expect(vectors.features[0]?.properties.speed).toBe(5)
    expect(vectors.features[0]?.properties.bearing).toBe(36.9)
  })
})
