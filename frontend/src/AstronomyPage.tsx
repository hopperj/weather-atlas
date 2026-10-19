import { useEffect, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import maplibregl from 'maplibre-gl'
import { AppIcon } from './AppIcon'
import { weatherBasemapStyle } from './mapPresentation'
import {
  astronomyForecast,
  initialObservingSite,
  initialAstronomyOptions,
  observingSiteSchema,
  restoreSites,
  type AstronomyFrame,
  type AstronomyOptions,
  type ObservingSite,
} from './astronomyApi'
import './astronomy.css'

function persist(key: string, value: unknown) {
  try {
    localStorage.setItem(key, JSON.stringify(value))
  } catch {
    /* This visit still works without storage. */
  }
}
function clock(value: string | null | undefined, zone: string, date = false) {
  if (!value) return 'No event this night'
  return new Intl.DateTimeFormat('en-GB', {
    timeZone: zone,
    hour: '2-digit',
    minute: '2-digit',
    hourCycle: 'h23',
    ...(date ? { weekday: 'short', day: 'numeric', month: 'short' } : {}),
  }).format(new Date(value))
}
const rows: { key: keyof AstronomyFrame; label: string; unit: string }[] = [
  { key: 'cloudPercent', label: 'Total cloud', unit: '%' },
  { key: 'sunAltitudeDegrees', label: 'Sun altitude', unit: '°' },
  { key: 'moonAltitudeDegrees', label: 'Moon altitude', unit: '°' },
  { key: 'moonIlluminatedPercent', label: 'Moon lit', unit: '%' },
  { key: 'temperatureC', label: 'Temperature', unit: '°C' },
  { key: 'humidityPercent', label: 'Humidity', unit: '%' },
  { key: 'dewPointC', label: 'Dew point', unit: '°C' },
  { key: 'windKmh', label: 'Wind', unit: 'km/h' },
  { key: 'gustKmh', label: 'Gusts', unit: 'km/h' },
  { key: 'rainMm', label: 'Precipitation¹', unit: 'mm' },
]

export function AstronomyPage() {
  const [site, setSite] = useState(initialObservingSite)
  const [saved, setSaved] = useState(() =>
    restoreSites('weather-atlas.astronomy.saved'),
  )
  const [options, setOptions] = useState<AstronomyOptions>(
    initialAstronomyOptions,
  )
  const [effectiveOptions, setEffectiveOptions] = useState(options)
  const settling = JSON.stringify(options) !== JSON.stringify(effectiveOptions)
  useEffect(() => {
    const timer = window.setTimeout(() => setEffectiveOptions(options), 300)
    return () => window.clearTimeout(timer)
  }, [options])
  const [nightIndex, setNightIndex] = useState(0)
  const [nightOnly, setNightOnly] = useState(true)
  const [red, setRed] = useState(false)
  const [picking, setPicking] = useState(false)
  const [following, setFollowing] = useState(() => {
    try {
      return (
        JSON.parse(
          localStorage.getItem('weather-atlas.astronomy.gps') ?? 'false',
        ) === true
      )
    } catch {
      return false
    }
  })
  const [visible, setVisible] = useState(document.visibilityState !== 'hidden')
  const [gpsMessage, setGPSMessage] = useState('')
  const [detail, setDetail] = useState<AstronomyFrame | null>(null)
  const lastFix = useRef({
    at: 0,
    latitude: site.latitude,
    longitude: site.longitude,
  })
  useEffect(() => {
    persist('weather-atlas.astronomy.options', options)
  }, [options])
  useEffect(() => {
    persist('weather-atlas.astronomy.site', [site])
  }, [site])
  const query = useQuery({
    queryKey: ['astronomy', site.latitude, site.longitude, effectiveOptions],
    queryFn: ({ signal }) => astronomyForecast(site, effectiveOptions, signal),
    staleTime: 120_000,
    refetchInterval: 300_000,
    retry: false,
  })
  const data = settling ? undefined : query.data
  const zone = data?.timeZone ?? 'UTC'
  const night = data?.nights[Math.min(nightIndex, data.nights.length - 1)]
  const frames =
    data?.frames.filter(
      (f) =>
        night &&
        f.time >= night.start &&
        f.time < night.end &&
        (!nightOnly || f.sunAltitudeDegrees < 0),
    ) ?? []
  const bestWindow = night?.windows.reduce<
    (typeof night.windows)[number] | undefined
  >(
    (best, next) => (!best || next.minutes > best.minutes ? next : best),
    undefined,
  )
  const choose = (next: ObservingSite) => {
    setFollowing(false)
    setSite(next)
    setNightIndex(0)
    setDetail(null)
    persist('weather-atlas.astronomy.site', [next])
  }
  useEffect(() => {
    const update = () => setVisible(document.visibilityState !== 'hidden')
    document.addEventListener('visibilitychange', update)
    return () => document.removeEventListener('visibilitychange', update)
  }, [])
  useEffect(() => {
    persist('weather-atlas.astronomy.gps', following)
  }, [following])
  useEffect(() => {
    if (!following || !visible) return
    if (!navigator.geolocation) return
    let active = true
    const watch = navigator.geolocation.watchPosition(
      ({ coords, timestamp }) => {
        if (!active) return
        const age = Date.now() - timestamp
        setGPSMessage(
          `Accuracy about ${Math.round(coords.accuracy)} m${age > 120_000 ? ' · stale fix' : ''}`,
        )
        if (age > 300_000) return
        const old = lastFix.current
        const distance = Math.hypot(
          (coords.latitude - old.latitude) * 111,
          (coords.longitude - old.longitude) *
            111 *
            Math.cos((coords.latitude * Math.PI) / 180),
        )
        if (old.at && (Date.now() - old.at < 60_000 || distance < 1)) return
        lastFix.current = {
          at: Date.now(),
          latitude: coords.latitude,
          longitude: coords.longitude,
        }
        setSite({
          latitude: coords.latitude,
          longitude: coords.longitude,
          name: 'Current location',
        })
        setDetail(null)
        setNightIndex(0)
      },
      (error) => {
        if (active)
          setGPSMessage(
            `${error.message} Your selected site is retained; choose on map instead.`,
          )
      },
      { enableHighAccuracy: false, maximumAge: 60_000, timeout: 15_000 },
    )
    return () => {
      active = false
      navigator.geolocation.clearWatch(watch)
    }
  }, [following, visible])
  return (
    <main className={`astronomy-page ${red ? 'astronomy-red' : ''}`}>
      <header className="astro-top">
        <a href="/forecast">
          <AppIcon /> Weather Atlas
        </a>
        <nav>
          <a href="/forecast">Forecast</a>
          <a href="/">Map</a>
          <a href="/astronomy" aria-current="page">
            Astronomy
          </a>
        </nav>
      </header>
      <div className="astro-heading">
        <div>
          <p className="astro-eyebrow">AFTER DARK</p>
          <h1>
            Astronomy <span>/ Clear sky</span>
          </h1>
          <p>Plan a night outside, one observing window at a time.</p>
        </div>
        <label>
          <input
            type="checkbox"
            checked={red}
            onChange={(e) => setRed(e.target.checked)}
          />{' '}
          Dim red view
        </label>
      </div>
      <section className="astro-card astro-site">
        <div>
          <h2>{site.name || 'Observing site'}</h2>
          <p>
            {site.latitude.toFixed(5)}°, {site.longitude.toFixed(5)}° · {zone} ·{' '}
            {following ? 'GPS following' : 'Fixed site'}
          </p>
          <p role="status">{gpsMessage}</p>
        </div>
        <div className="astro-actions">
          <button onClick={() => setPicking(true)}>Choose on map</button>
          <button
            aria-pressed={following}
            onClick={() => {
              if (!navigator.geolocation)
                setGPSMessage('GPS is unavailable. Choose a point on the map.')
              else {
                lastFix.current.at = 0
                setFollowing(!following)
              }
            }}
          >
            {' '}
            {following ? 'Stop GPS' : 'Use GPS'}
          </button>
          <button
            onClick={() => {
              const next = [
                ...saved.filter(
                  (s) =>
                    s.latitude !== site.latitude ||
                    s.longitude !== site.longitude,
                ),
                site,
              ].slice(-30)
              setSaved(next)
              persist('weather-atlas.astronomy.saved', next)
            }}
          >
            Save site
          </button>
        </div>
        {saved.length > 0 && (
          <div className="astro-saved">
            {saved.map((s) => (
              <span key={`${s.latitude}|${s.longitude}`}>
                <button onClick={() => choose(s)}>
                  {s.name ||
                    `${s.latitude.toFixed(3)}, ${s.longitude.toFixed(3)}`}
                </button>
                <button
                  aria-label={`Remove ${s.name}`}
                  onClick={() => {
                    const next = saved.filter((v) => v !== s)
                    setSaved(next)
                    persist('weather-atlas.astronomy.saved', next)
                  }}
                >
                  ×
                </button>
              </span>
            ))}
          </div>
        )}
      </section>
      <section className="astro-controls" aria-label="Observing preferences">
        <label>
          Model
          <select
            value={options.product}
            onChange={(e) =>
              setOptions({ ...options, product: e.target.value })
            }
          >
            <option value="gdps">GDPS · global</option>
            <option value="rdps">RDPS · regional</option>
            <option value="hrdps">HRDPS · high resolution</option>
          </select>
        </label>
        <label>
          Observing mode
          <select
            value={options.mode}
            onChange={(e) =>
              setOptions({
                ...options,
                mode: e.target.value as AstronomyOptions['mode'],
              })
            }
          >
            <option value="deep_sky">Deep sky · moonless darkness</option>
            <option value="lunar_planetary">
              Lunar / planetary · moonlight allowed
            </option>
          </select>
        </label>
        <label>
          Cloud limit {options.maxCloud}%
          <input
            type="range"
            min="0"
            max="100"
            step="5"
            value={options.maxCloud}
            onChange={(e) =>
              setOptions({ ...options, maxCloud: +e.target.value })
            }
          />
        </label>
        <label>
          Wind limit {options.maxWind} km/h
          <input
            type="range"
            min="0"
            max="80"
            step="5"
            value={options.maxWind}
            onChange={(e) =>
              setOptions({ ...options, maxWind: +e.target.value })
            }
          />
        </label>
      </section>
      <p className="astro-preview">
        Total-cloud preview · Layered cloud, seeing and transparency are not
        available yet.
      </p>
      {(query.isPending || settling) && (
        <p role="status">Preparing your observing forecast…</p>
      )}
      {query.error && !settling && (
        <div role="alert" className="astro-card">
          {query.error.message}{' '}
          <button onClick={() => void query.refetch()}>Retry</button>
        </div>
      )}
      {data && (
        <>
          <div className="astro-nights" aria-label="Observing night">
            {data.nights.map((n, i) => (
              <button
                key={n.date}
                aria-pressed={i === nightIndex}
                onClick={() => {
                  setNightIndex(i)
                  setDetail(null)
                }}
              >
                <strong>
                  {i === 0
                    ? 'Next night'
                    : clock(n.start, zone, true).split(',')[0]}
                </strong>
                <span>
                  {clock(n.start, zone, true).replace(/,?\s\d\d:\d\d$/, '')}
                </span>
                <small>
                  {n.state === 'window'
                    ? `${Math.max(...n.windows.map((w) => w.minutes))} min window`
                    : n.state === 'insufficient_data'
                      ? 'Insufficient data'
                      : 'No window'}
                </small>
              </button>
            ))}
          </div>
          {night && (
            <>
              <section className="astro-card astro-summary">
                <p className="astro-eyebrow">
                  {options.mode === 'deep_sky'
                    ? 'MOONLESS / ASTRONOMICALLY DARK'
                    : 'EVENING / MOONLIGHT ALLOWED'}
                </p>
                <h2>
                  {bestWindow
                    ? `${clock(bestWindow.start, zone)} – ${clock(bestWindow.end, zone)}`
                    : night.state === 'insufficient_data'
                      ? 'Insufficient data'
                      : 'No qualifying window'}
                </h2>
                <p>
                  {bestWindow && `${bestWindow.minutes} minutes · `}
                  {night.summary}
                </p>
                <p className="astro-muted">
                  {clock(night.start, zone, true)} →{' '}
                  {clock(night.end, zone, true)} · Clear does not mean good
                  seeing.
                </p>
              </section>
              <section className="astro-events" aria-label="Sun and Moon">
                <div className="astro-card">
                  <span>Sunset / sunrise</span>
                  <strong>
                    {clock(night.events.sunset, zone)} /{' '}
                    {clock(night.events.sunrise, zone)}
                  </strong>
                </div>
                <div className="astro-card">
                  <span>Astronomical darkness</span>
                  <strong>
                    {night.darkness.length
                      ? night.darkness
                          .map(
                            (v) =>
                              `${clock(v.start, zone)}–${clock(v.end, zone)}`,
                          )
                          .join(', ')
                      : 'None this night'}
                  </strong>
                </div>
                <div className="astro-card">
                  <span>Moon illumination</span>
                  <strong>{night.moonIlluminatedPercent.toFixed(0)}%</strong>
                  <small>
                    {night.moonPhaseName ? `${night.moonPhaseName} · ` : ''}At
                    the night midpoint; altitude matters too.
                  </small>
                </div>
                <div className="astro-card">
                  <span>Moonrise / moonset</span>
                  <strong>
                    {clock(night.events.moonrise, zone)} /{' '}
                    {clock(night.events.moonset, zone)}
                  </strong>
                </div>
              </section>
              <section className="astro-card">
                <div className="astro-timeline-heading">
                  <h2>The night, hour by hour</h2>
                  <label>
                    <input
                      type="checkbox"
                      checked={nightOnly}
                      onChange={(e) => setNightOnly(e.target.checked)}
                    />{' '}
                    Night only
                  </label>
                </div>
                <p className="astro-muted">
                  Native model times; gaps are not filled. Tap a time or value
                  for details. Midnight is labelled with its date.
                </p>
                {!frames.length ? (
                  <p>
                    No collected weather frames cover this night and selection.
                    Sun and Moon events remain available above.
                  </p>
                ) : (
                  <div className="astro-table-scroll">
                    <table className="astro-table">
                      <thead>
                        <tr>
                          <th scope="col">Site-local time</th>
                          {frames.map((f) => (
                            <th key={f.time}>
                              <button onClick={() => setDetail(f)}>
                                {clock(f.time, zone, true)}
                              </button>
                            </th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {rows.map((row) => (
                          <tr key={row.key}>
                            <th scope="row">
                              {row.label}
                              <small>{row.unit}</small>
                            </th>
                            {frames.map((f) => {
                              const value = f[row.key]
                              const known = typeof value === 'number'
                              return (
                                <td
                                  key={f.time}
                                  className={
                                    row.key === 'cloudPercent' && known
                                      ? value <= options.maxCloud
                                        ? 'astro-clear'
                                        : 'astro-cloudy'
                                      : ''
                                  }
                                >
                                  <button
                                    onClick={() => setDetail(f)}
                                    aria-label={`${row.label} at ${clock(f.time, zone, true)}: ${known ? value.toFixed(1) + row.unit : 'unavailable'}`}
                                  >
                                    {known
                                      ? value.toFixed(
                                          row.key === 'rainMm' ? 1 : 0,
                                        )
                                      : '—'}
                                  </button>
                                </td>
                              )
                            })}
                          </tr>
                        ))}
                        <tr>
                          <th scope="row">
                            Dew risk<small>Heuristic</small>
                          </th>
                          {frames.map((f) => (
                            <td key={f.time}>
                              {f.dewRisk === null
                                ? '—'
                                : f.dewRisk
                                  ? 'Watch'
                                  : 'Low'}
                            </td>
                          ))}
                        </tr>
                      </tbody>
                    </table>
                  </div>
                )}
                <p className="astro-muted">
                  ¹ Precipitation is the total ending at that time, over its
                  native 1 h or 3 h interval—not an invented hourly rate. A dash
                  means unavailable, never zero.
                </p>
              </section>
              {detail && (
                <section className="astro-card" aria-label="Selected interval">
                  <button
                    className="astro-close"
                    onClick={() => setDetail(null)}
                  >
                    Close details
                  </button>
                  <h2>{clock(detail.time, zone, true)}</h2>
                  <p>
                    Sun {detail.sunAltitudeDegrees.toFixed(1)}° · Moon{' '}
                    {detail.moonAltitudeDegrees.toFixed(1)}° ·{' '}
                    {detail.moonIlluminatedPercent.toFixed(0)}% illuminated
                  </p>
                  <p>
                    {detail.rainStart
                      ? `Precipitation interval: ${clock(detail.rainStart, zone, true)} to ${clock(detail.time, zone, true)}.`
                      : 'No precipitation amount is available for this time.'}
                  </p>
                  <p>
                    Dew risk uses a temperature/dew-point spread of 2°C or less.
                    It does not model your optics.
                  </p>
                  <p>
                    Low/middle/high cloud, seeing and transparency: not
                    available.
                  </p>
                  <a
                    href={`/?${new URLSearchParams({ astronomy: '1', latitude: String(site.latitude), longitude: String(site.longitude), product: data.product, valid_time: detail.time })}`}
                  >
                    Open weather map
                  </a>
                </section>
              )}
            </>
          )}
          <details className="astro-card">
            <summary>Sources, twilight & forecast limitations</summary>
            <p>
              {data.source} · Run{' '}
              {data.runTime ? clock(data.runTime, zone, true) : 'unavailable'} ·{' '}
              {data.stale ? 'Stale or missing model run' : 'Recent model run'} ·
              Updated {clock(data.generatedAt, zone, true)}
            </p>
            <p>{data.method}</p>
            <p>
              Twilight ends: civil {clock(night?.events.civilDusk, zone)},
              nautical {clock(night?.events.nauticalDusk, zone)}, astronomical{' '}
              {clock(night?.events.astronomicalDusk, zone)}.
            </p>
            {data.sample && (
              <p>
                Sample cell: {data.sample.latitude.toFixed(5)},{' '}
                {data.sample.longitude.toFixed(5)} ·{' '}
                {data.sample.pixelSize.join(' × ')} ({data.sample.crs}). Your
                site is not moved to the cell or a forecast town.
              </p>
            )}
            <ul>
              {data.limitations.map((text) => (
                <li key={text}>{text}</li>
              ))}
            </ul>
            <p>
              Rules {data.ruleVersion} · Windows require at least 60 minutes, no
              model precipitation, and your selected cloud/wind limits. This is
              planning guidance, not a probability or guarantee.
            </p>
          </details>
        </>
      )}
      <footer className="astro-muted">
        Weather prepared on the Weather Atlas server. Sites stay in this
        browser. Map tiles: OpenFreeMap / OpenStreetMap.{' '}
        <button
          onClick={() => void query.refetch()}
          disabled={query.isFetching}
        >
          {query.isFetching ? 'Updating…' : 'Refresh'}
        </button>
      </footer>
      {picking && (
        <SitePicker
          site={site}
          onCancel={() => setPicking(false)}
          onChoose={(next) => {
            choose(next)
            setPicking(false)
          }}
        />
      )}
    </main>
  )
}

function SitePicker({
  site,
  onCancel,
  onChoose,
}: {
  site: ObservingSite
  onCancel: () => void
  onChoose: (site: ObservingSite) => void
}) {
  const [latitude, setLatitude] = useState(String(site.latitude))
  const [longitude, setLongitude] = useState(String(site.longitude))
  const [name, setName] = useState(site.name)
  const [error, setError] = useState('')
  const container = useRef<HTMLDivElement>(null)
  const dialog = useRef<HTMLDivElement>(null)
  const pin = useRef<maplibregl.Marker | null>(null)
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null
    const focusable = () => [
      ...(dialog.current?.querySelectorAll<HTMLElement>(
        'button:not(:disabled), input, a[href], [tabindex="0"]',
      ) ?? []),
    ]
    focusable()[0]?.focus()
    const key = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onCancel()
      if (event.key === 'Tab') {
        const items = focusable()
        const first = items[0]
        const last = items.at(-1)
        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault()
          last?.focus()
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault()
          first?.focus()
        }
      }
    }
    document.addEventListener('keydown', key)
    return () => {
      document.removeEventListener('keydown', key)
      previous?.focus()
    }
  }, [onCancel])
  useEffect(() => {
    if (!container.current) return
    const map = new maplibregl.Map({
      container: container.current,
      style: weatherBasemapStyle({}),
      center: [site.longitude, site.latitude],
      zoom: 8,
    })
    pin.current = new maplibregl.Marker({ draggable: true })
      .setLngLat([site.longitude, site.latitude])
      .addTo(map)
    const move = (lon: number, lat: number) => {
      setLongitude(lon.toFixed(6))
      setLatitude(lat.toFixed(6))
      setName('Observing site')
      pin.current?.setLngLat([lon, lat])
    }
    map.on('click', (e) => move(e.lngLat.lng, e.lngLat.lat))
    pin.current.on('dragend', () => {
      const p = pin.current!.getLngLat()
      move(p.lng, p.lat)
    })
    map.on('error', () =>
      setError(
        'Map tiles are unavailable. You can still enter exact coordinates below.',
      ),
    )
    map.addControl(new maplibregl.NavigationControl())
    return () => {
      pin.current?.remove()
      map.remove()
    }
  }, [site.latitude, site.longitude])
  const candidate = observingSiteSchema.safeParse({
    latitude: latitude.trim() ? Number(latitude) : NaN,
    longitude: longitude.trim() ? Number(longitude) : NaN,
    name: name.trim(),
  })
  useEffect(() => {
    if (candidate.success)
      pin.current?.setLngLat([
        candidate.data.longitude,
        candidate.data.latitude,
      ])
  }, [
    latitude,
    longitude,
    candidate.success,
    candidate.data?.latitude,
    candidate.data?.longitude,
  ])
  return (
    <div
      className="astro-modal"
      ref={dialog}
      role="dialog"
      aria-modal="true"
      aria-label="Choose observing site"
    >
      <div className="astro-picker">
        <header>
          <h2>Choose observing site</h2>
          <button onClick={onCancel}>Cancel</button>
        </header>
        <p>
          Tap the map or drag the pin. Panning alone does not change your site.
        </p>
        <div className="astro-picker-map" ref={container} />
        <form
          onSubmit={(e) => {
            e.preventDefault()
            if (candidate.success) onChoose(candidate.data)
          }}
        >
          <label>
            Site name
            <input
              value={name}
              maxLength={120}
              onChange={(e) => setName(e.target.value)}
            />
          </label>
          <label>
            Latitude
            <input
              inputMode="decimal"
              value={latitude}
              onChange={(e) => setLatitude(e.target.value)}
            />
          </label>
          <label>
            Longitude
            <input
              inputMode="decimal"
              value={longitude}
              onChange={(e) => setLongitude(e.target.value)}
            />
          </label>
          <p role="status">
            {error ||
              (!candidate.success
                ? 'Enter valid latitude (−90 to 90) and longitude (−180 to 180).'
                : 'The exact point is used; no snapping to a forecast town.')}
          </p>
          <button disabled={!candidate.success}>Use this location</button>
        </form>
      </div>
    </div>
  )
}
