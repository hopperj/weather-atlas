import { describe, expect, it } from 'vitest'
import { hotspotCollectionSchema } from './api'
import { hotspotCollectionBounds } from './hotspots'

const baseCollection = {
  type: 'FeatureCollection' as const,
  data_date: '2026-07-21',
  generated_at: '2026-07-22T07:15:07Z',
  sensor: 'VIIRS-I',
  nominal_resolution_metres: 375,
  feature_count: 2,
  features: [
    {
      type: 'Feature' as const,
      geometry: {
        type: 'Point' as const,
        coordinates: [-117.25, 33.82] as [number, number],
      },
      properties: { observed_at: '2026-07-21T21:33:00Z', fwi: 50.7 },
    },
    {
      type: 'Feature' as const,
      geometry: {
        type: 'Point' as const,
        coordinates: [-131.4, 67.43] as [number, number],
      },
      properties: { observed_at: '2026-07-21T22:31:00Z', fwi: 18.1 },
    },
  ],
}

describe('hotspotCollectionBounds', () => {
  it('uses the validated extent published with the snapshot', () => {
    const collection = hotspotCollectionSchema.parse({
      ...baseCollection,
      bbox: [-133.893, 32.4016, -112.52, 67.45],
    })

    expect(hotspotCollectionBounds(collection)).toEqual([
      -133.893, 32.4016, -112.52, 67.45,
    ])
  })

  it('derives an extent from features when older snapshots omit bbox', () => {
    const collection = hotspotCollectionSchema.parse(baseCollection)

    expect(hotspotCollectionBounds(collection)).toEqual([
      -131.4, 33.82, -117.25, 67.43,
    ])
  })
})
