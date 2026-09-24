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

/** Restate recognized ECCC wording; an unpublished POP is neither 0% nor 100%. */
export function precipitationLikelihood(
  popPercent: number | null,
  condition: string,
): string | null {
  if (
    popPercent !== null &&
    Number.isFinite(popPercent) &&
    popPercent >= 0 &&
    popPercent <= 100
  )
    return forecastMetric(popPercent, '%')

  let text = condition.toLowerCase().trim().replace(/\.+$/, '')
  const possible = /^(chance|risk) of /.test(text)
  for (const prefix of ['chance of ', 'risk of ', 'periods of ', 'a few ']) {
    if (text.startsWith(prefix)) text = text.slice(prefix.length)
  }
  let kind: string
  switch (text) {
    case 'rain':
    case 'showers':
    case 'rain showers':
    case 'drizzle':
    case 'rain or drizzle':
    case 'drizzle or rain':
    case 'showers or drizzle':
      kind = 'Rain'
      break
    case 'snow':
    case 'wet snow':
    case 'flurries':
    case 'snow flurries':
    case 'snow showers':
    case 'snow and blowing snow':
      kind = 'Snow'
      break
    case 'rain or snow':
    case 'snow or rain':
    case 'rain mixed with snow':
    case 'snow mixed with rain':
    case 'wet snow mixed with rain':
    case 'flurries or rain showers':
    case 'rain showers or flurries':
    case 'rain showers or wet flurries':
      kind = 'Rain or snow'
      break
    case 'freezing rain':
      kind = 'Freezing rain'
      break
    case 'freezing drizzle':
      kind = 'Freezing drizzle'
      break
    case 'ice pellets':
    case 'sleet':
      kind = 'Ice pellets'
      break
    case 'thunderstorms':
    case 'thundershowers':
      kind = 'Thunderstorms'
      break
    case 'hail':
      kind = 'Hail'
      break
    default:
      return null
  }
  return `${kind} ${possible ? 'possible' : 'expected'}`
}
