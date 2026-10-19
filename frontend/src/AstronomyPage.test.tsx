// @vitest-environment jsdom
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { AstronomyPage } from './AstronomyPage'
import { astronomyFixture } from './astronomyFixtures'
import type {
  AstronomyForecast,
  AstronomyOptions,
  ObservingSite,
} from './astronomyApi'

const mocks = vi.hoisted(() => ({ forecast: vi.fn() }))
vi.mock('./astronomyApi', async (original) => ({
  ...(await original<typeof import('./astronomyApi')>()),
  astronomyForecast: mocks.forecast,
}))
vi.mock('maplibre-gl', () => {
  class Map {
    on() {
      return this
    }
    addControl() {}
    remove() {}
  }
  class Marker {
    setLngLat() {
      return this
    }
    addTo() {
      return this
    }
    on() {
      return this
    }
    remove() {}
  }
  return { default: { Map, Marker, NavigationControl: class {} } }
})
function open() {
  render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      <AstronomyPage />
    </QueryClientProvider>,
  )
}
beforeEach(() => {
  localStorage.clear()
  mocks.forecast.mockReset()
  mocks.forecast.mockImplementation(
    async (site: ObservingSite, options: AstronomyOptions) => ({
      ...astronomyFixture,
      latitude: site.latitude,
      longitude: site.longitude,
      product: options.product,
      mode: options.mode,
    }),
  )
})
afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})
it('shows a real window, Sun/Moon data, native rain intervals and honest missing cells', async () => {
  open()
  await screen.findByText(/120 minutes/)
  expect(screen.getByText('Total cloud')).toBeDefined()
  expect(
    screen.getByRole('button', { name: /Humidity at .*unavailable/ }),
  ).toBeDefined()
  fireEvent.click(screen.getByRole('button', { name: /Total cloud at/ }))
  expect(screen.getByText(/Precipitation interval:/)).toBeDefined()
  expect(
    screen.getByText(
      /Low\/middle\/high cloud, seeing and transparency: not available/,
    ),
  ).toBeDefined()
})
it('allows exact points without regional snapping and saves reusable sites', async () => {
  open()
  await screen.findByText(/120 minutes/)
  fireEvent.click(screen.getByRole('button', { name: 'Choose on map' }))
  fireEvent.change(screen.getByLabelText('Latitude'), {
    target: { value: '45.123456' },
  })
  fireEvent.change(screen.getByLabelText('Longitude'), {
    target: { value: '-65.987654' },
  })
  fireEvent.change(screen.getByLabelText('Site name'), {
    target: { value: 'Telescope' },
  })
  fireEvent.click(screen.getByRole('button', { name: 'Use this location' }))
  await screen.findByRole('heading', { name: 'Telescope' })
  fireEvent.click(screen.getByRole('button', { name: 'Save site' }))
  expect(
    JSON.parse(localStorage.getItem('weather-atlas.astronomy.saved')!)[0]
      .latitude,
  ).toBe(45.123456)
  await waitFor(() =>
    expect(mocks.forecast).toHaveBeenLastCalledWith(
      expect.objectContaining({ latitude: 45.123456, longitude: -65.987654 }),
      expect.anything(),
      expect.anything(),
    ),
  )
})
it('cancelling the map leaves the active site unchanged', async () => {
  open()
  await screen.findByText(/120 minutes/)
  fireEvent.click(screen.getByRole('button', { name: 'Choose on map' }))
  fireEvent.change(screen.getByLabelText('Latitude'), {
    target: { value: '50' },
  })
  fireEvent.keyDown(document, { key: 'Escape' })
  expect(screen.queryByRole('dialog')).toBeNull()
  expect(
    screen.getByRole('heading', { name: 'Halifax (default)' }),
  ).toBeDefined()
})
it('does not keep old observing windows under newly selected limits', async () => {
  open()
  await screen.findByText(/120 minutes/)
  mocks.forecast.mockReturnValue(new Promise<AstronomyForecast>(() => {}))
  fireEvent.change(screen.getByLabelText('Cloud limit 30%'), {
    target: { value: '10' },
  })
  await waitFor(() => expect(screen.queryByText(/120 minutes/)).toBeNull())
  expect(screen.getByText('Preparing your observing forecast…')).toBeDefined()
})
