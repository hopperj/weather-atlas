import { useEffect, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import {
  forecastApi,
  type ForecastRegion,
  type PrecipitationForecast,
} from './forecastApi'
import { forecastMetric } from './cityForecast'
import { AppIcon } from './AppIcon'
import {
  FORECAST_TIME_ZONE as TIME_ZONE,
  forecastDate,
  forecastDays,
} from './forecastTime'
import './forecast.css'

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

function Outlook({
  region,
  precipitation,
}: {
  region: ForecastRegion
  precipitation?: PrecipitationForecast
}) {
  const days = forecastDays(region)
  const estimates =
    precipitation?.regionId === region.id &&
    precipitation.issuedAt === region.issuedAt
      ? precipitation.periods
      : []
  function precipitationAmount(period: ForecastRegion['periods'][number]) {
    if (period.precipitationAmount !== null) return period.precipitationAmount
    const estimate = estimates.find(
      (row) => row.start === period.start && row.end === period.end,
    )
    if (
      estimate?.status !== 'complete' ||
      estimate.precipitationMm === null ||
      !estimate.runTime
    )
      return '—'
    const amount = estimate.precipitationMm
    return (
      <span
        aria-describedby="model-precipitation-note"
        title={`ECCC GDPS model estimate for ${dateTime(period.start)} to ${dateTime(period.end)} Atlantic; model run ${estimate.runTime}. Sampled at the region's representative location.`}
      >
        {amount > 0 && amount < 0.1 ? '<0.1' : amount.toFixed(1)} mm*
      </span>
    )
  }
  return (
    <>
      {region.stale && (
        <p className="forecast-warning" role="status">
          Forecast update overdue. Last issue: {dateTime(region.issuedAt)}{' '}
          Atlantic time. Collection needs to resume before this outlook can be
          considered current.
        </p>
      )}
      {days.length === 0 ? (
        <p className="forecast-empty">
          No current seven-day forecast is available for this region. The last
          collected bulletin has expired.
        </p>
      ) : (
        <div className="outlook-days">
          {days.map(([date, periods]) => (
            <article className="outlook-day" key={date}>
              <header>
                <h3>
                  {new Intl.DateTimeFormat('en-CA', {
                    timeZone: TIME_ZONE,
                    weekday: 'long',
                  }).format(new Date(periods[0].start))}
                </h3>
                <time>{date}</time>
              </header>
              {periods.map((period) => (
                <section key={period.start} className="outlook-period">
                  <h4>{period.name}</h4>
                  <strong className="outlook-temperature">
                    {forecastMetric(period.temperatureC, '°C')}
                    <small>{period.temperatureClass ?? 'Temp'}</small>
                  </strong>
                  <p className="outlook-condition">
                    {period.condition || 'Condition not issued'}
                  </p>
                  <dl>
                    <div>
                      <dt>Hum:</dt>
                      <dd>
                        {forecastMetric(period.relativeHumidityPercent, '%')}
                      </dd>
                    </div>
                    <div>
                      <dt>POP:</dt>
                      <dd>{forecastMetric(period.popPercent, '%')}</dd>
                    </div>
                    <div>
                      <dt>Precip Amount:</dt>
                      <dd>{precipitationAmount(period)}</dd>
                    </div>
                  </dl>
                </section>
              ))}
            </article>
          ))}
        </div>
      )}
    </>
  )
}

export function ForecastPage() {
  const queryClient = useQueryClient()
  const [location, setLocation] = useState(() => {
    const query = new URLSearchParams(window.location.search)
    return {
      regionId: query.get('region') ?? '',
      province: query.get('province') ?? '',
      scope: query.get('scope') === 'other' ? 'other' : 'auto',
    }
  })
  const [now, setNow] = useState(() => new Date())
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
  const changeLocation = (next: typeof location) => {
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
    void queryClient.invalidateQueries({ queryKey: ['forecast-precipitation'] })
  }

  return (
    <main className="forecast-page">
      <header className="forecast-topbar">
        <a className="forecast-brand" href="/?buffer=12">
          <AppIcon />
          Weather Model Atlas
        </a>
        <nav aria-label="Main navigation">
          <a href="/?buffer=12">Weather map</a>
          <a href="/forecast" aria-current="page">
            Forecast
          </a>
        </nav>
      </header>
      <div className="forecast-content">
        <section className="forecast-intro">
          <div>
            <p className="eyebrow">
              {selected?.provinceName.toUpperCase() ?? 'NOVA SCOTIA FIRST'} ·
              ECCC WEATHER
            </p>
            <h1>Your local forecast</h1>
            <p>
              The week ahead, with an hour-by-hour view of the next three days.
            </p>
            {selected && (
              <p className="forecast-selected-location" role="status">
                Viewing {selected.name}, {selected.provinceName}
              </p>
            )}
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
            <p id="forecast-selector-hint" className="forecast-selector-hint">
              Nova Scotia regions are one selection away. Choose Other to
              explore the rest of Canada.
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
            <button
              type="button"
              onClick={refresh}
              disabled={
                regions.isFetching ||
                hourly.isFetching ||
                precipitation.isFetching
              }
            >
              Refresh forecasts
            </button>
          </div>
        </section>
        {regions.error && (
          <p role="alert" className="forecast-warning">
            {regions.error.message}. Check that the forecast service and
            collection are running.
          </p>
        )}
        <section className="forecast-section" aria-labelledby="seven-day-title">
          <header className="forecast-section-heading">
            <div>
              <p className="eyebrow">THE WEEK AHEAD</p>
              <h2 id="seven-day-title">7-day forecast</h2>
            </div>
            <p>
              ECCC regional outlook
              {selected
                ? ` · Issued ${dateTime(selected.issuedAt)} Atlantic`
                : ''}
            </p>
          </header>
          {selected ? (
            <Outlook region={selected} precipitation={precipitation.data} />
          ) : (
            <p className="forecast-empty" role="status">
              {regions.isLoading
                ? 'Loading the seven-day outlook…'
                : browsingOther
                  ? 'Choose a province or territory and a region above to see its forecast.'
                  : 'No regional forecast is available.'}
            </p>
          )}
          <p className="forecast-note">
            Daily temperatures are forecast highs or lows. POP is the
            probability of precipitation. A dash means a value is unavailable.
          </p>
          <p className="forecast-note" id="model-precipitation-note">
            * Model estimate (ECCC GDPS), used only when the ECCC bulletin has
            no amount. Each estimate covers the full day or night period at the
            region’s representative location, in mm of water equivalent (rain
            plus melted snow, not snow depth). A dash remains if the model
            cannot cover the entire period.
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
          aria-labelledby="hourly-title"
          aria-busy={hourly.isFetching}
        >
          <header className="forecast-section-heading">
            <div>
              <p className="eyebrow">THE NEXT THREE DAYS</p>
              <h2 id="hourly-title">72-hour forecast</h2>
            </div>
            <p>
              {hourly.data
                ? `${hourly.data.availableHours} / 72 hours available · ${hourly.data.completeHours} complete`
                : 'ECCC GDPS · Hourly model forecast'}
            </p>
          </header>
          <p className="forecast-note">
            Times for all regions are shown in Atlantic time ({TIME_ZONE}),
            using a 24-hour clock. Values are sampled at the centre of the
            selected region. Precipitation is the amount in the hour ending at
            the displayed time. GDPS does not provide hourly POP in this feed.
          </p>
          {hourly.error && (
            <p role="alert" className="forecast-warning">
              {hourly.error.message}. The seven-day outlook remains available
              above.
            </p>
          )}
          {hourly.isLoading && (
            <p className="forecast-empty" role="status">
              Loading hourly forecasts…
            </p>
          )}
          {hourly.data && (
            <>
              {hourly.data.completeHours < 72 && (
                <p className="forecast-warning" role="status">
                  Some forecast hours or values have not been collected. Missing
                  values are shown as dashes; every hour remains listed.
                </p>
              )}
              <div
                className="hourly-table-scroll"
                tabIndex={0}
                role="region"
                aria-label="Scrollable 72-hour forecast"
              >
                <table className="hourly-forecast-table">
                  <caption>
                    {selected?.name}, {selected?.provinceName} ·{' '}
                    {dateTime(hourly.data.start)} to {dateTime(hourly.data.end)}{' '}
                    Atlantic
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
                        <td>{forecastMetric(hour.precipitationMm, '', 1)}</td>
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
                The current hour and following 71 hours are shown. Each row uses
                one GDPS run; its issue time is listed above. Forecast gaps are
                not interpolated.
              </p>
            </>
          )}
          {!selected && !regions.isLoading && (
            <p className="forecast-empty">
              Select an available forecast region to load hourly data.
            </p>
          )}
        </section>
        <footer className="forecast-footer">
          Source: Environment and Climate Change Canada ·
          <a href="https://eccc-msc.github.io/open-data/msc-data/citypage-weather/readme_citypageweather-datamart_en/">
            {' '}
            Regional forecasts
          </a>{' '}
          ·
          <a href="https://eccc-msc.github.io/open-data/msc-data/nwp_gdps/readme_gdps-datamart_en/">
            {' '}
            GDPS model data
          </a>
        </footer>
      </div>
    </main>
  )
}
