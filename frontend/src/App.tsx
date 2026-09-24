import { useQueries, useQuery, useQueryClient } from '@tanstack/react-query'
import type { GeoJSONSource, Map, Marker } from 'maplibre-gl'
import { useEffect, useMemo, useRef, useState } from 'react'
import {
  api,
  type CityForecastCollection,
  type Field,
  type ResolvedLayer,
  type Variable,
} from './api'
import {
  cityForecastInBounds,
  cityForecastTimes,
  precipitationLikelihood,
  forecastMetric,
} from './cityForecast'
import {
  forecastLeaderLine,
  layoutCityForecastLabels,
} from './cityForecastLayout'
import { hotspotCollectionBounds } from './hotspots'
import { cameraBounds } from './mapBounds'
import { SmokeRunBuilder } from './SmokeRunBuilder'
import { SmokeRunStatus } from './SmokeRunStatus'
import {
  bufferedTimelineFrames,
  nextReadyTimelineFrame,
  WEATHER_FRAME_LOOKAHEAD,
} from './playback'
import { useMapSelection } from './store'
import { AppIcon } from './AppIcon'
import { formatForecastHour, formatUtcTimestamp } from './time'
import {
  type BufferedWeatherFrame,
  type DisplayLayer,
  useWeatherLayers,
} from './useWeatherLayers'
import { groupVariables } from './variableGroups'
import {
  createWindArrowImage,
  weatherBasemapStyle,
  windInsertionPoint,
  windSize,
  WIND_VECTOR_LAYER_ID,
} from './mapPresentation'

const WILDFIRE_HOTSPOTS_CODE = 'wildfire_hotspots'
const WIND_ARROW_IMAGE_ID = 'wind-arrow-image'
const WIND_VECTOR_SOURCE_ID = 'wind-vector-source'
const WIND_U_FIELD = 'wind_u_10m'
const WIND_V_FIELD = 'wind_v_10m'
const CITY_FORECAST_PROVINCE = 'NS'
const CITY_FORECAST_OVERVIEW_ZOOM = 6
const NOVA_SCOTIA_BOUNDS: [[number, number], [number, number]] = [
  [-66.7, 43.2],
  [-59.5, 47.2],
]
const wildfireVariable: Variable = {
  code: WILDFIRE_HOTSPOTS_CODE,
  variableCode: 'wildfire_hotspots',
  name: 'Wildfire hotspots',
  variableClass: 'wildfire_observation',
  levelCode: 'viirs_375m',
  levelName: 'VIIRS 375 m · CWFIS',
  unit: 'detections',
  products: [],
}

const baseStyle = weatherBasemapStyle({
  vectorURL: import.meta.env.VITE_BASEMAP_VECTOR_URL,
  glyphURL: import.meta.env.VITE_BASEMAP_GLYPH_URL,
  rasterURL: import.meta.env.VITE_BASEMAP_TILE_URL,
})

function formatUtc(value: string, includeDate = true) {
  const date = new Date(value)
  return new Intl.DateTimeFormat('en-CA', {
    month: includeDate ? 'short' : undefined,
    day: includeDate ? '2-digit' : undefined,
    hour: '2-digit',
    minute: '2-digit',
    hourCycle: 'h23',
    timeZone: 'UTC',
    timeZoneName: 'short',
  }).format(date)
}

function toUtcInput(value: string | undefined) {
  return value ? new Date(value).toISOString().slice(0, 16) : ''
}

function fromUtcInput(value: string) {
  return new Date(`${value}:00Z`).toISOString()
}

function variableLabel(variable: Variable) {
  const precipitation = variable.code.match(
    /^precipitation_(\d+)h_(preliminary|final)$/,
  )
  if (precipitation) {
    return `${variable.name} · ${precipitation[1]}-hour ${precipitation[2]}`
  }
  const ensemblePrecipitation = variable.code.match(
    /^precipitation_(\d+)h_(ensemble|percentile_(25|75))$/,
  )
  if (ensemblePrecipitation) {
    const statistic =
      ensemblePrecipitation[2] === 'ensemble'
        ? 'ensemble control member'
        : `${ensemblePrecipitation[3]}th percentile`
    return `${variable.name} · ${ensemblePrecipitation[1]}-hour ${statistic}`
  }
  return `${variable.name} · ${variable.levelName}`
}

function smokeBboxFromMap(map: Map | null): [number, number, number, number] {
  if (!map) return [-70, 40, -55, 50]
  const bounds = map.getBounds()
  const raw = [
    bounds.getWest(),
    bounds.getSouth(),
    bounds.getEast(),
    bounds.getNorth(),
  ]
  if (!raw.every(Number.isFinite) || raw[2] <= raw[0] || raw[3] <= raw[1]) {
    return [-70, 40, -55, 50]
  }
  const centreLongitude = Math.max(-155, Math.min(155, (raw[0] + raw[2]) / 2))
  const centreLatitude = Math.max(-70, Math.min(70, (raw[1] + raw[3]) / 2))
  const width = Math.min(50, raw[2] - raw[0])
  const height = Math.min(40, raw[3] - raw[1])
  return [
    Number((centreLongitude - width / 2).toFixed(2)),
    Number((centreLatitude - height / 2).toFixed(2)),
    Number((centreLongitude + width / 2).toFixed(2)),
    Number((centreLatitude + height / 2).toFixed(2)),
  ]
}

type WindViewport = {
  bbox: [number, number, number, number]
  columns: number
  rows: number
}

function windViewportFromMap(map: Map): WindViewport | null {
  const bounds = map.getBounds()
  const west = Math.max(-180, bounds.getWest())
  const south = Math.max(-85, bounds.getSouth())
  const east = Math.min(180, bounds.getEast())
  const north = Math.min(85, bounds.getNorth())
  if (
    ![west, south, east, north].every(Number.isFinite) ||
    west >= east ||
    south >= north
  ) {
    return null
  }
  const canvas = map.getCanvas()
  return {
    bbox: [west, south, east, north].map((value) =>
      Number(value.toFixed(3)),
    ) as [number, number, number, number],
    columns: Math.max(8, Math.min(28, Math.round(canvas.clientWidth / 64))),
    rows: Math.max(4, Math.min(18, Math.round(canvas.clientHeight / 64))),
  }
}

function sameWindViewport(
  left: WindViewport | null,
  right: WindViewport | null,
) {
  if (!left || !right) return left === right
  return (
    left.columns === right.columns &&
    left.rows === right.rows &&
    left.bbox.every((value, index) => value === right.bbox[index])
  )
}

function cityForecastLabel(
  feature: CityForecastCollection['features'][number],
) {
  const { properties } = feature
  const likelihood = precipitationLikelihood(
    properties.popPercent,
    properties.condition,
  )
  const element = document.createElement('article')
  element.className = 'city-forecast-label'
  element.setAttribute(
    'aria-label',
    `${properties.locality}, ${properties.name}, ${properties.province}: ` +
      `temperature ${forecastMetric(properties.temperatureC, '°C')}, ` +
      `humidity ${forecastMetric(properties.relativeHumidityPercent, '%')}, ` +
      `precipitation outlook ${likelihood ?? (properties.condition || 'not provided')}, ` +
      `precipitation amount ${properties.precipitationAmount ?? 'not issued'}`,
  )

  const heading = document.createElement('header')
  const name = document.createElement('strong')
  name.textContent = properties.locality
  const period = document.createElement('small')
  period.textContent = `${properties.province} · ${properties.period}`
  heading.append(name, period)

  const metrics = document.createElement('dl')
  const rows = [
    ['Temp:', forecastMetric(properties.temperatureC, '°C')],
    ['Hum:', forecastMetric(properties.relativeHumidityPercent, '%')],
    ...(likelihood === null ? [] : [['Precip:', likelihood]]),
    ['Precip Amount:', properties.precipitationAmount ?? '—'],
  ] as const
  for (const [label, value] of rows) {
    const term = document.createElement('dt')
    term.textContent = label
    const description = document.createElement('dd')
    description.textContent = value
    metrics.append(term, description)
  }
  element.append(heading, metrics)
  element.title = [properties.name, properties.condition]
    .filter(Boolean)
    .join(' · ')
  return element
}

function paletteGradient(
  field: Field | undefined,
  resolved: ResolvedLayer | undefined,
) {
  const stops = resolved?.legend.palette ?? field?.palette ?? []
  if (stops.length === 0) return '#17314a'
  const minimum =
    resolved?.legend.minimum ?? field?.defaultMin ?? stops[0].value
  const maximum =
    resolved?.legend.maximum ?? field?.defaultMax ?? stops.at(-1)!.value
  const span = maximum - minimum || 1
  return `linear-gradient(90deg, ${stops
    .map(
      (stop) =>
        `${stop.color} ${Math.max(0, Math.min(100, ((stop.value - minimum) / span) * 100))}%`,
    )
    .join(', ')})`
}

function LayerEditor({
  layerId,
  fieldCode,
  fields,
  opacity,
  visible,
  displayMinimum,
  displayMaximum,
  resolved,
  opacityCutoff,
  canMoveDown,
  canMoveUp,
  canRemove,
}: {
  layerId: string
  fieldCode: string
  fields: Field[]
  opacity: number
  visible: boolean
  displayMinimum?: number
  displayMaximum?: number
  resolved?: ResolvedLayer
  opacityCutoff?: number
  canMoveDown: boolean
  canMoveUp: boolean
  canRemove: boolean
}) {
  const updateLayer = useMapSelection((state) => state.updateLayer)
  const moveLayer = useMapSelection((state) => state.moveLayer)
  const removeLayer = useMapSelection((state) => state.removeLayer)
  const field = fields.find((candidate) => candidate.code === fieldCode)
  const groupedFields = groupVariables(fields)
  const effectiveMinimum =
    displayMinimum ?? resolved?.legend.minimum ?? field?.defaultMin
  const effectiveMaximum =
    displayMaximum ?? resolved?.legend.maximum ?? field?.defaultMax
  const effectiveCutoff =
    effectiveMinimum !== undefined && effectiveMaximum !== undefined
      ? Math.max(
          effectiveMinimum,
          Math.min(effectiveMaximum, opacityCutoff ?? effectiveMinimum),
        )
      : undefined
  const cutoffStep =
    effectiveMinimum !== undefined && effectiveMaximum !== undefined
      ? Math.max((effectiveMaximum - effectiveMinimum) / 100, 0.01)
      : 0.01

  return (
    <section className="layer-editor">
      <div className="layer-editor-heading">
        <span
          className="layer-swatch"
          style={{ background: paletteGradient(field, resolved) }}
        />
        <div>
          <small>{field?.variableClass ?? 'Weather layer'}</small>
          <strong>{field?.name ?? 'Select a field'}</strong>
        </div>
        <button
          type="button"
          className={`visibility-button ${visible ? 'active' : ''}`}
          onClick={() => updateLayer(layerId, { visible: !visible })}
          aria-label={visible ? 'Hide layer' : 'Show layer'}
        >
          {visible ? '●' : '○'}
        </button>
      </div>

      <label>
        Variable and level
        <select
          value={fieldCode}
          onChange={(event) =>
            updateLayer(layerId, {
              field: event.target.value,
              displayMinimum: undefined,
              displayMaximum: undefined,
              opacityCutoff: undefined,
            })
          }
        >
          {groupedFields.map((group) => (
            <optgroup key={group.code} label={group.label}>
              {group.items.map((candidate) => (
                <option key={candidate.code} value={candidate.code}>
                  {candidate.name} · {candidate.levelName}
                </option>
              ))}
            </optgroup>
          ))}
        </select>
      </label>

      <div className="scale-controls">
        <label>
          Scale minimum
          <input
            type="number"
            step="any"
            value={effectiveMinimum ?? ''}
            onChange={(event) => {
              const value = event.currentTarget.valueAsNumber
              const upper = effectiveMaximum
              if (
                Number.isFinite(value) &&
                upper !== undefined &&
                value < upper
              ) {
                updateLayer(layerId, {
                  displayMinimum: value,
                  displayMaximum: upper,
                  opacityCutoff:
                    opacityCutoff === undefined
                      ? undefined
                      : Math.max(value, Math.min(upper, opacityCutoff)),
                })
              }
            }}
          />
        </label>
        <label>
          Scale maximum
          <input
            type="number"
            step="any"
            value={effectiveMaximum ?? ''}
            onChange={(event) => {
              const value = event.currentTarget.valueAsNumber
              const lower = effectiveMinimum
              if (
                Number.isFinite(value) &&
                lower !== undefined &&
                value > lower
              ) {
                updateLayer(layerId, {
                  displayMinimum: lower,
                  displayMaximum: value,
                  opacityCutoff:
                    opacityCutoff === undefined
                      ? undefined
                      : Math.max(lower, Math.min(value, opacityCutoff)),
                })
              }
            }}
          />
        </label>
      </div>

      {field?.variableCode === 'air_temperature' &&
        displayMinimum === undefined && (
          <small className="auto-scale-note">
            Automatic colour range · 5°C steps
          </small>
        )}

      {(displayMinimum !== undefined || displayMaximum !== undefined) && (
        <button
          className="text-button"
          type="button"
          onClick={() =>
            updateLayer(layerId, {
              displayMinimum: undefined,
              displayMaximum: undefined,
              opacityCutoff:
                opacityCutoff === undefined || !field
                  ? opacityCutoff
                  : Math.max(
                      field.defaultMin,
                      Math.min(field.defaultMax, opacityCutoff),
                    ),
            })
          }
        >
          Reset colour scale
        </button>
      )}

      <label className="opacity-control">
        <span>
          Opacity <output>{Math.round(opacity * 100)}%</output>
        </span>
        <input
          type="range"
          min="0"
          max="1"
          step="0.01"
          value={opacity}
          onChange={(event) =>
            updateLayer(layerId, { opacity: Number(event.target.value) })
          }
        />
      </label>

      <label className="opacity-control cutoff-control">
        <span>
          Transparent below
          <output>
            {effectiveCutoff === undefined
              ? '—'
              : `${Number(effectiveCutoff.toPrecision(4))} ${field?.unit ?? ''}`}
          </output>
        </span>
        <input
          aria-label={`Transparent below cutoff for ${field?.name ?? 'weather layer'}`}
          type="range"
          min={effectiveMinimum ?? 0}
          max={effectiveMaximum ?? 1}
          step={cutoffStep}
          value={effectiveCutoff ?? 0}
          disabled={
            effectiveMinimum === undefined || effectiveMaximum === undefined
          }
          onChange={(event) =>
            updateLayer(layerId, { opacityCutoff: Number(event.target.value) })
          }
        />
      </label>
      <div className="cutoff-footer">
        <small>Lower values are fully transparent.</small>
        {opacityCutoff !== undefined && (
          <button
            type="button"
            className="text-button"
            onClick={() => updateLayer(layerId, { opacityCutoff: undefined })}
          >
            Reset cutoff
          </button>
        )}
      </div>

      <div className="layer-actions">
        <button
          className="text-button"
          type="button"
          disabled={!canMoveDown}
          onClick={() => moveLayer(layerId, -1)}
        >
          Move down
        </button>
        <button
          className="text-button"
          type="button"
          disabled={!canMoveUp}
          onClick={() => moveLayer(layerId, 1)}
        >
          Move up
        </button>
        {canRemove && (
          <button
            className="text-button danger"
            type="button"
            onClick={() => removeLayer(layerId)}
          >
            Remove
          </button>
        )}
      </div>
    </section>
  )
}

export function App() {
  const mapContainer = useRef<HTMLDivElement>(null)
  const mapInstance = useRef<Map | null>(null)
  const sampleMarker = useRef<Marker | null>(null)
  const cityForecastMarkers = useRef<Marker[]>([])
  const cityForecastModeRef = useRef(false)
  const fittedDomain = useRef('')
  const fittedWildfireSnapshot = useRef('')
  const fittedCityForecast = useRef(false)
  const [mapReady, setMapReady] = useState(false)
  const [coordinate, setCoordinate] = useState({ longitude: -96, latitude: 57 })
  const [samplePoint, setSamplePoint] = useState<{
    longitude: number
    latitude: number
  } | null>(null)
  const [controlsOpen, setControlsOpen] = useState(true)
  const [rangeStart, setRangeStart] = useState('')
  const [rangeEnd, setRangeEnd] = useState('')
  const [hotspotDate, setHotspotDate] = useState('')
  const [viewMode, setViewMode] = useState<'layers' | 'city-forecast'>('layers')
  const [cityForecastTime, setCityForecastTime] = useState('')
  const [windVisible, setWindVisible] = useState(true)
  const [windViewport, setWindViewport] = useState<WindViewport | null>(null)
  const [smokeBuilderOpen, setSmokeBuilderOpen] = useState(false)
  const [smokeBuilderBbox, setSmokeBuilderBbox] = useState<
    [number, number, number, number]
  >([-70, 40, -55, 50])
  const [activeSmokeRunId, setActiveSmokeRunId] = useState('')
  const queryClient = useQueryClient()

  const selection = useMapSelection()
  const setValidTime = selection.setValidTime
  const wildfireSelected = selection.variable === WILDFIRE_HOTSPOTS_CODE
  const cityForecastMode = viewMode === 'city-forecast'

  useEffect(() => {
    cityForecastModeRef.current = cityForecastMode
  }, [cityForecastMode])

  const productsQuery = useQuery({
    queryKey: ['products'],
    queryFn: ({ signal }) => api.listProducts(signal),
  })
  const variablesQuery = useQuery({
    queryKey: ['variables'],
    queryFn: ({ signal }) => api.listVariables(signal),
  })
  const cityForecastQuery = useQuery({
    queryKey: ['city-forecasts', CITY_FORECAST_PROVINCE, cityForecastTime],
    queryFn: ({ signal }) =>
      api.cityForecasts(
        cityForecastTime || undefined,
        CITY_FORECAST_PROVINCE,
        signal,
      ),
    enabled: cityForecastMode,
    staleTime: 5 * 60_000,
    refetchInterval: 5 * 60_000,
  })
  const hotspotDatesQuery = useQuery({
    queryKey: ['hotspot-dates'],
    queryFn: ({ signal }) => api.listHotspotDates(signal),
    enabled: wildfireSelected,
    staleTime: 5 * 60_000,
  })
  const hotspotsQuery = useQuery({
    queryKey: ['hotspots', hotspotDate],
    queryFn: ({ signal }) => api.getHotspots(hotspotDate, signal),
    enabled: wildfireSelected && Boolean(hotspotDate),
    staleTime: 5 * 60_000,
  })
  const domainsQuery = useQuery({
    queryKey: ['domains', selection.product],
    queryFn: ({ signal }) => api.listDomains(selection.product, signal),
    enabled: !cityForecastMode && Boolean(selection.product),
  })
  const fieldsQuery = useQuery({
    queryKey: ['fields', selection.product],
    queryFn: ({ signal }) =>
      api.listFields(selection.product, undefined, signal),
    enabled: !cityForecastMode && Boolean(selection.product),
  })
  const timelineField = selection.layers[0]?.field || selection.variable
  const timelineQuery = useQuery({
    queryKey: [
      'timeline',
      selection.product,
      selection.domain,
      timelineField,
      rangeStart,
      rangeEnd,
      selection.runTime,
    ],
    queryFn: async ({ signal }) => {
      if (selection.runTime) {
        const items = await api.listTimes(
          selection.product,
          selection.runTime,
          timelineField,
          signal,
        )
        return {
          items: items
            .filter(
              (item) =>
                (!rangeStart || item.validTime >= rangeStart) &&
                (!rangeEnd || item.validTime <= rangeEnd),
            )
            .map((item) => ({ ...item, runTime: selection.runTime })),
          truncated: false,
        }
      }
      return api.listTimeline(
        selection.product,
        selection.domain,
        timelineField,
        rangeStart && rangeEnd
          ? { start: rangeStart, end: rangeEnd }
          : undefined,
        signal,
      )
    },
    enabled:
      !cityForecastMode &&
      Boolean(selection.product && selection.domain && timelineField),
    refetchInterval: 60_000,
  })

  const products = useMemo(() => productsQuery.data ?? [], [productsQuery.data])
  const variables = useMemo(
    () => variablesQuery.data ?? [],
    [variablesQuery.data],
  )
  const selectableVariables = useMemo(
    () => [...variables, wildfireVariable],
    [variables],
  )
  const groupedSelectableVariables = useMemo(
    () => groupVariables(selectableVariables),
    [selectableVariables],
  )
  const compatibleProducts = useMemo(() => {
    const variable = selectableVariables.find(
      (item) => item.code === selection.variable,
    )
    if (!variable) return []
    return products.filter(
      (product) =>
        product.latestRunTime !== null &&
        variable.products.includes(product.code),
    )
  }, [products, selectableVariables, selection.variable])
  const domains = useMemo(() => domainsQuery.data ?? [], [domainsQuery.data])
  const fields = useMemo(() => fieldsQuery.data ?? [], [fieldsQuery.data])
  const windAvailable = useMemo(
    () =>
      fields.some((field) => field.code === WIND_U_FIELD) &&
      fields.some((field) => field.code === WIND_V_FIELD),
    [fields],
  )
  const times = useMemo(
    () => timelineQuery.data?.items ?? [],
    [timelineQuery.data],
  )
  const activeTimeIndex = times.findIndex(
    (item) => item.validTime === selection.validTime,
  )
  const activeTime = activeTimeIndex >= 0 ? times[activeTimeIndex] : undefined
  const activeRunTime = activeTime?.runTime ?? ''
  const cityTimes = useMemo(
    () =>
      cityForecastQuery.data ? cityForecastTimes(cityForecastQuery.data) : [],
    [cityForecastQuery.data],
  )
  const activeCityTimeIndex = cityTimes.indexOf(cityForecastTime)
  const hotspotDates = hotspotDatesQuery.data?.items ?? []
  const latestHotspotDate = hotspotDatesQuery.data?.availableEnd ?? ''
  const selectedHotspotDate = hotspotDates.find(
    (item) => item.dataDate === hotspotDate,
  )
  const hotspotDateIndex = hotspotDates.findIndex(
    (item) => item.dataDate === hotspotDate,
  )
  const previousHotspotDate =
    hotspotDateIndex > 0 ? hotspotDates[hotspotDateIndex - 1]?.dataDate : ''
  const nextHotspotDate =
    hotspotDateIndex >= 0 && hotspotDateIndex < hotspotDates.length - 1
      ? hotspotDates[hotspotDateIndex + 1]?.dataDate
      : ''
  const hotspotObservationTime = useMemo(
    () =>
      hotspotsQuery.data?.features.reduce(
        (latest, feature) =>
          feature.properties.observed_at > latest
            ? feature.properties.observed_at
            : latest,
        '',
      ) ?? '',
    [hotspotsQuery.data],
  )
  const displayedValidTime = cityForecastMode
    ? (cityForecastQuery.data?.validTime ?? cityForecastTime)
    : wildfireSelected
      ? hotspotObservationTime
      : selection.validTime

  useEffect(() => {
    if (
      cityForecastMode &&
      cityTimes.length > 0 &&
      !cityTimes.includes(cityForecastTime)
    ) {
      setCityForecastTime(cityTimes[0])
    }
  }, [cityForecastMode, cityForecastTime, cityTimes])

  useEffect(() => {
    if (wildfireSelected && !hotspotDate && latestHotspotDate) {
      setHotspotDate(latestHotspotDate)
    }
  }, [hotspotDate, latestHotspotDate, wildfireSelected])

  useEffect(() => {
    if (
      !variablesQuery.isLoading &&
      selectableVariables.length > 0 &&
      !selectableVariables.some((item) => item.code === selection.variable)
    ) {
      const preferred =
        variables.find((item) => item.variableCode === 'air_temperature') ??
        variables[0] ??
        wildfireVariable
      selection.setVariable(preferred.code)
    }
  }, [selectableVariables, selection, variables, variablesQuery.isLoading])

  useEffect(() => {
    if (
      compatibleProducts.length > 0 &&
      !compatibleProducts.some((item) => item.code === selection.product)
    ) {
      selection.setProduct(compatibleProducts[0].code)
    }
  }, [compatibleProducts, selection])

  useEffect(() => {
    if (
      domains.length > 0 &&
      !domains.some((item) => item.code === selection.domain)
    ) {
      selection.setDomain(domains[0].code)
    }
  }, [domains, selection])

  useEffect(() => {
    if (
      times.length > 0 &&
      !times.some((item) => item.validTime === selection.validTime)
    ) {
      selection.setValidTime(times[0].validTime)
    }
  }, [times, selection])

  useEffect(() => {
    if (cityForecastMode || fields.length === 0) return
    const primaryField =
      fields.find((field) => field.code === selection.variable) ?? fields[0]
    selection.ensureLayer(primaryField.code)
    for (const layer of selection.layers) {
      if (!fields.some((field) => field.code === layer.field)) {
        selection.updateLayer(layer.id, {
          field: fields[0].code,
          displayMinimum: undefined,
          displayMaximum: undefined,
        })
      }
    }
  }, [cityForecastMode, fields, selection])

  const bufferedTimes = useMemo(
    () => bufferedTimelineFrames(times, selection.validTime),
    [selection.validTime, times],
  )
  const bufferedLayerRequests = useMemo(
    () =>
      bufferedTimes.flatMap((time) =>
        selection.layers.map((layer) => ({ layer, time })),
      ),
    [bufferedTimes, selection.layers],
  )
  const bufferedLayerQueries = useQueries({
    queries: bufferedLayerRequests.map(({ layer, time }) => ({
      queryKey: [
        'layer',
        selection.product,
        selection.domain,
        time.runTime,
        layer.field,
        time.validTime,
        layer.displayMinimum,
        layer.displayMaximum,
        layer.opacityCutoff,
      ],
      queryFn: ({ signal }: { signal: AbortSignal }) =>
        api.resolveLayer(
          {
            product: selection.product,
            domain: selection.domain,
            run: time.runTime,
            field: layer.field,
            validTime: time.validTime,
            minimum: layer.displayMinimum,
            maximum: layer.displayMaximum,
            opacityCutoff: layer.opacityCutoff,
          },
          signal,
        ),
      enabled: Boolean(
        !cityForecastMode &&
        selection.product &&
        selection.domain &&
        time.runTime &&
        time.validTime &&
        layer.field,
      ),
      staleTime: Number.POSITIVE_INFINITY,
    })),
  })

  const bufferedFrames = useMemo<BufferedWeatherFrame[]>(
    () =>
      bufferedTimes.map((time) => ({
        frameId: time.validTime,
        expectedLayerCount: selection.layers.length,
        layers: bufferedLayerQueries.flatMap((query, index) => {
          const request = bufferedLayerRequests[index]
          return request &&
            request.time.validTime === time.validTime &&
            query.data?.validTime === time.validTime
            ? [
                {
                  selectionId: request.layer.id,
                  layer: query.data,
                  opacity: request.layer.opacity,
                  visible: request.layer.visible,
                } satisfies DisplayLayer,
              ]
            : []
        }),
      })),
    [
      bufferedLayerQueries,
      bufferedLayerRequests,
      bufferedTimes,
      selection.layers.length,
    ],
  )

  const weatherLayerBuffer = useWeatherLayers(
    mapInstance,
    mapReady,
    cityForecastMode ? [] : bufferedFrames,
    cityForecastMode ? '' : selection.validTime,
  )
  const activeDisplayLayers =
    bufferedFrames.find((frame) => frame.frameId === selection.validTime)
      ?.layers ?? []
  const displayedFrameReady =
    selection.layers.length > 0 &&
    activeDisplayLayers.length === selection.layers.length &&
    activeDisplayLayers.every(
      (item) => item.layer.validTime === selection.validTime,
    ) &&
    weatherLayerBuffer.activeFrameReady
  const nextPlaybackFrame = nextReadyTimelineFrame(
    times,
    selection.validTime,
    weatherLayerBuffer.readyFrameIds,
  )
  const bufferedFutureCount = bufferedTimes
    .slice(1)
    .filter((time) =>
      weatherLayerBuffer.readyFrameIds.has(time.validTime),
    ).length
  const bufferedFutureTarget = Math.min(
    WEATHER_FRAME_LOOKAHEAD,
    Math.max(0, times.length - 1),
  )
  const playbackBuffering =
    selection.playing &&
    times.length > 1 &&
    (!displayedFrameReady || nextPlaybackFrame === undefined)

  const windQuery = useQuery({
    queryKey: [
      'wind-vectors',
      selection.product,
      selection.domain,
      activeRunTime,
      selection.validTime,
      windViewport,
    ],
    queryFn: ({ signal }) =>
      api.windVectors(
        {
          product: selection.product,
          domain: selection.domain,
          run: activeRunTime,
          validTime: selection.validTime,
          bbox: windViewport!.bbox,
          columns: windViewport!.columns,
          rows: windViewport!.rows,
        },
        signal,
      ),
    enabled: Boolean(
      !wildfireSelected &&
      !cityForecastMode &&
      windVisible &&
      windAvailable &&
      windViewport &&
      selection.product &&
      selection.domain &&
      activeRunTime &&
      selection.validTime,
    ),
    placeholderData: (previousData) => previousData,
    staleTime: 5 * 60_000,
  })

  const windDataMatchesSelection =
    windQuery.data?.product === selection.product &&
    windQuery.data.domain === selection.domain &&
    windQuery.data.runTime === activeRunTime &&
    windQuery.data.validTime === selection.validTime

  useEffect(() => {
    if (
      !selection.playing ||
      !displayedFrameReady ||
      nextPlaybackFrame === undefined
    ) {
      return
    }
    const timeout = window.setTimeout(() => {
      setValidTime(nextPlaybackFrame.validTime)
    }, 1000 / selection.playbackRate)
    return () => window.clearTimeout(timeout)
  }, [
    displayedFrameReady,
    nextPlaybackFrame,
    selection.playbackRate,
    selection.playing,
    setValidTime,
  ])

  useEffect(() => {
    const map = mapInstance.current
    if (!mapReady || !map) return
    const sourceId = 'cwfis-viirs-hotspots'
    const layerId = 'cwfis-viirs-hotspots-circles'
    if (!wildfireSelected) {
      fittedWildfireSnapshot.current = ''
      if (map.getLayer(layerId)) {
        map.setLayoutProperty(layerId, 'visibility', 'none')
      }
      return
    }
    if (!hotspotsQuery.data) {
      if (map.getLayer(layerId)) {
        map.setLayoutProperty(layerId, 'visibility', 'none')
      }
      return
    }
    if (!map.getSource(sourceId)) {
      map.addSource(sourceId, {
        type: 'geojson',
        data: hotspotsQuery.data,
      })
    } else {
      ;(map.getSource(sourceId) as GeoJSONSource).setData(hotspotsQuery.data)
    }
    if (!map.getLayer(layerId)) {
      map.addLayer({
        id: layerId,
        type: 'circle',
        source: sourceId,
        paint: {
          'circle-radius': [
            'interpolate',
            ['linear'],
            ['zoom'],
            2,
            2.5,
            7,
            5,
            12,
            9,
          ],
          'circle-color': [
            'interpolate',
            ['linear'],
            ['coalesce', ['get', 'fwi'], 0],
            0,
            '#ffd166',
            10,
            '#ff9f43',
            30,
            '#ff5c35',
            50,
            '#d7263d',
          ],
          'circle-opacity': 0.82,
          'circle-stroke-color': '#fff3d0',
          'circle-stroke-opacity': 0.7,
          'circle-stroke-width': 0.7,
        },
      })
    }
    map.setLayoutProperty(layerId, 'visibility', 'visible')

    const bounds = hotspotCollectionBounds(hotspotsQuery.data)
    const snapshotKey = bounds
      ? `${hotspotsQuery.data.data_date}/${bounds.join(',')}`
      : ''
    if (bounds && fittedWildfireSnapshot.current !== snapshotKey) {
      map.fitBounds(
        [
          [bounds[0], bounds[1]],
          [bounds[2], bounds[3]],
        ],
        { padding: 48, duration: 600, maxZoom: 7 },
      )
      fittedWildfireSnapshot.current = snapshotKey
    }
  }, [hotspotsQuery.data, mapReady, wildfireSelected])

  useEffect(() => {
    const map = mapInstance.current
    if (!mapReady || !map?.getStyle()) return
    if (
      cityForecastMode ||
      wildfireSelected ||
      !windVisible ||
      !windAvailable ||
      !windQuery.data ||
      !windDataMatchesSelection
    ) {
      if (map.getLayer(WIND_VECTOR_LAYER_ID)) {
        map.setLayoutProperty(WIND_VECTOR_LAYER_ID, 'visibility', 'none')
      }
      return
    }

    if (!map.hasImage(WIND_ARROW_IMAGE_ID)) {
      const arrow = createWindArrowImage()
      if (arrow) {
        map.addImage(WIND_ARROW_IMAGE_ID, arrow, {
          pixelRatio: 2,
          sdf: false,
        })
      }
    }
    if (!map.getSource(WIND_VECTOR_SOURCE_ID)) {
      map.addSource(WIND_VECTOR_SOURCE_ID, {
        type: 'geojson',
        data: windQuery.data,
      })
    } else {
      ;(map.getSource(WIND_VECTOR_SOURCE_ID) as GeoJSONSource).setData(
        windQuery.data,
      )
    }
    if (
      !map.getLayer(WIND_VECTOR_LAYER_ID) &&
      map.hasImage(WIND_ARROW_IMAGE_ID)
    ) {
      map.addLayer(
        {
          id: WIND_VECTOR_LAYER_ID,
          type: 'symbol',
          source: WIND_VECTOR_SOURCE_ID,
          layout: {
            'icon-image': WIND_ARROW_IMAGE_ID,
            'icon-size': windSize,
            'icon-rotate': ['get', 'bearing'],
            'icon-rotation-alignment': 'map',
            'icon-pitch-alignment': 'map',
            'icon-allow-overlap': true,
            'icon-ignore-placement': true,
          },
          paint: {
            'icon-opacity': 1,
          },
        },
        windInsertionPoint(map),
      )
    }
    if (map.getLayer(WIND_VECTOR_LAYER_ID)) {
      map.setLayoutProperty(WIND_VECTOR_LAYER_ID, 'visibility', 'visible')
      map.moveLayer(WIND_VECTOR_LAYER_ID, windInsertionPoint(map))
    }
  }, [
    cityForecastMode,
    displayedFrameReady,
    mapReady,
    selection.validTime,
    weatherLayerBuffer.activeFrameReady,
    wildfireSelected,
    windAvailable,
    windDataMatchesSelection,
    windQuery.data,
    windVisible,
  ])

  const sampleQuery = useQuery({
    queryKey: [
      'sample',
      selection.product,
      activeRunTime,
      selection.validTime,
      samplePoint,
      selection.layers.map((layer) => layer.field),
    ],
    queryFn: ({ signal }) =>
      api.sample(
        {
          product: selection.product,
          domain: selection.domain,
          run: activeRunTime,
          validTime: selection.validTime,
          longitude: samplePoint!.longitude,
          latitude: samplePoint!.latitude,
          fields: selection.layers
            .filter((layer) => layer.visible)
            .map((layer) => layer.field),
        },
        signal,
      ),
    enabled: Boolean(
      !cityForecastMode &&
      samplePoint &&
      activeRunTime &&
      selection.validTime &&
      selection.layers.length > 0,
    ),
  })

  useEffect(() => {
    if (!mapContainer.current || mapInstance.current) return
    let cancelled = false
    void import('maplibre-gl').then(({ default: maplibregl }) => {
      if (cancelled || !mapContainer.current || mapInstance.current) return
      const map = new maplibregl.Map({
        container: mapContainer.current,
        style: baseStyle,
        center: [-96, 57],
        zoom: 2.8,
        minZoom: 1.8,
        maxZoom: 14,
        attributionControl: false,
      })
      map.addControl(
        new maplibregl.NavigationControl({ visualizePitch: true }),
        'top-right',
      )
      map.addControl(
        new maplibregl.AttributionControl({ compact: true }),
        'bottom-right',
      )
      map.on('load', () => setMapReady(true))
      const updateMapViewport = () => {
        const center = map.getCenter()
        setCoordinate({ longitude: center.lng, latitude: center.lat })
        const viewport = windViewportFromMap(map)
        setWindViewport((current) =>
          sameWindViewport(current, viewport) ? current : viewport,
        )
      }
      map.on('load', updateMapViewport)
      map.on('moveend', updateMapViewport)
      map.on('resize', updateMapViewport)
      map.on('click', (event) => {
        if (cityForecastModeRef.current) return
        const point = {
          longitude: event.lngLat.lng,
          latitude: event.lngLat.lat,
        }
        setSamplePoint(point)
        sampleMarker.current?.remove()
        sampleMarker.current = new maplibregl.Marker({ color: '#56e0d2' })
          .setLngLat(event.lngLat)
          .addTo(map)
      })
      mapInstance.current = map
    })

    return () => {
      cancelled = true
      sampleMarker.current?.remove()
      for (const marker of cityForecastMarkers.current) marker.remove()
      cityForecastMarkers.current = []
      mapInstance.current?.remove()
      mapInstance.current = null
    }
  }, [])

  useEffect(() => {
    const map = mapInstance.current
    if (!mapReady || !map) return
    if (cityForecastMode) {
      sampleMarker.current?.remove()
      sampleMarker.current = null
      setSamplePoint(null)
      if (!fittedCityForecast.current) {
        map.fitBounds(NOVA_SCOTIA_BOUNDS, {
          padding: 48,
          duration: 600,
          // Limit only the initial overview, not the user's subsequent zoom.
          maxZoom: CITY_FORECAST_OVERVIEW_ZOOM,
        })
        fittedCityForecast.current = true
      }
      return
    }
    fittedCityForecast.current = false
  }, [cityForecastMode, mapReady])

  useEffect(() => {
    const map = mapInstance.current
    for (const marker of cityForecastMarkers.current) marker.remove()
    cityForecastMarkers.current = []
    if (!cityForecastMode || !mapReady || !map || !cityForecastQuery.data) {
      return
    }
    let cancelled = false
    const bounds = map.getBounds()
    const visibleFeatures = cityForecastQuery.data.features.filter((feature) =>
      cityForecastInBounds(feature.geometry.coordinates, [
        bounds.getWest(),
        bounds.getSouth(),
        bounds.getEast(),
        bounds.getNorth(),
      ]),
    )
    const container = map.getContainer()
    if (!container.clientWidth || !container.clientHeight) return
    void import('maplibre-gl').then(({ default: maplibregl }) => {
      if (cancelled || mapInstance.current !== map) return
      const mapRect = container.getBoundingClientRect()
      const workspace = container.closest('.workspace') ?? container
      const obstacles = [
        ...workspace.querySelectorAll(
          '.map-state, .map-valid-time, .coordinate-chip, .maplibregl-ctrl, .control-panel',
        ),
      ]
        .map((element) => element.getBoundingClientRect())
        .filter(
          (rect) =>
            rect.width > 0 &&
            rect.height > 0 &&
            rect.right > mapRect.left &&
            rect.left < mapRect.right &&
            rect.bottom > mapRect.top &&
            rect.top < mapRect.bottom,
        )
        .map((rect) => ({
          left: Math.max(0, rect.left - mapRect.left),
          top: Math.max(0, rect.top - mapRect.top),
          width:
            Math.min(mapRect.right, rect.right) -
            Math.max(mapRect.left, rect.left),
          height:
            Math.min(mapRect.bottom, rect.bottom) -
            Math.max(mapRect.top, rect.top),
        }))

      // Measure all cards in one hidden batch using their real font/content
      // sizes. Forecast text can wrap, so a guessed height causes collisions.
      const cards = visibleFeatures.map((feature) => ({
        feature,
        element: cityForecastLabel(feature),
      }))
      const fragment = document.createDocumentFragment()
      for (const { element } of cards) {
        element.style.visibility = 'hidden'
        fragment.append(element)
      }
      container.append(fragment)
      const labels = cards.map(({ feature, element }) => ({
        id: feature.properties.areaId,
        anchor: map.project(feature.geometry.coordinates),
        width: element.getBoundingClientRect().width,
        height: element.getBoundingClientRect().height,
      }))
      for (const { element } of cards) element.remove()
      const placements = layoutCityForecastLabels(
        labels,
        {
          width: container.clientWidth,
          height: container.clientHeight,
        },
        obstacles,
      )
      cityForecastMarkers.current = cards.map(({ feature, element }, index) => {
        const { offset } = placements[index]
        const line = forecastLeaderLine(offset, labels[index])
        element.style.visibility = ''
        element.style.setProperty('--forecast-anchor-x', `${line.anchor.x}px`)
        element.style.setProperty('--forecast-anchor-y', `${line.anchor.y}px`)
        element.style.setProperty('--forecast-line-x', `${line.start.x}px`)
        element.style.setProperty('--forecast-line-y', `${line.start.y}px`)
        element.style.setProperty('--forecast-line-length', `${line.length}px`)
        element.style.setProperty('--forecast-line-angle', `${line.angle}rad`)
        element.style.setProperty(
          '--forecast-pointer-display',
          line.length > 0 ? 'block' : 'none',
        )
        const marker = new maplibregl.Marker({
          element,
          anchor: 'center',
          offset,
        })
          .setLngLat(feature.geometry.coordinates)
          .addTo(map)
        return marker
      })
    })
    return () => {
      cancelled = true
      for (const marker of cityForecastMarkers.current) marker.remove()
      cityForecastMarkers.current = []
    }
  }, [
    cityForecastMode,
    cityForecastQuery.data,
    controlsOpen,
    mapReady,
    windViewport,
  ])

  const primaryField = fields.find(
    (field) => field.code === selection.layers[0]?.field,
  )
  const primaryResolved = activeDisplayLayers[0]?.layer

  useEffect(() => {
    const map = mapInstance.current
    const bounds = primaryResolved?.bounds
    const cameraExtent = bounds ? cameraBounds(bounds) : null
    const domainKey = `${selection.product}/${selection.domain}`
    if (
      cityForecastMode ||
      wildfireSelected ||
      !mapReady ||
      !map ||
      !cameraExtent ||
      fittedDomain.current === domainKey
    )
      return
    map.fitBounds(
      [
        [cameraExtent[0], cameraExtent[1]],
        [cameraExtent[2], cameraExtent[3]],
      ],
      { padding: 36, duration: 600, maxZoom: 5 },
    )
    fittedDomain.current = domainKey
  }, [
    cityForecastMode,
    mapReady,
    primaryResolved?.bounds,
    selection.domain,
    selection.product,
    wildfireSelected,
  ])
  const latestError = cityForecastMode
    ? cityForecastQuery.error
    : wildfireSelected
      ? (hotspotDatesQuery.error ?? hotspotsQuery.error)
      : (productsQuery.error ??
        variablesQuery.error ??
        domainsQuery.error ??
        fieldsQuery.error ??
        timelineQuery.error)
  const loading = cityForecastMode
    ? cityForecastQuery.isLoading
    : wildfireSelected
      ? hotspotDatesQuery.isLoading || hotspotsQuery.isLoading
      : productsQuery.isLoading ||
        variablesQuery.isLoading ||
        domainsQuery.isLoading ||
        fieldsQuery.isLoading ||
        timelineQuery.isLoading

  const stepTime = (delta: number) => {
    if (times.length === 0) return
    const current = activeTimeIndex >= 0 ? activeTimeIndex : 0
    selection.setValidTime(
      times[(current + delta + times.length) % times.length].validTime,
    )
  }

  const stepCityTime = (delta: number) => {
    if (cityTimes.length === 0) return
    const current = activeCityTimeIndex >= 0 ? activeCityTimeIndex : 0
    const destination = Math.max(
      0,
      Math.min(cityTimes.length - 1, current + delta),
    )
    setCityForecastTime(cityTimes[destination])
  }

  const resetTimelineRange = () => {
    setRangeStart('')
    setRangeEnd('')
    selection.setPlaying(false)
    selection.setValidTime('')
  }

  const showLatestTimelineRange = () => {
    selection.setRunTime('')
    resetTimelineRange()
    void queryClient.invalidateQueries({
      queryKey: [
        'timeline',
        selection.product,
        selection.domain,
        timelineField,
      ],
    })
  }

  const setPastWeek = () => {
    const end = new Date()
    const start = new Date(end.getTime() - 7 * 24 * 60 * 60 * 1000)
    selection.setRunTime('')
    setRangeStart(start.toISOString())
    setRangeEnd(end.toISOString())
    selection.setPlaying(false)
    selection.setValidTime('')
  }

  const changeRangeStart = (value: string) => {
    if (!value) return
    selection.setRunTime('')
    const start = fromUtcInput(value)
    const currentEnd = rangeEnd || times.at(-1)?.validTime
    const end =
      currentEnd && new Date(currentEnd) > new Date(start)
        ? currentEnd
        : new Date(
            new Date(start).getTime() + 24 * 60 * 60 * 1000,
          ).toISOString()
    setRangeStart(start)
    setRangeEnd(end)
    selection.setPlaying(false)
    selection.setValidTime('')
  }

  const changeRangeEnd = (value: string) => {
    if (!value) return
    selection.setRunTime('')
    const end = fromUtcInput(value)
    const currentStart = rangeStart || times[0]?.validTime
    const start =
      currentStart && new Date(currentStart) < new Date(end)
        ? currentStart
        : new Date(new Date(end).getTime() - 24 * 60 * 60 * 1000).toISOString()
    setRangeStart(start)
    setRangeEnd(end)
    selection.setPlaying(false)
    selection.setValidTime('')
  }

  const displayedRangeStart = rangeStart || times[0]?.validTime
  const displayedRangeEnd = rangeEnd || times.at(-1)?.validTime
  const timelineRunCount = new Set(times.map((time) => time.runTime)).size

  return (
    <main
      className={`app-shell ${wildfireSelected ? 'wildfire-mode' : ''} ${
        cityForecastMode ? 'city-forecast-mode' : ''
      }`}
    >
      <header className="topbar">
        <button
          className="brand-mark"
          type="button"
          aria-label="Toggle layer controls"
          onClick={() => setControlsOpen((open) => !open)}
        >
          <AppIcon />
        </button>
        <div className="brand-copy">
          <p className="eyebrow">ECCC MODEL EXPLORER</p>
          <h1>Weather Model Atlas</h1>
        </div>
        <a
          className="forecast-page-link"
          href="/forecast"
          aria-label="Open hourly and seven-day forecast"
        >
          <span className="forecast-page-link-icon" aria-hidden="true">
            <svg viewBox="0 0 32 32">
              <circle cx="12" cy="11" r="5" />
              <path d="M10 23.5h13.2a4.8 4.8 0 0 0 .5-9.6 7 7 0 0 0-13-1.4A5.5 5.5 0 0 0 10 23.5Z" />
            </svg>
          </span>
          <span className="forecast-page-link-copy">
            <strong>Forecast</strong>
            <small>Hourly &amp; 7-day</small>
          </span>
          <svg
            className="forecast-page-link-arrow"
            viewBox="0 0 16 16"
            aria-hidden="true"
          >
            <path d="m6 3.5 4.5 4.5L6 12.5" />
          </svg>
        </a>
        <div className={`run-status ${latestError ? 'error' : ''}`}>
          <span className="status-dot" />
          <div>
            <small>
              {latestError
                ? 'Catalogue unavailable'
                : loading
                  ? 'Loading catalogue'
                  : cityForecastMode
                    ? 'Official seven-day forecast'
                    : wildfireSelected
                      ? hotspotDate === latestHotspotDate
                        ? 'Latest VIIRS observations'
                        : 'Archived VIIRS observations'
                      : 'Frame model run'}
            </small>
            <strong>
              {cityForecastMode && cityForecastQuery.data
                ? `${cityForecastQuery.data.featureCount} forecast regions · issued ${formatUtc(cityForecastQuery.data.issuedAt)}`
                : wildfireSelected && hotspotsQuery.data
                  ? `${hotspotsQuery.data.feature_count.toLocaleString()} hotspots · ${hotspotsQuery.data.data_date}`
                  : activeRunTime
                    ? formatUtc(activeRunTime)
                    : latestError
                      ? latestError.message
                      : 'No data published'}
            </strong>
          </div>
        </div>
      </header>

      <section className="workspace">
        <aside className={`control-panel ${controlsOpen ? 'open' : ''}`}>
          <div className="panel-heading">
            <div>
              <p className="eyebrow">FORECAST CATALOGUE</p>
              <h2>{cityForecastMode ? '7-day forecast' : 'Map layers'}</h2>
            </div>
            <span className="layer-count">
              {(cityForecastMode
                ? (cityForecastQuery.data?.featureCount ?? 0)
                : wildfireSelected
                  ? 1
                  : selection.layers.length +
                    Number(windVisible && windAvailable)
              )
                .toString()
                .padStart(2, '0')}
            </span>
          </div>

          <div className="view-mode-switch" aria-label="Map view">
            <button
              type="button"
              className={!cityForecastMode ? 'active' : ''}
              aria-pressed={!cityForecastMode}
              onClick={() => setViewMode('layers')}
            >
              Map overlays
            </button>
            <button
              type="button"
              className={cityForecastMode ? 'active' : ''}
              aria-pressed={cityForecastMode}
              onClick={() => {
                selection.setPlaying(false)
                setViewMode('city-forecast')
              }}
            >
              7-day forecast
            </button>
          </div>

          {!cityForecastMode && (
            <div className="selection-grid">
              <label className="full-width">
                Variable
                <select
                  value={selection.variable}
                  onChange={(event) => {
                    resetTimelineRange()
                    selection.setVariable(event.target.value)
                  }}
                  disabled={variablesQuery.isLoading}
                >
                  {variablesQuery.isLoading && (
                    <option value="">Loading variables…</option>
                  )}
                  {groupedSelectableVariables.map((group) => (
                    <optgroup key={group.code} label={group.label}>
                      {group.items.map((variable) => (
                        <option key={variable.code} value={variable.code}>
                          {variableLabel(variable)}
                        </option>
                      ))}
                    </optgroup>
                  ))}
                </select>
              </label>

              {!wildfireSelected && (
                <>
                  <label>
                    Data product
                    <select
                      value={selection.product}
                      onChange={(event) => {
                        resetTimelineRange()
                        selection.setProduct(event.target.value)
                      }}
                      disabled={compatibleProducts.length === 0}
                    >
                      {compatibleProducts.length === 0 && (
                        <option value="">No compatible products</option>
                      )}
                      {compatibleProducts.map((product) => (
                        <option key={product.code} value={product.code}>
                          {product.name}
                        </option>
                      ))}
                    </select>
                  </label>

                  <label>
                    Domain
                    <select
                      value={selection.domain}
                      onChange={(event) => {
                        resetTimelineRange()
                        selection.setDomain(event.target.value)
                      }}
                      disabled={domains.length === 0}
                    >
                      {domains.length === 0 && (
                        <option value="">No domains</option>
                      )}
                      {domains.map((domain) => (
                        <option key={domain.code} value={domain.code}>
                          {domain.name}
                        </option>
                      ))}
                    </select>
                  </label>
                </>
              )}
            </div>
          )}

          {!cityForecastMode &&
            (wildfireSelected || selection.product === 'flexpart_smoke') && (
              <button
                className="smoke-build-button"
                type="button"
                onClick={() => {
                  setSmokeBuilderBbox(smokeBboxFromMap(mapInstance.current))
                  setSmokeBuilderOpen(true)
                }}
              >
                <span>+</span>
                <div>
                  <strong>Build smoke run</strong>
                  <small>CFFEPS emissions · FLEXPART transport</small>
                </div>
              </button>
            )}

          {cityForecastMode ? (
            <>
              <section className="timeline-range-card city-forecast-card">
                <div className="timeline-range-heading">
                  <div>
                    <p className="eyebrow">OFFICIAL 7-DAY FORECAST</p>
                    <strong>
                      {cityForecastQuery.data?.features[0]?.properties.period ??
                        'Loading forecast period…'}
                    </strong>
                  </div>
                  <button
                    type="button"
                    className="timeline-now-button"
                    onClick={() =>
                      cityTimes[0] && setCityForecastTime(cityTimes[0])
                    }
                    disabled={
                      cityTimes.length === 0 ||
                      cityForecastTime === cityTimes[0]
                    }
                    title="Return to the current forecast period"
                  >
                    Now
                  </button>
                </div>
                <div className="timeline-range-summary">
                  <span>
                    {cityForecastQuery.data?.featureCount ?? 0} Nova Scotia
                    forecast regions
                  </span>
                  <span>{cityTimes.length} half-day periods</span>
                </div>
                <p>
                  ECCC Nova Scotia regional text forecasts, shown without a
                  colour contour. Zoom in to focus on a few locations; only
                  towns in view are labelled. Forecasts cover their named
                  regions.
                </p>
                {cityForecastQuery.error && (
                  <p className="timeline-warning">
                    {cityForecastQuery.error.message}
                  </p>
                )}
              </section>

              <section className="forecast-field-guide">
                <p className="eyebrow">LABEL VALUES</p>
                <dl>
                  <div>
                    <dt>Temp</dt>
                    <dd>Forecast high or low · °C</dd>
                  </div>
                  <div>
                    <dt>Hum</dt>
                    <dd>Relative humidity · %</dd>
                  </div>
                  <div>
                    <dt>Precip chance</dt>
                    <dd>Issued probability (%) or forecast wording</dd>
                  </div>
                  <div>
                    <dt>Precip Amount</dt>
                    <dd>Issued amount · mm or cm</dd>
                  </div>
                </dl>
                <p>
                  When no percentage is issued, rain or snow wording is shown
                  instead where available. A dash for the amount means ECCC did
                  not issue a total for that period, not that no precipitation
                  is expected. Open the local forecast for model-supplied
                  amounts.
                </p>
              </section>

              <section className="forecast-source-note">
                <strong>ECCC City Page Weather</strong>
                <span>
                  Updated at least hourly, with amendments collected every 15
                  minutes.
                </span>
              </section>
            </>
          ) : wildfireSelected ? (
            <>
              <section className="timeline-range-card">
                <div className="timeline-range-heading">
                  <div>
                    <p className="eyebrow">OBSERVATION DATE</p>
                    <strong>Daily VIIRS hotspot snapshot</strong>
                  </div>
                  <button
                    type="button"
                    className="timeline-now-button"
                    onClick={() => setHotspotDate(latestHotspotDate)}
                    disabled={
                      !latestHotspotDate || hotspotDate === latestHotspotDate
                    }
                    title="Select the newest archived hotspot day"
                  >
                    Now
                  </button>
                </div>
                <div className="timeline-range-inputs">
                  <label>
                    Observation date
                    <input
                      type="date"
                      value={hotspotDate}
                      min={hotspotDatesQuery.data?.availableStart ?? undefined}
                      max={latestHotspotDate || undefined}
                      onChange={(event) => setHotspotDate(event.target.value)}
                      disabled={
                        hotspotDatesQuery.isLoading || hotspotDates.length === 0
                      }
                    />
                  </label>
                </div>
                <div className="timeline-range-summary">
                  <span>
                    {hotspotDates.length} archived day
                    {hotspotDates.length === 1 ? '' : 's'}
                  </span>
                  <span>
                    {selectedHotspotDate
                      ? `${selectedHotspotDate.featureCount.toLocaleString()} detections`
                      : 'Date not archived'}
                  </span>
                </div>
                <div className="hotspot-date-navigation">
                  <button
                    type="button"
                    className="text-button"
                    onClick={() =>
                      previousHotspotDate && setHotspotDate(previousHotspotDate)
                    }
                    disabled={!previousHotspotDate}
                    aria-label="Previous available hotspot date"
                  >
                    ← Previous
                  </button>
                  <button
                    type="button"
                    className="text-button"
                    onClick={() =>
                      nextHotspotDate && setHotspotDate(nextHotspotDate)
                    }
                    disabled={!nextHotspotDate}
                    aria-label="Next available hotspot date"
                  >
                    Next →
                  </button>
                </div>
                <p>
                  Each selection shows one UTC day. Satellite swaths, clouds,
                  and source availability can make coverage vary between days.
                </p>
                {hotspotDatesQuery.error && (
                  <p className="timeline-warning">
                    {hotspotDatesQuery.error.message}
                  </p>
                )}
              </section>

              <section className="legend-card wildfire-legend">
                <div className="legend-title">
                  <span>Fire Weather Index</span>
                  <strong>{hotspotsQuery.data?.sensor ?? 'VIIRS-I'}</strong>
                </div>
                <div
                  className="hotspot-ramp"
                  aria-label="Fire Weather Index colour ramp"
                />
                <div className="hotspot-ramp-labels">
                  <span>Low FWI</span>
                  <span>High FWI</span>
                </div>
                <p className="wildfire-summary">
                  {hotspotsQuery.isLoading || !hotspotDate
                    ? 'Loading the selected CWFIS snapshot…'
                    : hotspotsQuery.error
                      ? hotspotsQuery.error.message
                      : `${hotspotsQuery.data?.feature_count.toLocaleString() ?? 0} detections · ${hotspotsQuery.data?.nominal_resolution_metres ?? 375} m nominal resolution`}
                </p>
              </section>
            </>
          ) : (
            <>
              <section className="timeline-range-card">
                <div className="timeline-range-heading">
                  <div>
                    <p className="eyebrow">ANIMATION WINDOW</p>
                    <strong>
                      {selection.runTime
                        ? 'Selected FLEXPART run'
                        : 'Best forecast by valid time'}
                    </strong>
                  </div>
                  <button
                    type="button"
                    className="timeline-now-button"
                    onClick={showLatestTimelineRange}
                    disabled={Boolean(
                      !selection.product || !selection.domain || !timelineField,
                    )}
                    title="Reset to the latest available data and the following 24 hours"
                  >
                    Now
                  </button>
                </div>
                <div className="timeline-range-inputs">
                  <label>
                    Start (UTC)
                    <input
                      type="datetime-local"
                      value={toUtcInput(displayedRangeStart)}
                      onChange={(event) => changeRangeStart(event.target.value)}
                    />
                  </label>
                  <label>
                    End (UTC)
                    <input
                      type="datetime-local"
                      value={toUtcInput(displayedRangeEnd)}
                      onChange={(event) => changeRangeEnd(event.target.value)}
                    />
                  </label>
                </div>
                <div className="timeline-range-summary">
                  <span>
                    {times.length} frame{times.length === 1 ? '' : 's'} ·{' '}
                    {timelineRunCount} model run
                    {timelineRunCount === 1 ? '' : 's'}
                  </span>
                  <button
                    type="button"
                    className="text-button"
                    onClick={setPastWeek}
                  >
                    Past 7 days
                  </button>
                </div>
                <p>
                  {selection.runTime
                    ? `Showing only frames published by the run requested at ${formatUtc(selection.runTime)}.`
                    : 'Each valid time uses the available prediction with the shortest forecast lead.'}
                </p>
                {timelineQuery.data?.truncated && (
                  <p className="timeline-warning">
                    This range exceeds 1,000 frames. Narrow it to view every
                    frame.
                  </p>
                )}
              </section>

              <div className="layer-stack">
                {selection.layers.map((layer, index) => (
                  <LayerEditor
                    key={layer.id}
                    layerId={layer.id}
                    fieldCode={layer.field}
                    fields={fields}
                    opacity={layer.opacity}
                    visible={layer.visible}
                    displayMinimum={layer.displayMinimum}
                    displayMaximum={layer.displayMaximum}
                    resolved={
                      activeDisplayLayers.find(
                        (item) => item.selectionId === layer.id,
                      )?.layer
                    }
                    opacityCutoff={layer.opacityCutoff}
                    canMoveDown={index > 0}
                    canMoveUp={index < selection.layers.length - 1}
                    canRemove={selection.layers.length > 1}
                  />
                ))}
              </div>

              <button
                className="add-layer-button"
                type="button"
                onClick={() => fields[0] && selection.addLayer(fields[0].code)}
                disabled={fields.length === 0 || selection.layers.length >= 3}
              >
                <span>+</span> Add overlay{' '}
                {selection.layers.length >= 3 && '· limit reached'}
              </button>

              {windAvailable && (
                <section className="wind-overlay-card">
                  <div className="wind-overlay-heading">
                    <div>
                      <p className="eyebrow">VECTOR OVERLAY</p>
                      <strong>10 m wind arrows</strong>
                    </div>
                    <button
                      type="button"
                      className={`wind-toggle ${windVisible ? 'active' : ''}`}
                      onClick={() => setWindVisible((visible) => !visible)}
                      aria-pressed={windVisible}
                      aria-label={`${windVisible ? 'Hide' : 'Show'} 10 metre wind arrows`}
                    >
                      <span />
                      {windVisible ? 'On' : 'Off'}
                    </button>
                  </div>
                  <p>
                    Larger arrows indicate stronger wind. Dark arrows with white
                    outlines point where the air is moving and remain distinct
                    from the weather colours.
                  </p>
                  {windVisible && windQuery.isFetching && (
                    <small>Updating wind field…</small>
                  )}
                  {windVisible && windQuery.error && (
                    <small className="wind-overlay-error">
                      Wind vectors are unavailable for this frame.
                    </small>
                  )}
                </section>
              )}

              {primaryField && (
                <section className="legend-card">
                  <div className="legend-title">
                    <span>{primaryField.name}</span>
                    <strong>{primaryField.unit}</strong>
                  </div>
                  <div
                    className="color-ramp"
                    style={{
                      background: paletteGradient(
                        primaryField,
                        primaryResolved,
                      ),
                    }}
                  />
                  <div className="legend-labels">
                    <span>
                      {primaryResolved?.legend.minimum ??
                        primaryField.defaultMin}
                    </span>
                    <span>
                      {Math.round(
                        ((primaryResolved?.legend.minimum ??
                          primaryField.defaultMin) +
                          (primaryResolved?.legend.maximum ??
                            primaryField.defaultMax)) /
                          2,
                      )}
                    </span>
                    <span>
                      {primaryResolved?.legend.maximum ??
                        primaryField.defaultMax}
                    </span>
                  </div>
                </section>
              )}

              {!loading && products.length === 0 && !latestError && (
                <div className="empty-state">
                  <strong>
                    The platform is ready for its first processed run.
                  </strong>
                  <p>
                    Enable an ingestion DAG after inventorying the desired ECCC
                    fields.
                  </p>
                </div>
              )}
              {latestError && (
                <div className="empty-state error">
                  <strong>Catalogue connection failed.</strong>
                  <p>{latestError.message}</p>
                </div>
              )}
            </>
          )}
        </aside>

        <div className="map-stage">
          <div
            ref={mapContainer}
            className="map"
            aria-label="Interactive ECCC weather map"
          />
          <div
            className={`map-state ${mapReady ? 'ready' : ''}`}
            role="status"
            aria-live="polite"
          >
            <span />{' '}
            {mapReady
              ? cityForecastMode
                ? cityForecastQuery.isLoading
                  ? 'Loading official forecast regions'
                  : cityForecastQuery.error
                    ? 'Official forecast regions unavailable'
                    : `${cityForecastQuery.data?.featureCount ?? 0} official forecast regions ready`
                : wildfireSelected
                  ? hotspotDatesQuery.isLoading || hotspotsQuery.isLoading
                    ? 'Loading VIIRS hotspots'
                    : hotspotDatesQuery.error || hotspotsQuery.error
                      ? 'VIIRS hotspots unavailable'
                      : `${hotspotsQuery.data?.feature_count.toLocaleString() ?? 0} VIIRS hotspots ready`
                  : playbackBuffering
                    ? `Buffering next frame · current frame held · ${bufferedFutureCount}/${bufferedFutureTarget} ahead ready`
                    : `${activeDisplayLayers.length} weather layer${activeDisplayLayers.length === 1 ? '' : 's'} ready · ${bufferedFutureCount}/${bufferedFutureTarget} ahead buffered${
                        windVisible && windAvailable
                          ? windQuery.isFetching
                            ? ' · wind updating'
                            : windDataMatchesSelection
                              ? ` · ${windQuery.data?.featureCount ?? 0} wind arrows`
                              : ' · wind unavailable'
                          : ''
                      }`
              : 'Loading basemap'}
          </div>
          <div className="map-valid-time">
            <small>
              {cityForecastMode
                ? 'FORECAST PERIOD · UTC'
                : wildfireSelected
                  ? 'OBSERVATION TIME · UTC'
                  : 'VALID TIME · UTC'}
            </small>
            {displayedValidTime ? (
              <time dateTime={displayedValidTime}>
                {formatUtcTimestamp(displayedValidTime)}
              </time>
            ) : (
              <strong>NO DATA SELECTED</strong>
            )}
          </div>
          <div className="coordinate-chip">
            {Math.abs(coordinate.latitude).toFixed(2)}°{' '}
            {coordinate.latitude >= 0 ? 'N' : 'S'} ·{' '}
            {Math.abs(coordinate.longitude).toFixed(2)}°{' '}
            {coordinate.longitude >= 0 ? 'E' : 'W'}
          </div>

          {activeSmokeRunId && (
            <SmokeRunStatus
              runId={activeSmokeRunId}
              onClose={() => setActiveSmokeRunId('')}
              onPublished={(run) => {
                void queryClient.invalidateQueries({ queryKey: ['products'] })
                void queryClient.invalidateQueries({ queryKey: ['variables'] })
                void queryClient.invalidateQueries({ queryKey: ['timeline'] })
                setRangeStart('')
                setRangeEnd('')
                selection.setVariable('wildfire_pm25_surface')
                selection.setProduct('flexpart_smoke')
                selection.setDomain('scenario_domain')
                selection.setRunTime(run.requestedAt)
                selection.ensureLayer('wildfire_pm25_surface')
                setActiveSmokeRunId('')
              }}
            />
          )}

          {!cityForecastMode && !wildfireSelected && samplePoint && (
            <section className="sample-panel" aria-live="polite">
              <div className="sample-heading">
                <div>
                  <p className="eyebrow">POINT INSPECTION</p>
                  <strong>
                    {samplePoint.latitude.toFixed(4)},{' '}
                    {samplePoint.longitude.toFixed(4)}
                  </strong>
                </div>
                <button
                  type="button"
                  onClick={() => setSamplePoint(null)}
                  aria-label="Close sample"
                >
                  ×
                </button>
              </div>
              {sampleQuery.isLoading && (
                <p className="sample-loading">Reading model grids…</p>
              )}
              {sampleQuery.error && (
                <p className="sample-error">{sampleQuery.error.message}</p>
              )}
              {sampleQuery.data?.values.map((value) => (
                <div className="sample-value" key={value.field}>
                  <span>{value.variable.replaceAll('_', ' ')}</span>
                  <strong>
                    {value.nodata || value.value === null
                      ? 'No data'
                      : `${value.value.toFixed(1)} ${value.unit}`}
                  </strong>
                </div>
              ))}
            </section>
          )}
        </div>
      </section>

      {cityForecastMode ? (
        <footer className="timeline city-forecast-timeline">
          <button
            className="step-button"
            type="button"
            onClick={() => stepCityTime(-1)}
            disabled={activeCityTimeIndex <= 0}
            aria-label="Previous forecast period"
          >
            ‹
          </button>
          <button
            className="play-button city-now-button"
            type="button"
            onClick={() => cityTimes[0] && setCityForecastTime(cityTimes[0])}
            disabled={cityTimes.length === 0 || activeCityTimeIndex <= 0}
            aria-label="Return to current forecast period"
          >
            NOW
          </button>
          <button
            className="step-button"
            type="button"
            onClick={() => stepCityTime(1)}
            disabled={
              activeCityTimeIndex < 0 ||
              activeCityTimeIndex >= cityTimes.length - 1
            }
            aria-label="Next forecast period"
          >
            ›
          </button>

          <div className="time-readout">
            <small>FORECAST PERIOD</small>
            <strong>
              {cityForecastTime ? formatUtc(cityForecastTime) : 'No forecast'}
            </strong>
          </div>
          <div className="slider-wrap">
            <input
              aria-label="Seven-day forecast period"
              type="range"
              min="0"
              max={Math.max(0, cityTimes.length - 1)}
              value={Math.max(0, activeCityTimeIndex)}
              onChange={(event) =>
                setCityForecastTime(cityTimes[Number(event.target.value)] ?? '')
              }
              disabled={cityTimes.length < 2}
            />
            <div className="tick-labels">
              <span>{cityTimes[0] ? formatUtc(cityTimes[0]) : 'CURRENT'}</span>
              <span>{cityTimes.length} PERIODS</span>
              <span>
                {cityTimes.at(-1) ? formatUtc(cityTimes.at(-1)!) : 'DAY 7'}
              </span>
            </div>
          </div>
          <div className="city-forecast-source">
            <small>SOURCE</small>
            <strong>ECCC</strong>
          </div>
          <div className="forecast-badge">
            <small>RANGE</small>
            <strong>7 DAYS</strong>
          </div>
        </footer>
      ) : !wildfireSelected ? (
        <footer className="timeline">
          <button
            className="step-button"
            type="button"
            onClick={() => stepTime(-1)}
            disabled={times.length < 2}
            aria-label="Previous forecast time"
          >
            ‹
          </button>
          <button
            className="play-button"
            type="button"
            onClick={() => selection.setPlaying(!selection.playing)}
            disabled={times.length < 2}
            title={
              times.length < 2
                ? 'Playback requires at least two available frames'
                : undefined
            }
            aria-label={
              selection.playing
                ? 'Pause forecast animation'
                : 'Play forecast animation'
            }
          >
            {selection.playing ? 'Ⅱ' : '▶'}
          </button>
          <button
            className="step-button"
            type="button"
            onClick={() => stepTime(1)}
            disabled={times.length < 2}
            aria-label="Next forecast time"
          >
            ›
          </button>

          <div className="time-readout">
            <small>VALID TIME</small>
            <strong>
              {selection.validTime
                ? formatUtc(selection.validTime)
                : 'No frames'}
            </strong>
          </div>
          <div className="slider-wrap">
            <input
              aria-label="Forecast frame"
              type="range"
              min="0"
              max={Math.max(0, times.length - 1)}
              value={Math.max(0, activeTimeIndex)}
              onChange={(event) =>
                selection.setValidTime(
                  times[Number(event.target.value)]!.validTime,
                )
              }
              disabled={times.length < 2}
            />
            <div className="tick-labels">
              <span>{times[0] ? formatUtc(times[0].validTime) : 'START'}</span>
              <span>{times.length} FRAMES</span>
              <span>
                {times.at(-1) ? formatUtc(times.at(-1)!.validTime) : 'END'}
              </span>
            </div>
          </div>
          <label className="speed-control">
            Speed
            <select
              value={selection.playbackRate}
              onChange={(event) =>
                selection.setPlaybackRate(Number(event.target.value))
              }
            >
              {[0.5, 1, 2, 4].map((rate) => (
                <option key={rate} value={rate}>
                  {rate} fps
                </option>
              ))}
            </select>
          </label>
          <div className="forecast-badge">
            <small>
              {activeTime?.forecastHour === null ? 'ANALYSIS' : 'FORECAST LEAD'}
            </small>
            <strong>
              {activeTime?.forecastHour === null ||
              activeTime?.forecastHour === undefined
                ? (activeTime?.timeKind ?? '—')
                : formatForecastHour(activeTime.forecastHour)}
            </strong>
          </div>
        </footer>
      ) : null}
      <SmokeRunBuilder
        open={smokeBuilderOpen}
        initialBbox={smokeBuilderBbox}
        onClose={() => setSmokeBuilderOpen(false)}
        onSubmitted={(submission) => {
          setSmokeBuilderOpen(false)
          setActiveSmokeRunId(submission.runId)
        }}
      />
    </main>
  )
}
