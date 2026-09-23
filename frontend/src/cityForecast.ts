import type { CityForecastCollection } from './api'
import type { MapBounds } from './mapBounds'

const TWELVE_HOURS_MS = 12 * 60 * 60 * 1000
const SEVEN_DAYS_MS = 7 * 24 * 60 * 60 * 1000

export function cityForecastInBounds(
  [longitude, latitude]: [number, number],
  [west, south, east, north]: MapBounds,
) {
  // A fixed geographic margin would keep distant, offscreen towns labelled
  // even when the user zooms into a single town.
  return (
    longitude >= west &&
    longitude <= east &&
    latitude >= south &&
    latitude <= north
  )
}

export function cityForecastTimes(
  forecast: Pick<CityForecastCollection, 'availableStart' | 'availableEnd'>,
  now = new Date(),
) {
  const availableStart = new Date(forecast.availableStart).getTime()
  const availableEnd = new Date(forecast.availableEnd).getTime()
  const nowTime = now.getTime()
  if (
    !Number.isFinite(availableStart) ||
    !Number.isFinite(availableEnd) ||
    availableStart >= availableEnd ||
    !Number.isFinite(nowTime)
  ) {
    return []
  }
  const roundedNow = new Date(nowTime)
  roundedNow.setUTCMinutes(0, 0, 0)
  const start = Math.max(availableStart, roundedNow.getTime())
  const end = Math.min(availableEnd - 1, start + SEVEN_DAYS_MS)
  const times: string[] = []
  for (let value = start; value <= end; value += TWELVE_HOURS_MS) {
    times.push(new Date(value).toISOString())
  }
  return times
}

export function forecastMetric(
  value: number | null,
  suffix: string,
  digits = 0,
) {
  return value === null ? '—' : `${value.toFixed(digits)}${suffix}`
}
