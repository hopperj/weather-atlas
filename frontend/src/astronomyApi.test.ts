// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  astronomyForecast,
  astronomySchema,
  initialObservingSite,
  observingSiteSchema,
  restoreSites,
} from './astronomyApi'
import { astronomyFixture } from './astronomyFixtures'

afterEach(() => {
  vi.unstubAllGlobals()
  localStorage.clear()
  window.history.replaceState(null, '', '/')
})
describe('astronomy contract', () => {
  it('preserves missing values, not synthetic zeroes', () => {
    const value = astronomySchema.parse(astronomyFixture)
    expect(value.frames[0].humidityPercent).toBeNull()
    expect(value.frames[0].rainMm).toBe(0)
    expect(value.nights[0].events.moonrise).toBeNull()
  })
  it('seeds an exact arbitrary point and restores an independent observing site', () => {
    window.history.replaceState(
      null,
      '',
      '/astronomy?latitude=45.123456&longitude=-65.987654&name=Telescope',
    )
    expect(initialObservingSite()).toEqual({
      latitude: 45.123456,
      longitude: -65.987654,
      name: 'Telescope',
    })
    localStorage.setItem(
      'weather-atlas.astronomy.site',
      JSON.stringify([{ latitude: 50, longitude: -100, name: 'Saved site' }]),
    )
    expect(initialObservingSite().name).toBe('Saved site')
    expect(
      observingSiteSchema.safeParse({
        latitude: NaN,
        longitude: 0,
        name: 'bad',
      }).success,
    ).toBe(false)
    localStorage.setItem('broken', '{}')
    expect(restoreSites('broken')).toEqual([])
  })
  it('requests the same server without an area ID and rejects another point', async () => {
    const fetcher = vi
      .fn()
      .mockResolvedValue({ ok: true, json: async () => astronomyFixture })
    vi.stubGlobal('fetch', fetcher)
    const site = { latitude: 44.65, longitude: -63.57, name: 'Site' }
    const options = {
      product: 'gdps',
      mode: 'deep_sky' as const,
      maxCloud: 30,
      maxWind: 25,
    }
    await astronomyForecast(site, options)
    const url = fetcher.mock.calls[0][0] as string
    expect(url).toContain('/api/v1/astronomy/forecast?')
    expect(url).not.toContain('area_id')
    await expect(
      astronomyForecast({ ...site, latitude: 45 }, options),
    ).rejects.toThrow('different site')
  })
})
