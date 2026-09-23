// @vitest-environment jsdom
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ForecastPage } from './ForecastPage'
import {
  type ForecastRegion,
  type HourlyForecast,
  type PrecipitationForecast,
  hourlySchema,
  precipitationSchema,
  regionsSchema,
} from './forecastApi'
import { forecastDate, forecastDays } from './forecastTime'

const mocks = vi.hoisted(() => ({
  regions: vi.fn(),
  hourly: vi.fn(),
  precipitation: vi.fn(),
}))
vi.mock('./forecastApi', async (importOriginal) => ({
  ...(await importOriginal<typeof import('./forecastApi')>()),
  forecastApi: mocks,
}))

const region: ForecastRegion = {
  id: '0123456789abcdef',
  name: 'Halifax Metro',
  province: 'NS',
  provinceName: 'Nova Scotia',
  latitude: 44.65,
  longitude: -63.57,
  issuedAt: '2026-09-06T12:00:00Z',
  stale: false,
  periods: [
    {
      name: 'Sunday',
      start: '2026-09-06T12:00:00Z',
      end: '2026-09-06T21:00:00Z',
      temperatureC: 22,
      temperatureClass: 'high',
      relativeHumidityPercent: 60,
      popPercent: 0,
      precipitationAmount: '0 mm',
      condition: 'Sunny',
    },
    {
      name: 'Sunday night',
      start: '2026-09-06T21:00:00Z',
      end: '2026-09-07T09:00:00Z',
      temperatureC: 12,
      temperatureClass: 'low',
      relativeHumidityPercent: null,
      popPercent: null,
      precipitationAmount: null,
      condition: 'Clear',
    },
  ],
}
const other: ForecastRegion = {
  ...region,
  id: 'fedcba9876543210',
  name: 'Yarmouth County',
}
const toronto: ForecastRegion = {
  ...region,
  id: '1111111111111111',
  name: 'Toronto',
  province: 'ON',
  provinceName: 'Ontario',
  latitude: 43.65,
  longitude: -79.38,
  periods: [{ ...region.periods[0], condition: 'Rain in Toronto' }],
}
const vancouver: ForecastRegion = {
  ...region,
  id: '2222222222222222',
  name: 'Metro Vancouver',
  province: 'BC',
  provinceName: 'British Columbia',
  latitude: 49.28,
  longitude: -123.12,
}
const iqaluit: ForecastRegion = {
  ...region,
  id: '3333333333333333',
  name: 'Iqaluit',
  province: 'NU',
  provinceName: 'Nunavut',
  latitude: 63.75,
  longitude: -68.52,
}
const hourly: HourlyForecast = {
  regionId: region.id,
  source: 'ECCC GDPS',
  generatedAt: '2026-09-06T12:00:00Z',
  start: '2026-09-06T12:00:00Z',
  end: '2026-09-09T12:00:00Z',
  availableHours: 71,
  completeHours: 71,
  hours: Array.from({ length: 72 }, (_, index) => ({
    time: new Date(Date.UTC(2026, 8, 6, 12 + index)).toISOString(),
    runTime: index === 1 ? null : '2026-09-06T12:00:00Z',
    precipitationStart: new Date(
      Date.UTC(2026, 8, 6, 11 + index),
    ).toISOString(),
    status: index === 1 ? 'missing' : 'complete',
    temperatureC: index === 1 ? null : 19,
    relativeHumidityPercent: index === 1 ? null : 65,
    precipitationMm: index === 1 ? null : 0,
    windKmh: index === 1 ? null : 36,
    gustKmh: index === 1 ? null : 54,
  })),
}

function mount() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  })
  render(
    <QueryClientProvider client={client}>
      <ForecastPage />
    </QueryClientProvider>,
  )
  return client
}

function precipitationFor(
  place: ForecastRegion,
  amount: number | null,
): PrecipitationForecast {
  return {
    regionId: place.id,
    issuedAt: place.issuedAt,
    generatedAt: place.issuedAt,
    source: 'ECCC GDPS',
    periods: place.periods.map((period) => ({
      start: period.start,
      end: period.end,
      status: amount === null ? 'missing' : 'complete',
      precipitationMm: amount,
      runTime: amount === null ? null : '2026-09-06T00:00:00Z',
    })),
  }
}

beforeEach(() => {
  window.history.replaceState(null, '', '/forecast')
  mocks.regions.mockResolvedValue({
    generatedAt: region.issuedAt,
    timeZone: 'America/Halifax',
    regions: [region, other, toronto, vancouver, iqaluit],
  })
  mocks.hourly.mockResolvedValue(hourly)
  mocks.precipitation.mockImplementation(async (id: string) =>
    precipitationFor(
      [region, other, toronto, vancouver, iqaluit].find(
        (place) => place.id === id,
      )!,
      null,
    ),
  )
})
afterEach(() => {
  cleanup()
  vi.resetAllMocks()
})

describe('forecast page', () => {
  it('uses the selected icon without changing the named link back to the map', async () => {
    const client = mount()
    const brand = screen.getByRole('link', { name: 'Weather Model Atlas' })
    expect(brand.getAttribute('href')).toBe('/?buffer=12')
    expect(brand.querySelector('img')?.getAttribute('src')).toBe(
      '/icons/crimson-sky-v1-96.png',
    )
    await screen.findByText('Your local forecast')
    client.clear()
  })

  it('fills only missing bulletin amounts with a starred model estimate and explanation', async () => {
    mocks.precipitation.mockResolvedValue(precipitationFor(region, 6.24))
    mount()
    const value = await screen.findByText('6.2 mm*')
    expect(screen.getAllByText('6.2 mm*')).toHaveLength(1)
    expect(screen.getByText('0 mm')).toBeTruthy()
    expect(value.getAttribute('title')).toContain('2026-09-06T00:00:00Z')
    expect(value.getAttribute('aria-describedby')).toBe(
      'model-precipitation-note',
    )
    expect(
      screen.getByText(/Model estimate \(ECCC GDPS\), used only/),
    ).toBeTruthy()
  })

  it.each([
    [0, '0.0 mm*'],
    [0.03, '<0.1 mm*'],
  ])('marks model zero and trace totals (%s)', async (amount, display) => {
    mocks.precipitation.mockResolvedValue(
      precipitationFor(region, Number(amount)),
    )
    mount()
    expect(await screen.findByText(String(display))).toBeTruthy()
  })

  it('preserves official ranges and snow amounts without making a model request', async () => {
    const supplied = {
      ...region,
      periods: region.periods.map((period, i) => ({
        ...period,
        precipitationAmount: i ? '2 cm' : '5 to 10 mm',
      })),
    }
    mocks.regions.mockResolvedValue({ regions: [supplied] })
    mount()
    expect(await screen.findByText('5 to 10 mm')).toBeTruthy()
    expect(screen.getByText('2 cm')).toBeTruthy()
    expect(mocks.precipitation).not.toHaveBeenCalled()
  })

  it.each(['region', 'issue', 'interval', 'incomplete'])(
    'rejects mismatched or incomplete model totals (%s)',
    async (mismatch) => {
      const estimate = precipitationFor(region, 6.24)
      if (mismatch === 'region') estimate.regionId = other.id
      if (mismatch === 'issue') estimate.issuedAt = '2026-09-06T00:00:00Z'
      if (mismatch === 'interval')
        estimate.periods[1].end = '2026-09-07T06:00:00Z'
      if (mismatch === 'incomplete') estimate.periods[1].status = 'missing'
      mocks.precipitation.mockResolvedValue(estimate)
      mount()
      await screen.findByRole('table')
      await waitFor(() =>
        expect(
          screen.queryByText('Estimating missing precipitation amounts…'),
        ).toBeNull(),
      )
      expect(screen.queryByText('6.2 mm*')).toBeNull()
      expect(screen.getByText('0 mm')).toBeTruthy()
    },
  )

  it('clears model amounts on region changes while retaining the bulletin', async () => {
    mocks.precipitation.mockImplementation((id: string) =>
      id === region.id
        ? Promise.resolve(precipitationFor(region, 6.24))
        : new Promise(() => {}),
    )
    mount()
    await screen.findByText('6.2 mm*')
    fireEvent.change(screen.getByLabelText('Forecast region'), {
      target: { value: other.id },
    })
    await screen.findByText('Estimating missing precipitation amounts…')
    expect(screen.queryByText('6.2 mm*')).toBeNull()
    expect(screen.getByText('0 mm')).toBeTruthy()
    expect(mocks.precipitation).toHaveBeenLastCalledWith(
      other.id,
      expect.anything(),
    )
  })

  it('keeps ECCC forecasts usable if model precipitation fails', async () => {
    mocks.precipitation.mockRejectedValue(new Error('Unavailable'))
    mount()
    expect(
      await screen.findByText(
        /Model precipitation estimates could not be refreshed/,
      ),
    ).toBeTruthy()
    expect(screen.getByText('Sunny')).toBeTruthy()
    expect(screen.getByText('0 mm')).toBeTruthy()
  })

  it('shows both outlooks, zero amounts, and every hour including gaps', async () => {
    mount()
    expect(await screen.findByText('Sunny')).toBeTruthy()
    expect(screen.getByText('Clear')).toBeTruthy()
    expect(screen.getByRole('heading', { name: '7-day forecast' })).toBeTruthy()
    expect(
      screen.getByRole('heading', { name: '72-hour forecast' }),
    ).toBeTruthy()
    expect(screen.getByText('0 mm')).toBeTruthy()
    const table = await screen.findByRole('table')
    expect(within(table).getAllByRole('row')).toHaveLength(73)
    expect(within(table).getByText('Not available')).toBeTruthy()
    expect(within(table).getByText('2026-09-06 10:00')).toBeTruthy()
    expect(screen.getByText(/71 \/ 72 hours available/)).toBeTruthy()
    expect(mocks.hourly).toHaveBeenCalledWith(region.id, expect.anything())
  })

  it('selects a region from the URL and clears the old hourly data on change', async () => {
    window.history.replaceState(null, '', `/forecast?region=${other.id}`)
    mount()
    await screen.findByRole('table')
    expect(
      (screen.getByLabelText('Forecast region') as HTMLSelectElement).value,
    ).toBe(other.id)
    expect(mocks.hourly).toHaveBeenCalledWith(other.id, expect.anything())
    mocks.hourly.mockImplementation(() => new Promise(() => {}))
    fireEvent.change(screen.getByLabelText('Forecast region'), {
      target: { value: region.id },
    })
    await waitFor(() => expect(screen.queryByRole('table')).toBeNull())
    expect(window.location.search).toContain(region.id)
    expect(screen.getByText('Loading hourly forecasts…')).toBeTruthy()
  })

  it('keeps the daily view usable if hourly retrieval fails', async () => {
    mocks.hourly.mockRejectedValue(new Error('Catalogue database is not ready'))
    mount()
    expect(await screen.findByRole('alert')).toBeTruthy()
    expect(screen.getByText('Sunny')).toBeTruthy()
    expect(screen.queryByRole('table')).toBeNull()
  })

  it('identifies expired bulletins instead of presenting old values as current', async () => {
    mocks.regions.mockResolvedValue({
      generatedAt: region.issuedAt,
      timeZone: 'America/Halifax',
      regions: [{ ...region, stale: true, periods: [] }],
    })
    mount()
    expect(
      await screen.findByText(/last collected bulletin has expired/),
    ).toBeTruthy()
    expect(screen.queryByText('Sunny')).toBeNull()
  })

  it('keeps only NS regions at the first level with Other for the rest of Canada', async () => {
    mount()
    await screen.findByText('Sunny')
    const primary = screen.getByLabelText('Forecast region')
    expect(
      within(primary)
        .getAllByRole('option')
        .map((option) => option.textContent),
    ).toEqual([
      'Halifax Metro',
      'Yarmouth County',
      'Other province or territory…',
    ])
    expect(screen.queryByLabelText('Province or territory')).toBeNull()
    expect(screen.queryByLabelText('Region')).toBeNull()
  })

  it('filters other regions by province and updates both outlooks only after selection', async () => {
    mount()
    await screen.findByRole('table')
    const calls = mocks.hourly.mock.calls.length
    fireEvent.change(screen.getByLabelText('Forecast region'), {
      target: { value: 'other' },
    })
    expect(screen.queryByRole('table')).toBeNull()
    expect(screen.queryByText('Sunny')).toBeNull()
    expect(
      (screen.getByLabelText('Region') as HTMLSelectElement).disabled,
    ).toBe(true)
    expect(
      within(screen.getByLabelText('Province or territory'))
        .getAllByRole('option')
        .map((option) => option.textContent),
    ).toEqual([
      'Select a province or territory…',
      'British Columbia',
      'Nunavut',
      'Ontario',
    ])
    fireEvent.change(screen.getByLabelText('Province or territory'), {
      target: { value: 'ON' },
    })
    expect(
      within(screen.getByLabelText('Region'))
        .getAllByRole('option')
        .map((option) => option.textContent),
    ).toEqual(['Select a region…', 'Toronto'])
    expect(mocks.hourly).toHaveBeenCalledTimes(calls)
    expect(window.location.search).toBe('?scope=other&province=ON')
    fireEvent.change(screen.getByLabelText('Region'), {
      target: { value: toronto.id },
    })
    expect(await screen.findByText('Rain in Toronto')).toBeTruthy()
    await screen.findByRole('table')
    expect(mocks.hourly).toHaveBeenLastCalledWith(toronto.id, expect.anything())
    expect(window.location.search).toBe(`?region=${toronto.id}`)
    expect(screen.getByText('Viewing Toronto, Ontario')).toBeTruthy()
    fireEvent.change(screen.getByLabelText('Province or territory'), {
      target: { value: 'BC' },
    })
    expect(screen.queryByText('Rain in Toronto')).toBeNull()
    expect(screen.queryByRole('table')).toBeNull()
    expect((screen.getByLabelText('Region') as HTMLSelectElement).value).toBe(
      '',
    )
    expect(
      within(screen.getByLabelText('Region')).queryByRole('option', {
        name: 'Toronto',
      }),
    ).toBeNull()
    expect(
      within(screen.getByLabelText('Region')).getByRole('option', {
        name: 'Metro Vancouver',
      }),
    ).toBeTruthy()
    fireEvent.change(screen.getByLabelText('Forecast region'), {
      target: { value: other.id },
    })
    expect(screen.queryByLabelText('Province or territory')).toBeNull()
    await screen.findByRole('table')
    expect(mocks.hourly).toHaveBeenLastCalledWith(other.id, expect.anything())
    expect(
      screen.getByText('Viewing Yarmouth County, Nova Scotia'),
    ).toBeTruthy()
  })

  it('restores an outside-NS deep link and its province without loading Halifax', async () => {
    window.history.replaceState(null, '', `/forecast?region=${iqaluit.id}`)
    mount()
    await screen.findByRole('table')
    expect(
      (screen.getByLabelText('Forecast region') as HTMLSelectElement).value,
    ).toBe('other')
    expect(
      (screen.getByLabelText('Province or territory') as HTMLSelectElement)
        .value,
    ).toBe('NU')
    expect((screen.getByLabelText('Region') as HTMLSelectElement).value).toBe(
      iqaluit.id,
    )
    expect(mocks.hourly).toHaveBeenCalledWith(iqaluit.id, expect.anything())
    expect(mocks.hourly).not.toHaveBeenCalledWith(region.id, expect.anything())
    expect(
      screen.getByText(/Times for all regions are shown in Atlantic time/),
    ).toBeTruthy()
  })

  it('restores an unfinished province selection without fetching an unrelated forecast', async () => {
    window.history.replaceState(null, '', '/forecast?scope=other&province=BC')
    mount()
    await screen.findByRole('option', { name: 'Metro Vancouver' })
    expect(
      (screen.getByLabelText('Province or territory') as HTMLSelectElement)
        .value,
    ).toBe('BC')
    expect((screen.getByLabelText('Region') as HTMLSelectElement).value).toBe(
      '',
    )
    expect(mocks.hourly).not.toHaveBeenCalled()
  })

  it('keeps other regions accessible when no NS bulletin is in the catalogue', async () => {
    mocks.regions.mockResolvedValue({
      generatedAt: region.issuedAt,
      timeZone: 'America/Halifax',
      regions: [toronto],
    })
    mount()
    await screen.findByRole('option', { name: 'Other province or territory…' })
    expect(
      (screen.getByLabelText('Forecast region') as HTMLSelectElement).disabled,
    ).toBe(false)
    fireEvent.change(screen.getByLabelText('Forecast region'), {
      target: { value: 'other' },
    })
    expect(screen.getByRole('option', { name: 'Ontario' })).toBeTruthy()
  })
})

describe('forecast time and data contracts', () => {
  it('rejects negative model precipitation values', () => {
    expect(
      precipitationSchema.parse(precipitationFor(region, 0)).periods[1]
        .precipitationMm,
    ).toBe(0)
    expect(() =>
      precipitationSchema.parse(precipitationFor(region, -1)),
    ).toThrow()
  })
  it('requires province metadata for hierarchical region selection', () => {
    const result = regionsSchema.parse({
      generatedAt: region.issuedAt,
      timeZone: 'America/Halifax',
      regions: [region, toronto, iqaluit],
    })
    expect(result.regions.map((item) => item.province)).toEqual([
      'NS',
      'ON',
      'NU',
    ])
    expect(() =>
      regionsSchema.parse({
        ...result,
        regions: [{ ...region, province: 'XX' }],
      }),
    ).toThrow()
  })
  it('uses Atlantic dates and groups day and night without losing night values', () => {
    expect(forecastDate('2026-09-07T01:00:00Z')).toBe('2026-09-06')
    expect(forecastDays(region)).toHaveLength(1)
    expect(forecastDays(region)[0][1]).toHaveLength(2)
    // Standard time uses UTC-4; summer uses UTC-3.
    expect(forecastDate('2026-12-01T03:30:00Z')).toBe('2026-11-30')
    expect(forecastDate('2026-06-01T03:30:00Z')).toBe('2026-06-01')
  })

  it('rejects a shortened hourly series so missing slots cannot disappear', () => {
    expect(hourlySchema.parse(hourly).hours).toHaveLength(72)
    expect(() =>
      hourlySchema.parse({ ...hourly, hours: hourly.hours.slice(1) }),
    ).toThrow()
  })
})
