import type { ForecastRegion } from './forecastApi'

export const FORECAST_TIME_ZONE = 'America/Halifax'

export function forecastDate(value: string, timeZone = FORECAST_TIME_ZONE) {
  return new Intl.DateTimeFormat('en-CA', {
    timeZone,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).format(new Date(value))
}

export function forecastDays(region: ForecastRegion) {
  const days = new Map<string, ForecastRegion['periods']>()
  for (const period of region.periods) {
    const date = forecastDate(period.start)
    days.set(date, [...(days.get(date) ?? []), period])
  }
  return [...days.entries()].slice(0, 7)
}
