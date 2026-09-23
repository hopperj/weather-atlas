import { describe, expect, it } from 'vitest'
import {
  cityForecastInBounds,
  cityForecastTimes,
  forecastMetric,
} from './cityForecast'
import type { MapBounds } from './mapBounds'

describe('city forecast presentation', () => {
  const towns: [number, number][] = [
    [-66.12, 43.84], // Yarmouth
    [-63.6, 44.65], // Halifax
    [-63.28, 45.36], // Truro
    [-60.18, 46.13], // Sydney
  ]

  it('shows the provincial overview and narrows to just the towns in a close-up', () => {
    const overview: MapBounds = [-66.7, 43.2, -59.5, 47.2]
    const closeUp: MapBounds = [-63.7, 44.6, -63.5, 44.7]
    expect(
      towns.filter((town) => cityForecastInBounds(town, overview)),
    ).toEqual(towns)
    expect(towns.filter((town) => cityForecastInBounds(town, closeUp))).toEqual(
      [towns[1]],
    )
  })

  it('does not retain offscreen towns within the old 0.6-degree margin', () => {
    expect(
      cityForecastInBounds([-63.6, 44.65], [-63.5, 44.7, -63.4, 44.8]),
    ).toBe(false)
    expect(
      cityForecastInBounds([-63.5, 44.7], [-63.5, 44.7, -63.4, 44.8]),
    ).toBe(true)
  })

  it('builds a bounded seven-day half-day timeline', () => {
    const times = cityForecastTimes(
      {
        availableStart: '2026-07-28T09:00:00Z',
        availableEnd: '2026-08-04T09:00:00Z',
      },
      new Date('2026-07-28T19:00:00Z'),
    )

    expect(times[0]).toBe('2026-07-28T19:00:00.000Z')
    expect(times.at(-1)).toBe('2026-08-04T07:00:00.000Z')
    expect(times).toHaveLength(14)
  })

  it('formats issued values while preserving missing data', () => {
    expect(forecastMetric(24, '°C')).toBe('24°C')
    expect(forecastMetric(null, '%')).toBe('—')
  })
})
