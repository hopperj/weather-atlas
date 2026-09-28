import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import {
  forecastApi,
  type ForecastRegion,
  type PrecipitationForecast,
} from './forecastApi'
import { forecastMetric, precipitationLikelihood } from './cityForecast'
import { AppIcon } from './AppIcon'
import {
  FORECAST_TIME_ZONE as TIME_ZONE,
  forecastDate,
  forecastDays,
} from './forecastTime'
import './forecast.css'

type Period = ForecastRegion['periods'][number]
type LocationSelection = {
  regionId: string
  province: string
  scope: 'auto' | 'ns' | 'other'
}

type ForecastColorMode = 'dark' | 'light'

const FORECAST_COLOR_MODE_KEY = 'weather-atlas.forecast-color-mode'

function savedColorMode(): ForecastColorMode {
  try {
    return window.localStorage.getItem(FORECAST_COLOR_MODE_KEY) === 'light'
      ? 'light'
      : 'dark'
  } catch {
    return 'dark'
  }
}

function clock(value: string, timeZone = TIME_ZONE) {
  return new Intl.DateTimeFormat('en-GB', {
    timeZone,
    hour: '2-digit',
    minute: '2-digit',
    hourCycle: 'h23',
  }).format(new Date(value))
}

function dateTime(value: string) {
  return `${forecastDate(value)} ${clock(value)}`
}

function longDate(value: string) {
  return new Intl.DateTimeFormat('en-CA', {
    timeZone: TIME_ZONE,
    weekday: 'long',
    month: 'long',
    day: 'numeric',
  }).format(new Date(value))
}

function dayName(value: string, index: number) {
  if (index === 0) return 'Today'
  return new Intl.DateTimeFormat('en-CA', {
    timeZone: TIME_ZONE,
    weekday: 'short',
  }).format(new Date(value))
}

function weatherKind(condition: string) {
  const value = condition.toLowerCase()
  if (/thunder|storm|lightning/.test(value)) return 'storm'
  if (/freezing rain|ice pellet|sleet/.test(value)) return 'ice'
  if (/snow|flurr/.test(value)) return 'snow'
  if (/rain|shower|drizzle/.test(value)) return 'rain'
  if (/fog|mist|haze/.test(value)) return 'fog'
  if (/partly|mix of sun|clearing|few clouds/.test(value)) return 'partly'
  if (/cloud|overcast/.test(value)) return 'cloud'
  if (/clear|sun/.test(value)) return 'clear'
  return 'unknown'
}

function WeatherGlyph({
  condition,
  night = false,
  className = '',
}: {
  condition: string
  night?: boolean
  className?: string
}) {
  const kind = weatherKind(condition)
  const cloudy = [
    'partly',
    'cloud',
    'rain',
    'snow',
    'storm',
    'ice',
    'fog',
  ].includes(kind)
  return (
    <svg
      viewBox="0 0 96 72"
      className={`weather-glyph weather-glyph-${kind} ${className}`}
      role="img"
      aria-label={condition || 'Weather condition unavailable'}
    >
      {kind === 'clear' || kind === 'partly' ? (
        night ? (
          <path
            className="weather-moon"
            d="M50 8c-13 5-19 20-13 32 5 11 19 16 30 10-6 10-19 15-31 10C20 53 14 34 22 20 28 10 39 5 50 8Z"
          />
        ) : (
          <g className="weather-sun">
            <circle cx="34" cy="28" r="13" />
            <path d="M34 4v8M34 44v8M10 28h8M50 28h8M17 11l6 6M45 39l6 6M17 45l6-6M45 17l6-6" />
          </g>
        )
      ) : null}
      {cloudy ? (
        <path
          className="weather-cloud"
          d="M25 54h43c11 0 17-7 17-15 0-9-7-16-16-16-2 0-4 0-6 1C59 14 50 9 40 11 28 13 20 22 20 34v1C12 37 8 42 9 47c1 5 6 7 16 7Z"
        />
      ) : null}
      {kind === 'rain' || kind === 'storm' || kind === 'ice' ? (
        <g className="weather-rain">
          <path d="M29 59l-4 9M48 59l-4 9M67 59l-4 9" />
        </g>
      ) : null}
      {kind === 'snow' ? (
        <g className="weather-snow">
          <path d="M29 58v11M24 61l10 6M34 61l-10 6M53 58v11M48 61l10 6M58 61l-10 6" />
        </g>
      ) : null}
      {kind === 'storm' ? (
        <path className="weather-bolt" d="M49 49h12l-9 10h8L45 72l4-13h-8Z" />
      ) : null}
      {kind === 'fog' ? (
        <g className="weather-fog">
          <path d="M19 60h58M27 68h43" />
        </g>
      ) : null}
      {kind === 'unknown' ? (
        <text x="48" y="48" textAnchor="middle">
          ?
        </text>
      ) : null}
    </svg>
  )
}

function periodAt(region: ForecastRegion | undefined, value: string) {
  if (!region) return undefined
  const time = new Date(value).getTime()
  return region.periods.find(
    (period) =>
      new Date(period.start).getTime() <= time &&
      time < new Date(period.end).getTime(),
  )
}

function modelEstimate(
  period: Period,
  region: ForecastRegion,
  precipitation?: PrecipitationForecast,
) {
  if (period.precipitationAmount !== null) return null
  if (
    precipitation?.regionId !== region.id ||
    precipitation.issuedAt !== region.issuedAt
  )
    return null
  const estimate = precipitation.periods.find(
    (row) => row.start === period.start && row.end === period.end,
  )
  return estimate?.status === 'complete' &&
    estimate.precipitationMm !== null &&
    estimate.runTime
    ? estimate
    : null
}

function PrecipitationAmount({
  period,
  region,
  precipitation,
}: {
  period: Period
  region: ForecastRegion
  precipitation?: PrecipitationForecast
}) {
  if (period.precipitationAmount !== null)
    return <span>{period.precipitationAmount}</span>
  const estimate = modelEstimate(period, region, precipitation)
  if (!estimate) return <>—</>
  const amount = estimate.precipitationMm!
  return (
    <span
      aria-describedby="model-precipitation-note"
      title={`ECCC GDPS model estimate for ${dateTime(period.start)} to ${dateTime(period.end)} Atlantic; model run ${estimate.runTime}. Sampled at the region's representative location.`}
    >
      {amount > 0 && amount < 0.1 ? '<0.1' : amount.toFixed(1)} mm*
    </span>
  )
}

function DailyForecast({
  region,
  precipitation,
}: {
  region: ForecastRegion
  precipitation?: PrecipitationForecast
}) {
  const days = forecastDays(region)
  if (days.length === 0)
    return (
      <p className="forecast-empty">
        No current seven-day forecast is available for this region. The last
        collected bulletin has expired.
      </p>
    )

  return (
    <div className="daily-forecast-card">
      {days.map(([date, periods], index) => {
        const daytime =
          periods.find((period) => period.temperatureClass === 'high') ??
          periods[0]
        const night = periods.find(
          (period) => period.temperatureClass === 'low',
        )
        const precipitationPeriods = periods.map((period) => ({
          label: period.temperatureClass === 'low' ? 'Night' : 'Day',
          likelihood: precipitationLikelihood(
            period.popPercent,
            period.condition,
          ),
          period,
        }))
        return (
          <article className="daily-row" key={date}>
            <div className="daily-date">
              <strong>{dayName(periods[0].start, index)}</strong>
              <span>
                {new Intl.DateTimeFormat('en-CA', {
                  timeZone: TIME_ZONE,
                  month: 'short',
                  day: 'numeric',
                }).format(new Date(periods[0].start))}
              </span>
            </div>
            <WeatherGlyph
              condition={daytime.condition}
              className="daily-icon"
            />
            <div className="daily-summary">
              <strong>{daytime.condition || 'Condition unavailable'}</strong>
              {night && <span>Night: {night.condition}</span>}
            </div>
            <div className="daily-temperatures" aria-label="High and low">
              <strong>
                {forecastMetric(
                  periods.find((period) => period.temperatureClass === 'high')
                    ?.temperatureC ?? null,
                  '°',
                )}
              </strong>
              <span>
                {forecastMetric(
                  periods.find((period) => period.temperatureClass === 'low')
                    ?.temperatureC ?? null,
                  '°',
                )}
              </span>
            </div>
            <div
              className="daily-pop"
              aria-label="Probability of precipitation"
            >
              {precipitationPeriods.map(({ label, likelihood, period }) => (
                <span key={period.start}>
                  <small>{label}</small>
                  <strong>{likelihood ?? 'Not issued'}</strong>
                </span>
              ))}
            </div>
            <div className="daily-amounts" aria-label="Precipitation totals">
              {precipitationPeriods.map(({ label, period }) => (
                <span key={period.start}>
                  <small>{label}</small>
                  <strong>
                    <PrecipitationAmount
                      period={period}
                      region={region}
                      precipitation={precipitation}
                    />
                  </strong>
                </span>
              ))}
            </div>
          </article>
        )
      })}
    </div>
  )
}

function DetailCard({
  label,
  value,
  note,
}: {
  label: string
  value: ReactNode
  note: string
}) {
  return (
    <article className="weather-detail-card">
      <p>{label}</p>
      <strong>{value}</strong>
      <span>{note}</span>
    </article>
  )
}

export function ForecastPage() {
  const queryClient = useQueryClient()
  const hourlyStripRef = useRef<HTMLDivElement>(null)
  const [colorMode, setColorMode] = useState<ForecastColorMode>(savedColorMode)
  const [location, setLocation] = useState<LocationSelection>(() => {
    const query = new URLSearchParams(window.location.search)
    return {
      regionId: query.get('region') ?? '',
      province: query.get('province') ?? '',
      scope: query.get('scope') === 'other' ? 'other' : 'auto',
    }
  })
  const [now, setNow] = useState(() => new Date())
  const [locating, setLocating] = useState(false)
  const [locationMessage, setLocationMessage] = useState('')
  useEffect(() => {
    try {
      window.localStorage.setItem(FORECAST_COLOR_MODE_KEY, colorMode)
    } catch {
      // The selected mode still applies for this visit when storage is blocked.
    }
  }, [colorMode])
  useEffect(() => {
    const timer = window.setInterval(() => setNow(new Date()), 60_000)
    return () => window.clearInterval(timer)
  }, [])

  const regions = useQuery({
    queryKey: ['forecast-regions'],
    queryFn: ({ signal }) => forecastApi.regions(signal),
    staleTime: 300_000,
    refetchInterval: 300_000,
  })
  const allRegions = regions.data?.regions ?? []
  const nsRegions = allRegions.filter((region) => region.province === 'NS')
  const savedRegion = allRegions.find(
    (region) => region.id === location.regionId,
  )
  const browsingOther =
    location.scope === 'other' ||
    (location.scope === 'auto' &&
      Boolean(savedRegion && savedRegion.province !== 'NS'))
  const otherProvinces = [
    ...new Map(
      allRegions
        .filter((region) => region.province !== 'NS')
        .map((region) => [region.province, region.provinceName]),
    ).entries(),
  ].sort((a, b) => a[1].localeCompare(b[1]))
  const province =
    location.province ||
    (savedRegion?.province !== 'NS' ? savedRegion?.province : '') ||
    ''
  const provinceRegions = allRegions.filter(
    (region) => region.province === province,
  )
  const selected = browsingOther
    ? savedRegion?.province === province && province !== 'NS'
      ? savedRegion
      : undefined
    : (nsRegions.find((region) => region.id === location.regionId) ??
      nsRegions.find((region) => region.name.includes('Halifax Metro')) ??
      nsRegions[0])

  const hourly = useQuery({
    queryKey: ['forecast-hourly', selected?.id, now.toISOString().slice(0, 13)],
    queryFn: ({ signal }) => forecastApi.hourly(selected!.id, signal),
    enabled: Boolean(selected),
    staleTime: 300_000,
    refetchInterval: 300_000,
  })
  const officialHourly = useQuery({
    queryKey: ['forecast-official-hourly', selected?.id],
    queryFn: ({ signal }) => forecastApi.officialHourly(selected!.id, signal),
    enabled: Boolean(selected),
    staleTime: 300_000,
    refetchInterval: 300_000,
    retry: false,
  })
  const precipitation = useQuery({
    queryKey: [
      'forecast-precipitation',
      selected?.id,
      selected?.issuedAt,
      selected?.periods,
    ],
    queryFn: ({ signal }) => forecastApi.precipitation(selected!.id, signal),
    enabled: Boolean(
      selected?.periods.some((period) => period.precipitationAmount === null),
    ),
    staleTime: 300_000,
    refetchInterval: 300_000,
  })
  const observations = useQuery({
    queryKey: [
      'forecast-current',
      selected?.id,
      selected?.longitude,
      selected?.latitude,
    ],
    queryFn: ({ signal }) =>
      forecastApi.nearby(selected!.longitude, selected!.latitude, signal),
    enabled: Boolean(selected),
    staleTime: 300_000,
    refetchInterval: 300_000,
    retry: false,
  })

  const changeLocation = (next: LocationSelection) => {
    setLocation(next)
    const url = new URL(window.location.href)
    for (const key of ['region', 'province', 'scope'])
      url.searchParams.delete(key)
    if (next.regionId) url.searchParams.set('region', next.regionId)
    else if (next.scope === 'other') {
      url.searchParams.set('scope', 'other')
      if (next.province) url.searchParams.set('province', next.province)
    }
    window.history.replaceState(null, '', url)
  }

  const refresh = () => {
    setNow(new Date())
    void queryClient.invalidateQueries({ queryKey: ['forecast-regions'] })
    void queryClient.invalidateQueries({ queryKey: ['forecast-hourly'] })
    void queryClient.invalidateQueries({
      queryKey: ['forecast-official-hourly'],
    })
    void queryClient.invalidateQueries({
      queryKey: ['forecast-precipitation'],
    })
    void queryClient.invalidateQueries({ queryKey: ['forecast-current'] })
  }

  const useCurrentLocation = () => {
    if (!navigator.geolocation) {
      setLocationMessage('Location services are not available in this browser.')
      return
    }
    setLocating(true)
    setLocationMessage('Finding the nearest forecast region…')
    navigator.geolocation.getCurrentPosition(
      ({ coords }) => {
        void forecastApi
          .nearest(coords.longitude, coords.latitude)
          .then((match) => {
            changeLocation({
              scope: match.region.province === 'NS' ? 'ns' : 'other',
              province: match.region.province,
              regionId: match.region.id,
            })
            setLocationMessage(
              `Using ${match.region.name}, ${match.distanceKm.toFixed(1)} km from your location.`,
            )
          })
          .catch((error: unknown) =>
            setLocationMessage(
              error instanceof Error
                ? error.message
                : 'No nearby forecast region was found.',
            ),
          )
          .finally(() => setLocating(false))
      },
      () => {
        setLocating(false)
        setLocationMessage(
          'Location access was not available. Choose a region instead.',
        )
      },
      { enableHighAccuracy: false, timeout: 10_000, maximumAge: 300_000 },
    )
  }

  const station = useMemo(
    () =>
      observations.data?.items.find(
        (item) => !item.stale && item.observation.values.temperatureC !== null,
      ) ?? observations.data?.items[0],
    [observations.data],
  )
  const firstHour = hourly.data?.hours.find((hour) => hour.status !== 'missing')
  const officialHours =
    officialHourly.data &&
    officialHourly.data.regionId === selected?.id &&
    !officialHourly.data.stale
      ? officialHourly.data.hours
      : []
  const officialHoursByTime = new Map(
    officialHours.map((hour) => [hour.time, hour]),
  )
  const currentOfficialHour = officialHours[0]
  const currentPeriod = selected
    ? (periodAt(selected, now.toISOString()) ?? selected.periods[0])
    : undefined
  const currentPrecipitationLikelihood = currentPeriod
    ? currentOfficialHour?.popPercent !== null &&
      currentOfficialHour?.popPercent !== undefined
      ? forecastMetric(currentOfficialHour.popPercent, '%')
      : precipitationLikelihood(
          currentPeriod.popPercent,
          currentPeriod.condition,
        )
    : null
  const currentTemperature =
    station?.observation.values.temperatureC ??
    currentOfficialHour?.temperatureC ??
    firstHour?.temperatureC ??
    null
  const currentFeelsLike = currentOfficialHour?.feelsLikeC ?? null
  const daily = selected ? forecastDays(selected) : []
  const firstDay = daily[0]?.[1] ?? []
  const high =
    firstDay.find((period) => period.temperatureClass === 'high')
      ?.temperatureC ?? null
  const low =
    firstDay.find((period) => period.temperatureClass === 'low')
      ?.temperatureC ?? null
  const currentCondition =
    currentOfficialHour?.condition ||
    currentPeriod?.condition ||
    'Forecast unavailable'
  const theme = weatherKind(currentCondition)
  const currentValues = station?.observation.values
  const detailHumidity =
    currentValues?.humidityPercent ?? firstHour?.relativeHumidityPercent ?? null
  const detailWind =
    currentValues?.windKmh ??
    currentOfficialHour?.windKmh ??
    firstHour?.windKmh ??
    null
  const detailGust =
    currentValues?.gustKmh ??
    currentOfficialHour?.gustKmh ??
    firstHour?.gustKmh ??
    null
  const detailWindDirection = currentOfficialHour?.windDirection ?? null
  const detailPressure = currentValues?.pressureHpa ?? null
  const detailPrecipitation =
    currentValues?.precipitationMm ?? firstHour?.precipitationMm ?? null
  const displayedHours =
    hourly.data?.hours.slice(0, 24) ??
    officialHours.map((hour) => ({
      time: hour.time,
      runTime: null,
      precipitationStart: hour.time,
      status: 'missing' as const,
      temperatureC: null,
      relativeHumidityPercent: null,
      precipitationMm: null,
      windKmh: null,
      gustKmh: null,
    }))

  return (
    <main
      className={`forecast-page forecast-color-${colorMode} forecast-theme-${theme}`}
    >
      <header className="forecast-topbar">
        <a className="forecast-brand" href="/?buffer=12">
          <AppIcon />
          <span>Weather Model Atlas</span>
        </a>
        <div className="forecast-topbar-actions">
          <nav aria-label="Main navigation">
            <a href="/?buffer=12">Weather map</a>
            <a href="/forecast" aria-current="page">
              Forecast
            </a>
          </nav>
          <details className="forecast-settings">
            <summary>Settings</summary>
            <div className="forecast-settings-panel">
              <label htmlFor="forecast-color-mode">Appearance</label>
              <select
                id="forecast-color-mode"
                value={colorMode}
                onChange={(event) =>
                  setColorMode(event.target.value as ForecastColorMode)
                }
              >
                <option value="dark">Dark</option>
                <option value="light">Light</option>
              </select>
              <small>Saved on this device.</small>
            </div>
          </details>
        </div>
      </header>

      <div className="forecast-content">
        <section
          className="forecast-location-card"
          aria-label="Forecast location"
        >
          <div className="location-heading">
            <span className="location-pin" aria-hidden="true">
              ⌖
            </span>
            <div>
              <p>Forecast location</p>
              <strong>
                {selected
                  ? `${selected.locality ?? selected.name}, ${selected.province}`
                  : 'Choose a region'}
              </strong>
            </div>
          </div>
          <div className="forecast-location">
            <label htmlFor="forecast-region">Forecast region</label>
            <select
              id="forecast-region"
              value={browsingOther ? 'other' : (selected?.id ?? '')}
              onChange={(event) =>
                changeLocation(
                  event.target.value === 'other'
                    ? { scope: 'other', province: '', regionId: '' }
                    : {
                        scope: 'ns',
                        province: 'NS',
                        regionId: event.target.value,
                      },
                )
              }
              disabled={allRegions.length === 0}
              aria-describedby="forecast-selector-hint"
            >
              {!selected && !browsingOther && (
                <option value="">
                  {regions.isLoading
                    ? 'Loading regions…'
                    : allRegions.length
                      ? 'Select a region…'
                      : 'No regions available'}
                </option>
              )}
              {nsRegions.map((region) => (
                <option key={region.id} value={region.id}>
                  {region.name}
                </option>
              ))}
              {otherProvinces.length > 0 && (
                <option value="other">Other province or territory…</option>
              )}
            </select>
            <p id="forecast-selector-hint" className="visually-hidden">
              Nova Scotia regions are listed first. Choose Other to explore the
              rest of Canada.
            </p>
            {browsingOther && (
              <div className="forecast-other-location">
                <label htmlFor="forecast-province">Province or territory</label>
                <select
                  id="forecast-province"
                  value={province}
                  onChange={(event) =>
                    changeLocation({
                      scope: 'other',
                      province: event.target.value,
                      regionId: '',
                    })
                  }
                >
                  <option value="">Select a province or territory…</option>
                  {otherProvinces.map(([code, name]) => (
                    <option key={code} value={code}>
                      {name}
                    </option>
                  ))}
                </select>
                <label htmlFor="forecast-other-region">Region</label>
                <select
                  id="forecast-other-region"
                  value={selected?.id ?? ''}
                  disabled={!province || provinceRegions.length === 0}
                  onChange={(event) =>
                    changeLocation({
                      scope: 'other',
                      province,
                      regionId: event.target.value,
                    })
                  }
                >
                  <option value="">
                    {province
                      ? 'Select a region…'
                      : 'Choose a province or territory first'}
                  </option>
                  {provinceRegions.map((region) => (
                    <option key={region.id} value={region.id}>
                      {region.name}
                    </option>
                  ))}
                </select>
              </div>
            )}
          </div>
          <div className="location-actions">
            <button
              type="button"
              onClick={useCurrentLocation}
              disabled={locating}
            >
              {locating ? 'Locating…' : 'Use my location'}
            </button>
            <button
              type="button"
              className="icon-button"
              onClick={refresh}
              disabled={
                regions.isFetching ||
                hourly.isFetching ||
                precipitation.isFetching ||
                observations.isFetching
              }
              aria-label="Refresh forecasts"
              title="Refresh forecasts"
            >
              ↻
            </button>
          </div>
          <p className="visually-hidden" role="status">
            {selected
              ? `Viewing ${selected.name}, ${selected.provinceName}`
              : 'No forecast region selected'}
          </p>
          {locationMessage && (
            <p className="location-message" role="status">
              {locationMessage}
            </p>
          )}
        </section>

        {regions.error && (
          <p role="alert" className="forecast-warning">
            {regions.error.message}. Check that the forecast service and
            collection are running.
          </p>
        )}

        {selected ? (
          <>
            <section className="forecast-hero" aria-labelledby="forecast-title">
              <div className="hero-atmosphere" aria-hidden="true" />
              <div className="hero-copy">
                <div className="hero-heading">
                  <div>
                    <h1 id="forecast-title">
                      {selected.locality ?? selected.name}
                    </h1>
                    <span className="hero-province">
                      {selected.provinceName}
                    </span>
                  </div>
                  <p className="hero-kicker">
                    {longDate(now.toISOString())} · Atlantic time
                  </p>
                </div>
                <div className="hero-dashboard">
                  <div className="hero-weather">
                    <WeatherGlyph
                      condition={currentCondition}
                      night={currentPeriod?.temperatureClass === 'low'}
                      className="hero-weather-icon"
                    />
                    <div className="hero-temperature-group">
                      <strong className="hero-temperature">
                        {forecastMetric(currentTemperature, '°')}
                      </strong>
                      <div className="hero-condition">
                        <strong>{currentCondition}</strong>
                        {currentFeelsLike !== null && (
                          <span>
                            Feels like {forecastMetric(currentFeelsLike, '°')}
                          </span>
                        )}
                      </div>
                    </div>
                  </div>
                  <div className="hero-metrics">
                    <div className="hero-metric">
                      <span>High / Low</span>
                      <strong>
                        {forecastMetric(high, '°')} / {forecastMetric(low, '°')}
                      </strong>
                    </div>
                    <div className="hero-metric">
                      <span>Humidity</span>
                      <strong>{forecastMetric(detailHumidity, '%')}</strong>
                    </div>
                    <div className="hero-metric">
                      <span>Wind</span>
                      <strong>
                        {detailWindDirection ? `${detailWindDirection} ` : ''}
                        {forecastMetric(detailWind, ' km/h')}
                      </strong>
                      {detailGust !== null && (
                        <small>Gusts {detailGust.toFixed(0)} km/h</small>
                      )}
                    </div>
                    <div
                      className="hero-precipitation"
                      aria-label="Current forecast precipitation"
                    >
                      <div className="hero-metric hero-metric-precipitation">
                        <span title="Probability of precipitation">
                          POP
                          {currentOfficialHour
                            ? ` · ${clock(currentOfficialHour.time)}`
                            : ' · current period'}
                        </span>
                        <strong>
                          {currentPrecipitationLikelihood ?? 'Not issued'}
                        </strong>
                      </div>
                      <div className="hero-metric hero-metric-precipitation">
                        <span>Period precipitation</span>
                        <strong>
                          {currentPeriod ? (
                            <PrecipitationAmount
                              period={currentPeriod}
                              region={selected}
                              precipitation={precipitation.data}
                            />
                          ) : (
                            '—'
                          )}
                        </strong>
                      </div>
                    </div>
                  </div>
                </div>
                <div className="hero-footer">
                  <p className="hero-source">
                    {station
                      ? `Observed at ${station.name} · ${clock(station.observation.observedAt)} AT · temperature and station details`
                      : currentOfficialHour
                        ? `ECCC hourly forecast for ${clock(currentOfficialHour.time)} AT`
                        : hourly.isLoading
                          ? 'Loading current conditions…'
                          : 'Current temperature is the nearest available model hour'}
                  </p>
                  <p className="hero-summary">
                    {selected.briefing?.overview ??
                      `${currentCondition}. See the hourly and seven-day outlook below.`}
                  </p>
                  <a href="/?buffer=12">View weather map →</a>
                </div>
              </div>
            </section>

            {selected.stale && (
              <p className="forecast-warning" role="status">
                Forecast update overdue. Last issue:{' '}
                {dateTime(selected.issuedAt)} Atlantic time. Collection needs to
                resume before this outlook can be considered current.
              </p>
            )}

            <section
              className="forecast-section forecast-section-card forecast-hourly-section"
              aria-labelledby="hourly-title"
              aria-busy={hourly.isFetching}
            >
              <header className="forecast-section-heading">
                <div className="forecast-section-title">
                  <p className="eyebrow">HOUR BY HOUR</p>
                  <div className="forecast-section-title-line">
                    <h2 id="hourly-title">Next 24 hours</h2>
                    <p>ECCC official hourly · GDPS amounts</p>
                  </div>
                </div>
                <div
                  className="hourly-navigation"
                  aria-label="Hourly forecast navigation"
                >
                  <button
                    type="button"
                    onClick={() =>
                      hourlyStripRef.current?.scrollBy({
                        left: -560,
                        behavior: 'smooth',
                      })
                    }
                    aria-label="Earlier forecast hours"
                  >
                    ‹
                  </button>
                  <button
                    type="button"
                    onClick={() =>
                      hourlyStripRef.current?.scrollBy({
                        left: 560,
                        behavior: 'smooth',
                      })
                    }
                    aria-label="Later forecast hours"
                  >
                    ›
                  </button>
                </div>
              </header>
              {hourly.error && (
                <p role="alert" className="forecast-warning">
                  {hourly.error.message}. Official hourly values remain
                  available when collected.
                </p>
              )}
              {hourly.isLoading && (
                <p className="forecast-empty" role="status">
                  Loading hourly forecasts…
                </p>
              )}
              {(officialHourly.error || officialHourly.data?.stale) && (
                <p className="forecast-warning" role="status">
                  Official hourly conditions and POP are{' '}
                  {officialHourly.data?.stale ? 'out of date' : 'unavailable'}.
                  Model values remain visible.
                </p>
              )}
              {displayedHours.length > 0 && (
                <>
                  {displayedHours.some(
                    (hour) => hour.status !== 'complete',
                  ) && (
                    <p className="forecast-warning" role="status">
                      Some GDPS model hours or values have not been collected.
                      Official hourly values remain visible where available.
                    </p>
                  )}
                  <div
                    className="hourly-strip"
                    ref={hourlyStripRef}
                    tabIndex={0}
                    role="region"
                    aria-label="Scrollable 24-hour forecast"
                  >
                    {displayedHours.map((hour, index) => {
                      const period = periodAt(selected, hour.time)
                      const official = officialHoursByTime.get(hour.time)
                      const condition =
                        official?.condition ||
                        period?.condition ||
                        'Conditions unavailable'
                      return (
                        <article
                          className={`hour-card${index === 0 ? ' hour-card-current' : ''}`}
                          key={hour.time}
                        >
                          <div className="hour-time">
                            <time dateTime={hour.time}>{clock(hour.time)}</time>
                            {index === 0 && <span>Now</span>}
                          </div>
                          <WeatherGlyph
                            condition={condition}
                            night={period?.temperatureClass === 'low'}
                          />
                          <span className="hour-condition">{condition}</span>
                          <strong>
                            {forecastMetric(
                              official?.temperatureC ?? hour.temperatureC,
                              '°',
                            )}
                          </strong>
                          <span className="hour-pop">
                            {official?.popPercent === null ||
                            official?.popPercent === undefined
                              ? 'POP —'
                              : `POP ${official.popPercent.toFixed(0)}%`}
                          </span>
                          <span className="hour-precipitation">
                            {hour.precipitationMm === null
                              ? 'GDPS amount —'
                              : `GDPS ${hour.precipitationMm.toFixed(1)} mm`}
                          </span>
                          <small>
                            {hour.relativeHumidityPercent === null
                              ? 'Humidity —'
                              : `${hour.relativeHumidityPercent.toFixed(0)}% humidity`}
                          </small>
                        </article>
                      )
                    })}
                  </div>
                  <p className="hourly-source-legend">
                    POP and conditions: ECCC official hourly forecast · Amounts:
                    GDPS point forecast
                  </p>
                </>
              )}
            </section>

            <section
              className="forecast-section forecast-section-card forecast-daily-section"
              aria-labelledby="seven-day-title"
            >
              <header className="forecast-section-heading">
                <div>
                  <p className="eyebrow">THE WEEK AHEAD</p>
                  <h2 id="seven-day-title">7-day forecast</h2>
                </div>
                <p>Issued {dateTime(selected.issuedAt)} AT</p>
              </header>
              <div className="daily-column-headings" aria-hidden="true">
                <span>Day</span>
                <span>Conditions</span>
                <span>High / Low</span>
                <span>POP</span>
                <span>Precipitation (total)</span>
              </div>
              <DailyForecast
                region={selected}
                precipitation={precipitation.data}
              />
              <p className="forecast-note" id="model-precipitation-note">
                * Model estimate (ECCC GDPS), used only when the ECCC bulletin
                has no amount. It covers the full day or night period in mm of
                water equivalent. A dash means an amount is unavailable.
              </p>
              {precipitation.isLoading && (
                <p className="forecast-note" role="status">
                  Estimating missing precipitation amounts…
                </p>
              )}
              {precipitation.error && (
                <p className="forecast-warning" role="status">
                  Model precipitation estimates could not be refreshed. ECCC
                  bulletin values remain available. Try Refresh forecasts.
                </p>
              )}
            </section>

            <section
              className="forecast-section"
              aria-labelledby="details-title"
            >
              <header className="forecast-section-heading">
                <div>
                  <p className="eyebrow">RIGHT NOW</p>
                  <h2 id="details-title">Weather details</h2>
                </div>
                <p>
                  {station
                    ? `${station.name} · ${station.distanceKm ?? '—'} km away`
                    : 'Nearest station or model estimate'}
                </p>
              </header>
              <div className="weather-details-grid">
                <DetailCard
                  label="Humidity"
                  value={forecastMetric(detailHumidity, '%')}
                  note={
                    station ? 'Observed relative humidity' : 'Model estimate'
                  }
                />
                <DetailCard
                  label="Wind"
                  value={forecastMetric(detailWind, ' km/h')}
                  note={
                    detailGust === null
                      ? 'No gust reported'
                      : `Gusting to ${detailGust.toFixed(0)} km/h`
                  }
                />
                <DetailCard
                  label="Pressure"
                  value={forecastMetric(detailPressure, ' hPa', 1)}
                  note={
                    station ? 'Mean sea-level pressure' : 'Station unavailable'
                  }
                />
                <DetailCard
                  label="Precipitation"
                  value={forecastMetric(detailPrecipitation, ' mm', 1)}
                  note={
                    currentValues?.precipitationMm !== null &&
                    currentValues?.precipitationMm !== undefined
                      ? 'Observed recent accumulation'
                      : 'Model amount for this hour'
                  }
                />
              </div>
              {station && (
                <p className="forecast-note">
                  Current readings: {station.attribution}. Conditions and daily
                  highs/lows come from the regional forecast.
                </p>
              )}
              {observations.error && (
                <p className="forecast-note" role="status">
                  A nearby observation was not available, so current details use
                  the nearest model hour where possible.
                </p>
              )}
            </section>

            {hourly.data && (
              <details className="forecast-data-details">
                <summary>
                  <span>
                    <h2>72-hour forecast</h2>
                    <small>All model values and run information</small>
                  </span>
                  <span aria-hidden="true">＋</span>
                </summary>
                <div className="forecast-data-body">
                  <p className="forecast-note">
                    Times for all regions are shown in Atlantic time (
                    {TIME_ZONE}), using a 24-hour clock. Values are sampled at
                    the centre of the selected region. Precipitation is the
                    amount in the hour ending at the displayed time. GDPS does
                    not provide hourly POP in this feed; official POP and
                    conditions come from ECCC's separate public hourly forecast.
                  </p>
                  <div
                    className="hourly-table-scroll"
                    tabIndex={0}
                    role="region"
                    aria-label="Scrollable 72-hour forecast"
                  >
                    <table className="hourly-forecast-table">
                      <caption>
                        {selected.name}, {selected.provinceName} ·{' '}
                        {dateTime(hourly.data.start)} to{' '}
                        {dateTime(hourly.data.end)} Atlantic
                      </caption>
                      <thead>
                        <tr>
                          <th scope="col">Date & time</th>
                          <th scope="col">Temp (°C)</th>
                          <th scope="col">Hum (%)</th>
                          <th scope="col">Precip (mm / 1h)</th>
                          <th scope="col">Wind (km/h)</th>
                          <th scope="col">Gust (km/h)</th>
                          <th scope="col">Availability</th>
                          <th scope="col">Model run (UTC)</th>
                        </tr>
                      </thead>
                      <tbody>
                        {hourly.data.hours.map((hour, index, hours) => (
                          <tr
                            key={hour.time}
                            className={
                              index === 0 ||
                              forecastDate(hour.time) !==
                                forecastDate(hours[index - 1].time)
                                ? 'hourly-day-start'
                                : ''
                            }
                          >
                            <th scope="row">
                              <time dateTime={hour.time}>
                                {dateTime(hour.time)}
                              </time>
                            </th>
                            <td className="hourly-temperature">
                              {forecastMetric(hour.temperatureC, '')}
                            </td>
                            <td>
                              {forecastMetric(hour.relativeHumidityPercent, '')}
                            </td>
                            <td>
                              {forecastMetric(hour.precipitationMm, '', 1)}
                            </td>
                            <td>{forecastMetric(hour.windKmh, '')}</td>
                            <td>{forecastMetric(hour.gustKmh, '')}</td>
                            <td>
                              <span className={`hour-status ${hour.status}`}>
                                {hour.status === 'missing'
                                  ? 'Not available'
                                  : hour.status === 'partial'
                                    ? 'Partial'
                                    : 'Complete'}
                              </span>
                            </td>
                            <td className="hour-run">
                              {hour.runTime
                                ? `${forecastDate(hour.runTime, 'UTC')} ${clock(hour.runTime, 'UTC')}`
                                : '—'}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  <p className="forecast-note">
                    {hourly.data.availableHours} / 72 hours available ·{' '}
                    {hourly.data.completeHours} complete. Each row uses one GDPS
                    run; forecast gaps are not interpolated.
                  </p>
                </div>
              </details>
            )}
          </>
        ) : (
          <p className="forecast-empty" role="status">
            {regions.isLoading
              ? 'Loading the forecast…'
              : browsingOther
                ? 'Choose a province or territory and a region above to see its forecast.'
                : 'No regional forecast is available.'}
          </p>
        )}

        <footer className="forecast-footer">
          <span>
            Official and model data from Environment and Climate Change Canada.
          </span>
          <span>
            <a href="https://eccc-msc.github.io/open-data/msc-data/citypage-weather/readme_citypageweather-datamart_en/">
              Regional forecasts
            </a>{' '}
            ·{' '}
            <a href="https://eccc-msc.github.io/open-data/msc-data/nwp_gdps/readme_gdps-datamart_en/">
              GDPS model data
            </a>
          </span>
        </footer>
      </div>
    </main>
  )
}
