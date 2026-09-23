import { afterEach, describe, expect, it, vi } from 'vitest'
import { smokeApi } from './smokeApi'

const capabilities = {
  writesEnabled: false,
  latestCompleteGfsCycle: '2026-07-22T06:00:00Z',
  availableStart: '2026-07-22T06:00:00Z',
  availableEnd: '2026-07-23T06:00:00Z',
  maximumHorizonHours: 24,
  species: ['PM25', 'CO', 'BC'],
  uncertaintyModes: ['low', 'central', 'high'],
  gridSpacingDegrees: [0.25, 0.5, 1],
  maximumParticles: 1_000_000,
  maximumReleaseGroupsPerEventHour: 36,
  minimumParticlesPerRelease: 50,
  primaryEmissionsOnly: true,
}

describe('smoke API client', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('validates capabilities and encodes a bounded event query', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(JSON.stringify(capabilities), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            schemaVersion: 1,
            algorithmVersion: 'v1',
            items: [],
          }),
          { status: 200, headers: { 'Content-Type': 'application/json' } },
        ),
      )
    vi.stubGlobal('fetch', fetchMock)

    await expect(smokeApi.capabilities()).resolves.toMatchObject({
      primaryEmissionsOnly: true,
      maximumHorizonHours: 24,
    })
    await smokeApi.listEvents(
      [-66, 43, -60, 48],
      '2026-07-21T06:00:00Z',
      '2026-07-23T06:00:00Z',
    )
    expect(fetchMock.mock.calls[1]?.[0]).toBe(
      '/api/v1/fire-events?bbox=-66%2C43%2C-60%2C48&start=2026-07-21T06%3A00%3A00Z&end=2026-07-23T06%3A00%3A00Z',
    )
  })

  it('rejects an invalid server payload before it reaches the UI', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({ ...capabilities, primaryEmissionsOnly: false }),
          {
            status: 200,
            headers: { 'Content-Type': 'application/json' },
          },
        ),
      ),
    )

    await expect(smokeApi.capabilities()).rejects.toThrow()
  })
})
