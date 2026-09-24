import { useEffect, useMemo, useState, type ReactNode } from 'react'
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
        const likelihoods = periods
          .map((period) =>
            precipitationLikelihood(period.popPercent, period.condition),
          )
          .filter((value): value is string => Boolean(value))
        const pop = likelihoods.find((value) => value.endsWith('%'))
        const wording = likelihoods.find((value) => !value.endsWith('%'))
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
              <small>
                {wording ?? (pop ? `${pop} precipitation` : 'No POP issued')}
              </small>
            </div>
            <div className="daily-amounts">
              {periods.map((period) => (
                <span key={period.start}>
                  {period.temperatureClass === 'low' ? 'Night' : 'Day'}:{' '}
                  <PrecipitationAmount
                    period={period}
                    region={region}
                    precipitation={precipitation}
                  />
                </span>
              ))}
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
  const currentPeriod = selected
    ? (periodAt(selected, now.toISOString()) ?? selected.periods[0])
    : undefined
  const currentTemperature =
    station?.observation.values.temperatureC ?? firstHour?.temperatureC ?? null
  const daily = selected ? forecastDays(selected) : []
  const firstDay = daily[0]?.[1] ?? []
  const high =
    firstDay.find((period) => period.temperatureClass === 'high')
      ?.temperatureC ?? null
  const low =
    firstDay.find((period) => period.temperatureClass === 'low')
      ?.temperatureC ?? null
  const currentCondition = currentPeriod?.condition || 'Forecast unavailable'
  const theme = weatherKind(currentCondition)
  const currentValues = station?.observation.values
  const detailHumidity =
    currentValues?.humidityPercent ?? firstHour?.relativeHumidityPercent ?? null
  const detailWind = currentValues?.windKmh ?? firstHour?.windKmh ?? null
  const detailGust = currentValues?.gustKmh ?? firstHour?.gustKmh ?? null
  const detailPressure = currentValues?.pressureHpa ?? null
  const detailPrecipitation =
    currentValues?.precipitationMm ?? firstHour?.precipitationMm ?? null

  return (
    <main className={`forecast-page forecast-theme-${theme}`}>
      <header className="forecast-topbar">
        <a className="forecast-brand" href="/?buffer=12">
          <AppIcon />
          <span>Weather Model Atlas</span>
        </a>
        <nav aria-label="Main navigation">
          <a href="/?buffer=12">Weather map</a>
          <a href="/forecast" aria-current="page">
            Forecast
          </a>
        </nav>
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
                <p className="hero-kicker">
                  {longDate(now.toISOString())} · Atlantic time
                </p>
                <h1 id="forecast-title">
                  {selected.locality ?? selected.name}
                </h1>
                <div className="hero-weather">
                  <WeatherGlyph
                    condition={currentCondition}
                    night={currentPeriod?.temperatureClass === 'low'}
                    className="hero-weather-icon"
                  />
                  <strong className="hero-temperature">
                    {forecastMetric(currentTemperature, '°')}
                  </strong>
                  <div className="hero-condition">
                    <strong>{currentCondition}</strong>
                    <span>
                      High {forecastMetric(high, '°')} · Low{' '}
                      {forecastMetric(low, '°')}
                    </span>
                  </div>
                </div>
                <p className="hero-source">
                  {station
                    ? `Observed at ${station.name} · ${clock(station.observation.observedAt)} AT`
                    : hourly.isLoading
                      ? 'Loading current conditions…'
                      : 'Current temperature is the nearest available model hour'}
                </p>
              </div>
              <div className="hero-briefing">
                <p>Forecast at a glance</p>
                <strong>
                  {selected.briefing?.overview ??
                    `${currentCondition}. See the hourly and seven-day outlook below.`}
                </strong>
                {selected.briefing && (
                  <span>
                    {selected.briefing.precipitation}{' '}
                    {selected.briefing.temperatures}
                  </span>
                )}
                <a href="/?buffer=12">View weather map →</a>
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
              className="forecast-section"
              aria-labelledby="hourly-title"
              aria-busy={hourly.isFetching}
            >
              <header className="forecast-section-heading">
                <div>
                  <p className="eyebrow">HOUR BY HOUR</p>
                  <h2 id="hourly-title">Next 24 hours</h2>
                </div>
                <p>ECCC GDPS · Updated automatically</p>
              </header>
              {hourly.error && (
                <p role="alert" className="forecast-warning">
                  {hourly.error.message}. The seven-day outlook remains
                  available below.
                </p>
              )}
              {hourly.isLoading && (
                <p className="forecast-empty" role="status">
                  Loading hourly forecasts…
                </p>
              )}
              {hourly.data && (
                <>
                  {hourly.data.hours
                    .slice(0, 24)
                    .some((hour) => hour.status !== 'complete') && (
                    <p className="forecast-warning" role="status">
                      Some forecast hours or values have not been collected.
                      Missing values are shown as dashes; every hour remains
                      listed.
                    </p>
                  )}
                  <div
                    className="hourly-strip"
                    tabIndex={0}
                    role="region"
                    aria-label="Scrollable 24-hour forecast"
                  >
                    {hourly.data.hours.slice(0, 24).map((hour, index) => {
                      const period = periodAt(selected, hour.time)
                      const condition =
                        period?.condition || 'Conditions unavailable'
                      return (
                        <article className="hour-card" key={hour.time}>
                          <time dateTime={hour.time}>
                            {index === 0 ? 'Now' : clock(hour.time)}
                          </time>
                          <WeatherGlyph
                            condition={condition}
                            night={period?.temperatureClass === 'low'}
                          />
                          <strong>
                            {forecastMetric(hour.temperatureC, '°')}
                          </strong>
                          <span className="hour-precipitation">
                            {hour.precipitationMm === null
                              ? '—'
                              : `${hour.precipitationMm.toFixed(1)} mm`}
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
                </>
              )}
            </section>

            <section
              className="forecast-section"
              aria-labelledby="seven-day-title"
            >
              <header className="forecast-section-heading">
                <div>
                  <p className="eyebrow">THE WEEK AHEAD</p>
                  <h2 id="seven-day-title">7-day forecast</h2>
                </div>
                <p>Issued {dateTime(selected.issuedAt)} AT</p>
              </header>
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
                    not provide hourly POP in this feed.
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
