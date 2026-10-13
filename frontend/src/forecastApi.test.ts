// @vitest-environment jsdom
import { afterEach, expect, it, vi } from 'vitest'
import { forecastApi } from './forecastApi'

afterEach(() => vi.unstubAllGlobals())

it('revalidates forecast refreshes with the server instead of reusing a fresh HTTP response', async () => {
  const fetchMock = vi.fn().mockResolvedValue({
    ok: true,
    json: async () => ({
      generatedAt: '2026-10-09T13:00:00Z',
      timeZone: 'America/Halifax',
      regions: [],
    }),
  })
  vi.stubGlobal('fetch', fetchMock)
  const signal = new AbortController().signal
  await forecastApi.regions(signal)
  expect(fetchMock).toHaveBeenCalledWith('/api/v1/forecast/regions', {
    signal,
    cache: 'no-cache',
  })
})
