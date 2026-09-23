// @vitest-environment jsdom

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { App } from './App'
import { useMapSelection } from './store'

const apiMocks = vi.hoisted(() => ({
  cityForecasts: vi.fn(),
  listProducts: vi.fn(),
  listVariables: vi.fn(),
  listHotspotDates: vi.fn(),
  getHotspots: vi.fn(),
  listDomains: vi.fn(),
  listFields: vi.fn(),
  listTimes: vi.fn(),
  listTimeline: vi.fn(),
  resolveLayer: vi.fn(),
  sample: vi.fn(),
  windVectors: vi.fn(),
}))

const mapMocks = vi.hoisted(() => ({
  create: vi.fn(),
  on: vi.fn(),
  fitBounds: vi.fn(),
  setMaxZoom: vi.fn(),
}))

vi.mock('./api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('./api')>()
  return { ...actual, api: apiMocks }
})

vi.mock('maplibre-gl', () => {
  class MapStub {
    container: HTMLElement
    constructor(options: { container: HTMLElement }) {
      this.container = options.container
      mapMocks.create(options)
    }
    addControl() {}
    on = mapMocks.on
    off() {}
    fitBounds = mapMocks.fitBounds
    setMaxZoom = mapMocks.setMaxZoom
    remove() {}
    getLayer() {}
    getBounds() {
      return {
        getWest: () => -66.7,
        getSouth: () => 43.2,
        getEast: () => -59.5,
        getNorth: () => 47.2,
      }
    }
    getContainer() {
      return this.container
    }
    getCanvas() {
      return this.container
    }
    project() {
      return { x: 500, y: 300 }
    }
    getCenter() {
      return { lng: -96, lat: 57 }
    }
    getStyle() {
      return null
    }
  }

  return {
    default: {
      Map: MapStub,
      NavigationControl: class {},
      AttributionControl: class {},
      Marker: class {
        setLngLat() {
          return this
        }
        addTo() {
          return this
        }
        remove() {}
      },
    },
  }
})

const latestFrames = [
  {
    runTime: '2026-07-21T18:00:00Z',
    validTime: '2026-07-21T23:00:00Z',
    forecastHour: 5,
    intervalStart: null,
    intervalEnd: null,
    timeKind: 'instant',
  },
  {
    runTime: '2026-07-21T18:00:00Z',
    validTime: '2026-07-22T23:00:00Z',
    forecastHour: 29,
    intervalStart: null,
    intervalEnd: null,
    timeKind: 'instant',
  },
]

describe('timeline range selector', () => {
  beforeEach(() => {
    useMapSelection.setState({
      variable: '',
      product: '',
      domain: '',
      runTime: '',
      validTime: '',
      layers: [],
      playing: false,
    })
    apiMocks.listProducts.mockResolvedValue([
      {
        code: 'hrdps',
        name: 'HRDPS',
        description: null,
        kind: 'forecast',
        priority: 1,
        latestRunTime: '2026-07-21T18:00:00Z',
      },
    ])
    apiMocks.cityForecasts.mockResolvedValue({
      type: 'FeatureCollection',
      provider: 'eccc',
      product: 'citypage_weather',
      generatedAt: '2026-07-28T19:10:00Z',
      issuedAt: '2026-07-28T19:05:00Z',
      validTime: '2026-07-28T19:00:00Z',
      availableStart: '2026-07-28T19:00:00Z',
      availableEnd: '2026-08-04T21:00:00Z',
      featureCount: 1,
      attribution: 'Environment and Climate Change Canada',
      licenseUrl: 'https://dd.weather.gc.ca/doc/LICENCE_GENERAL.txt',
      features: [
        {
          type: 'Feature',
          id: 'halifax',
          geometry: {
            type: 'Point',
            coordinates: [-63.57, 44.65],
          },
          properties: {
            areaId: 'halifax',
            name: 'Halifax Metro',
            locality: 'Halifax',
            province: 'NS',
            issuedAt: '2026-07-28T19:05:00Z',
            sourceSite: 's0000318',
            period: 'Tuesday night',
            validStart: '2026-07-28T19:00:00Z',
            validEnd: '2026-07-29T09:00:00Z',
            temperatureC: 17,
            temperatureClass: 'low',
            relativeHumidityPercent: 95,
            popPercent: 80,
            precipitationAmount: '10–20 mm',
            condition: 'Rain',
          },
        },
      ],
    })
    apiMocks.listVariables.mockResolvedValue([
      {
        code: 'air_temperature_2m',
        variableCode: 'air_temperature',
        name: 'Air temperature',
        variableClass: 'atmosphere',
        levelCode: '2m',
        levelName: '2 metres above ground',
        unit: 'degC',
        products: ['hrdps'],
      },
    ])
    apiMocks.getHotspots.mockResolvedValue({
      type: 'FeatureCollection',
      data_date: '2026-07-20',
      generated_at: '2026-07-21T07:15:07Z',
      sensor: 'VIIRS-I',
      nominal_resolution_metres: 375,
      feature_count: 2,
      features: [
        {
          type: 'Feature',
          geometry: { type: 'Point', coordinates: [-79.67, 33.19] },
          properties: { observed_at: '2026-07-20T06:16:00Z', fwi: 19.5 },
        },
        {
          type: 'Feature',
          geometry: { type: 'Point', coordinates: [-113.5, 52.1] },
          properties: { observed_at: '2026-07-20T23:38:00Z', fwi: 31 },
        },
      ],
    })
    apiMocks.listHotspotDates.mockResolvedValue({
      items: [
        {
          dataDate: '2026-07-19',
          featureCount: 5,
          firstObservation: '2026-07-19T01:00:00Z',
          lastObservation: '2026-07-19T23:00:00Z',
          bbox: [-130, 30, -60, 68],
        },
        {
          dataDate: '2026-07-20',
          featureCount: 2,
          firstObservation: '2026-07-20T06:16:00Z',
          lastObservation: '2026-07-20T23:38:00Z',
          bbox: [-113.5, 33.19, -79.67, 52.1],
        },
      ],
      availableStart: '2026-07-19',
      availableEnd: '2026-07-20',
    })
    apiMocks.listDomains.mockResolvedValue([
      { code: 'continental', name: 'Continental', bounds: [-141, 39, -42, 84] },
    ])
    apiMocks.listFields.mockResolvedValue([
      {
        code: 'air_temperature_2m',
        variableCode: 'air_temperature',
        name: 'Air temperature',
        variableClass: 'atmosphere',
        levelCode: '2m',
        levelName: '2 metres above ground',
        unit: 'degC',
        palette: [
          { value: -40, color: '#000040' },
          { value: 40, color: '#ff0000' },
        ],
        defaultMin: -40,
        defaultMax: 40,
      },
    ])
    apiMocks.listTimeline.mockResolvedValue({
      items: latestFrames,
      truncated: false,
    })
    apiMocks.listTimes.mockResolvedValue(
      latestFrames.map((frame) => ({
        validTime: frame.validTime,
        forecastHour: frame.forecastHour,
        intervalStart: frame.intervalStart,
        intervalEnd: frame.intervalEnd,
        timeKind: frame.timeKind,
      })),
    )
    apiMocks.resolveLayer.mockResolvedValue({
      product: 'hrdps',
      domain: 'continental',
      runTime: '2026-07-21T18:00:00Z',
      validTime: '2026-07-21T23:00:00Z',
      forecastHour: 5,
      field: 'air_temperature_2m',
      variable: 'air_temperature',
      level: '2m',
      unit: 'degC',
      tileUrl: '/tiles/example/{z}/{x}/{y}.webp',
      token: 'test-token',
      bounds: [-141, 39, -42, 84],
      legend: {
        minimum: -40,
        maximum: 40,
        palette: [
          { value: -40, color: '#000040' },
          { value: 40, color: '#ff0000' },
        ],
      },
    })
  })

  afterEach(() => {
    cleanup()
    vi.clearAllMocks()
  })

  it('uses server-normalized temperature bounds in the editor and preserves manual overrides', async () => {
    const originalLayer = await apiMocks.resolveLayer()
    apiMocks.resolveLayer.mockImplementation(async (request) => ({
      ...originalLayer,
      validTime: request.validTime,
      legend: {
        minimum: request.minimum ?? 0,
        maximum: request.maximum ?? 25,
        palette: [
          { value: request.minimum ?? 0, color: '#000040' },
          { value: request.maximum ?? 25, color: '#ff0000' },
        ],
      },
    }))
    apiMocks.resolveLayer.mockClear()
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false, gcTime: 0 } },
    })
    render(
      <QueryClientProvider client={queryClient}>
        <App />
      </QueryClientProvider>,
    )
    const minimum = (await screen.findByLabelText(
      'Scale minimum',
    )) as HTMLInputElement
    const maximum = screen.getByLabelText('Scale maximum') as HTMLInputElement
    await waitFor(() => {
      expect(minimum.value).toBe('0')
      expect(maximum.value).toBe('25')
    })
    expect(screen.getByText('Automatic colour range · 5°C steps')).toBeTruthy()
    expect(
      screen
        .getByLabelText('Transparent below cutoff for Air temperature')
        .getAttribute('min'),
    ).toBe('0')
    fireEvent.change(minimum, { target: { value: '-5' } })
    await waitFor(() =>
      expect(apiMocks.resolveLayer).toHaveBeenCalledWith(
        expect.objectContaining({ minimum: -5, maximum: 25 }),
        expect.anything(),
      ),
    )
    expect(screen.queryByText('Automatic colour range · 5°C steps')).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'Reset colour scale' }))
    await waitFor(() => {
      expect(minimum.value).toBe('0')
      expect(maximum.value).toBe('25')
    })
    queryClient.clear()
  })

  it('uses the selected icon while keeping the layer toggle functional', async () => {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false, gcTime: 0 } },
    })
    const { container } = render(
      <QueryClientProvider client={queryClient}>
        <App />
      </QueryClientProvider>,
    )
    await screen.findByLabelText('Start (UTC)')
    const toggle = screen.getByRole('button', { name: 'Toggle layer controls' })
    expect(toggle.querySelector('img')?.getAttribute('src')).toBe(
      '/icons/crimson-sky-v1-96.png',
    )
    const controls = container.querySelector('.control-panel')!
    expect(controls.classList.contains('open')).toBe(true)
    fireEvent.click(toggle)
    expect(controls.classList.contains('open')).toBe(false)
    fireEvent.click(toggle)
    expect(controls.classList.contains('open')).toBe(true)
    queryClient.clear()
  })

  it('resets a custom range to the latest available 24-hour window', async () => {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    })
    render(
      <QueryClientProvider client={queryClient}>
        <App />
      </QueryClientProvider>,
    )

    const startInput = await screen.findByLabelText('Start (UTC)')
    const endInput = screen.getByLabelText('End (UTC)')
    const nowButton = screen.getByRole('button', { name: 'Now' })

    await waitFor(() => {
      expect((startInput as HTMLInputElement).value).toBe('2026-07-21T23:00')
      expect((endInput as HTMLInputElement).value).toBe('2026-07-22T23:00')
      expect((nowButton as HTMLButtonElement).disabled).toBe(false)
      expect(screen.getByText('2026-07-21 23:00:00')).toBeTruthy()
    })

    fireEvent.change(startInput, { target: { value: '2026-07-14T00:00' } })
    await waitFor(() => {
      expect(apiMocks.listTimeline).toHaveBeenCalledWith(
        'hrdps',
        'continental',
        'air_temperature_2m',
        {
          start: '2026-07-14T00:00:00.000Z',
          end: '2026-07-22T23:00:00Z',
        },
        expect.anything(),
      )
    })

    apiMocks.listTimeline.mockClear()
    fireEvent.click(nowButton)

    await waitFor(() => {
      expect(apiMocks.listTimeline).toHaveBeenCalledWith(
        'hrdps',
        'continental',
        'air_temperature_2m',
        undefined,
        expect.anything(),
      )
      expect((startInput as HTMLInputElement).value).toBe('2026-07-21T23:00')
      expect((endInput as HTMLInputElement).value).toBe('2026-07-22T23:00')
    })
  })

  it('offers a wind-arrow overlay when both 10 metre components exist', async () => {
    apiMocks.listFields.mockResolvedValue([
      {
        code: 'air_temperature_2m',
        variableCode: 'air_temperature',
        name: 'Air temperature',
        variableClass: 'atmosphere',
        levelCode: '2m',
        levelName: '2 metres above ground',
        unit: 'degC',
        palette: [{ value: -40, color: '#000040' }],
        defaultMin: -40,
        defaultMax: 40,
      },
      {
        code: 'wind_u_10m',
        variableCode: 'wind_u',
        name: 'Eastward wind',
        variableClass: 'atmosphere',
        levelCode: '10m',
        levelName: '10 metres above ground',
        unit: 'm/s',
        palette: [{ value: -40, color: '#000040' }],
        defaultMin: -40,
        defaultMax: 40,
      },
      {
        code: 'wind_v_10m',
        variableCode: 'wind_v',
        name: 'Northward wind',
        variableClass: 'atmosphere',
        levelCode: '10m',
        levelName: '10 metres above ground',
        unit: 'm/s',
        palette: [{ value: -40, color: '#000040' }],
        defaultMin: -40,
        defaultMax: 40,
      },
    ])
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    })
    render(
      <QueryClientProvider client={queryClient}>
        <App />
      </QueryClientProvider>,
    )

    const toggle = await screen.findByRole('button', {
      name: 'Hide 10 metre wind arrows',
    })
    fireEvent.click(toggle)

    expect(
      screen.getByRole('button', { name: 'Show 10 metre wind arrows' }),
    ).toBeTruthy()
    expect(screen.getByText('10 m wind arrows')).toBeTruthy()
  })

  it('pins a completed FLEXPART run until the user returns to Now', async () => {
    const requestedAt = '2026-07-22T12:34:56Z'
    useMapSelection.setState({
      variable: 'wildfire_pm25_surface',
      product: 'flexpart_smoke',
      domain: 'scenario_domain',
      runTime: requestedAt,
      validTime: '',
      layers: [
        {
          id: 'smoke-layer',
          field: 'wildfire_pm25_surface',
          opacity: 0.78,
          visible: true,
        },
      ],
      playing: false,
    })
    apiMocks.listProducts.mockResolvedValue([
      {
        code: 'flexpart_smoke',
        name: 'FLEXPART smoke',
        description: null,
        kind: 'simulation',
        priority: 1,
        latestRunTime: requestedAt,
      },
    ])
    apiMocks.listVariables.mockResolvedValue([
      {
        code: 'wildfire_pm25_surface',
        variableCode: 'wildfire_pm25',
        name: 'Wildfire PM2.5',
        variableClass: 'wildfire',
        levelCode: 'surface',
        levelName: 'Surface',
        unit: 'µg/m³',
        products: ['flexpart_smoke'],
      },
    ])
    apiMocks.listDomains.mockResolvedValue([
      {
        code: 'scenario_domain',
        name: 'Scenario domain',
        bounds: [-66, 43, -60, 48],
      },
    ])
    apiMocks.listFields.mockResolvedValue([
      {
        code: 'wildfire_pm25_surface',
        variableCode: 'wildfire_pm25',
        name: 'Wildfire PM2.5',
        variableClass: 'wildfire',
        levelCode: 'surface',
        levelName: 'Surface',
        unit: 'µg/m³',
        palette: [{ value: 0, color: '#ffffff' }],
        defaultMin: 0,
        defaultMax: 100,
      },
    ])

    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    })
    render(
      <QueryClientProvider client={queryClient}>
        <App />
      </QueryClientProvider>,
    )

    await waitFor(() => {
      expect(apiMocks.listTimes).toHaveBeenCalledWith(
        'flexpart_smoke',
        requestedAt,
        'wildfire_pm25_surface',
        expect.anything(),
      )
      expect(screen.getByText('Selected FLEXPART run')).toBeTruthy()
    })
    expect(apiMocks.listTimeline).not.toHaveBeenCalled()

    fireEvent.click(screen.getByRole('button', { name: 'Now' }))

    await waitFor(() => {
      expect(apiMocks.listTimeline).toHaveBeenCalledWith(
        'flexpart_smoke',
        'scenario_domain',
        'wildfire_pm25_surface',
        undefined,
        expect.anything(),
      )
      expect(screen.getByText('Best forecast by valid time')).toBeTruthy()
    })
  })

  it('selects wildfire observations from the variable dropdown without a permanent widget', async () => {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    })
    render(
      <QueryClientProvider client={queryClient}>
        <App />
      </QueryClientProvider>,
    )

    const variableSelect = await screen.findByLabelText('Variable')
    await waitFor(() => {
      expect((variableSelect as HTMLSelectElement).value).toBe(
        'air_temperature_2m',
      )
    })
    expect(
      Array.from(variableSelect.querySelectorAll('optgroup')).map((group) =>
        group.getAttribute('label'),
      ),
    ).toEqual(['Temperature & humidity', 'Wildfire observations'])

    expect(screen.queryByText('WILDFIRE OBSERVATIONS')).toBeNull()
    fireEvent.change(variableSelect, { target: { value: 'wildfire_hotspots' } })

    await waitFor(() => {
      expect(apiMocks.getHotspots).toHaveBeenCalled()
      expect(apiMocks.getHotspots).toHaveBeenCalledWith(
        '2026-07-20',
        expect.anything(),
      )
      expect(screen.getByText('2026-07-20 23:38:00')).toBeTruthy()
      expect(
        screen.getByText('2 detections · 375 m nominal resolution'),
      ).toBeTruthy()
    })
    expect(screen.queryByLabelText('Data product')).toBeNull()
    expect(screen.queryByLabelText('Domain')).toBeNull()
    expect(screen.queryByLabelText('Start (UTC)')).toBeNull()
    const hotspotDate = screen.getByLabelText('Observation date')
    expect((hotspotDate as HTMLInputElement).value).toBe('2026-07-20')
    fireEvent.click(
      screen.getByRole('button', {
        name: 'Previous available hotspot date',
      }),
    )
    await waitFor(() => {
      expect((hotspotDate as HTMLInputElement).value).toBe('2026-07-19')
      expect(apiMocks.getHotspots).toHaveBeenCalledWith(
        '2026-07-19',
        expect.anything(),
      )
    })
    expect(screen.queryByText('WILDFIRE OBSERVATIONS')).toBeNull()
  })

  it('switches to the contour-free official seven-day forecast view', async () => {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    })
    render(
      <QueryClientProvider client={queryClient}>
        <App />
      </QueryClientProvider>,
    )

    fireEvent.click(
      await screen.findByRole('button', { name: '7-day forecast' }),
    )

    await waitFor(() => {
      expect(apiMocks.cityForecasts).toHaveBeenCalledWith(
        undefined,
        'NS',
        expect.anything(),
      )
      expect(screen.getByText('OFFICIAL 7-DAY FORECAST')).toBeTruthy()
      expect(screen.getByText('Probability of precipitation · %')).toBeTruthy()
      expect(screen.getByText('Issued amount · mm or cm')).toBeTruthy()
    })
    expect(screen.queryByLabelText('Variable')).toBeNull()
    expect(screen.queryByText('Add overlay')).toBeNull()
    expect(
      screen.getByRole('slider', { name: 'Seven-day forecast period' }),
    ).toBeTruthy()

    await waitFor(() => expect(mapMocks.create).toHaveBeenCalledOnce())
    await act(async () => {
      for (const [event, callback] of mapMocks.on.mock.calls) {
        if (event === 'load') callback()
      }
    })
    expect(mapMocks.create).toHaveBeenCalledWith(
      expect.objectContaining({ maxZoom: 14 }),
    )
    expect(mapMocks.fitBounds).toHaveBeenCalledWith(
      [
        [-66.7, 43.2],
        [-59.5, 47.2],
      ],
      expect.objectContaining({ maxZoom: 6 }),
    )
    // The whole-province fit is just the initial camera, not an interaction cap.
    expect(mapMocks.setMaxZoom).not.toHaveBeenCalled()
    expect(screen.getByText(/Zoom in to focus on a few locations/)).toBeTruthy()
  })
})
