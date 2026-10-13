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

export function activeForecast(
  region: ForecastRegion,
  now: Date,
): ForecastRegion {
  const periods = region.periods.filter(
    (period) => new Date(period.end).getTime() > now.getTime(),
  )
  return {
    ...region,
    periods,
    stale:
      region.stale ||
      now.getTime() - new Date(region.issuedAt).getTime() > 24 * 3600_000 ||
      periods.length === 0,
    briefing:
      region.briefing && new Date(region.briefing.validUntil) > now
        ? region.briefing
        : null,
  }
}

export function forecastDayName(value: string, now: Date) {
  if (forecastDate(value) === forecastDate(now.toISOString())) return 'Today'
  return new Intl.DateTimeFormat('en-CA', {
    timeZone: FORECAST_TIME_ZONE,
    weekday: 'short',
  }).format(new Date(value))
}

export function forecastDays(region: ForecastRegion, now = new Date()) {
  const days = new Map<string, ForecastRegion['periods']>()
  for (const period of region.periods) {
    if (new Date(period.end) <= now) continue
    const date = forecastDate(period.start)
    days.set(date, [...(days.get(date) ?? []), period])
  }
  return [...days.entries()].slice(0, 7)
}
