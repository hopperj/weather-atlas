import { describe, expect, it } from 'vitest'
import { activeForecast, forecastDayName, forecastDays } from './forecastTime'
import type { ForecastRegion } from './forecastApi'

const region: ForecastRegion = {
  id: '0123456789abcdef',
  name: 'Halifax',
  province: 'NS',
  provinceName: 'Nova Scotia',
  latitude: 44.65,
  longitude: -63.6,
  issuedAt: '2026-10-09T08:00:00Z',
  stale: false,
  periods: [
    {
      name: 'Friday',
      start: '2026-10-09T08:00:00Z',
      end: '2026-10-09T21:00:00Z',
      temperatureC: 17,
      temperatureClass: 'high',
      relativeHumidityPercent: 60,
      popPercent: 60,
      precipitationAmount: '10 mm',
      condition: 'Showers',
    },
    {
      name: 'Friday night',
      start: '2026-10-09T21:00:00Z',
      end: '2026-10-10T09:00:00Z',
      temperatureC: 6,
      temperatureClass: 'low',
      relativeHumidityPercent: 75,
      popPercent: 60,
      precipitationAmount: null,
      condition: 'Chance of showers',
    },
    {
      name: 'Saturday',
      start: '2026-10-10T09:00:00Z',
      end: '2026-10-10T21:00:00Z',
      temperatureC: 11,
      temperatureClass: 'high',
      relativeHumidityPercent: 50,
      popPercent: null,
      precipitationAmount: null,
      condition: 'Sunny',
    },
  ],
}

describe('forecast freshness against the display clock', () => {
  it('changes Today at local midnight without discarding the still-valid overnight forecast', () => {
    const before = new Date('2026-10-10T02:59:00Z')
    const after = new Date('2026-10-10T03:01:00Z')
    expect(forecastDayName(region.periods[1].start, before)).toBe('Today')
    expect(forecastDayName(region.periods[1].start, after)).toBe('Fri')
    expect(forecastDayName(region.periods[2].start, after)).toBe('Today')
    expect(forecastDays(region, after)[0][1]).toEqual([region.periods[1]])
    expect(activeForecast(region, after).periods).not.toContain(
      region.periods[0],
    )
  })
  it('expires saved data even if the server originally marked it fresh', () => {
    const now = new Date('2026-10-19T12:00:00Z')
    const active = activeForecast(region, now)
    expect(active.stale).toBe(true)
    expect(active.periods).toEqual([])
    expect(forecastDays(active, now)).toEqual([])
    expect(forecastDayName(region.periods[0].start, now)).toBe('Fri')
  })
})
