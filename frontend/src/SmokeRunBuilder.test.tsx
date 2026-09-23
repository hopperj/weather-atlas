// @vitest-environment jsdom

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { SmokeRunBuilder } from './SmokeRunBuilder'

const smokeMocks = vi.hoisted(() => ({
  capabilities: vi.fn(),
  listEvents: vi.fn(),
  createScenarioAndRun: vi.fn(),
}))

vi.mock('./smokeApi', () => ({ smokeApi: smokeMocks }))

function renderBuilder(writesEnabled: boolean, eventCount = 1) {
  smokeMocks.capabilities.mockResolvedValue({
    writesEnabled,
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
  })
  smokeMocks.listEvents.mockResolvedValue({
    schemaVersion: 1,
    algorithmVersion: 'v1',
    items: Array.from({ length: eventCount }, (_, index) => ({
      event_id: `event-${index}`,
      first_observed_at: '2026-07-21T18:00:00Z',
      last_observed_at: '2026-07-22T05:00:00Z',
      latitude: 45,
      longitude: -63,
      fuel_types: ['C2'],
      model_eligible: true,
      maximum_estimated_area_ha: 10,
      fire_weather: { ffmc: 91, dmc: 44, dc: 310 },
      warnings: [],
    })),
  })
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={client}>
      <SmokeRunBuilder
        open
        initialBbox={[-66, 43, -60, 48]}
        onClose={vi.fn()}
        onSubmitted={vi.fn()}
      />
    </QueryClientProvider>,
  )
}

async function advanceToReview() {
  const submitCurrentStep = () => {
    const form = screen
      .getByRole('button', { name: 'Continue' })
      .closest('form')
    if (!form) throw new Error('smoke builder form is missing')
    fireEvent.submit(form)
  }
  await screen.findByText(/Latest complete GFS cycle:/)
  submitCurrentStep()
  await screen.findByText(/reconciled fire events/)
  submitCurrentStep()
  await screen.findByText('Transported species')
  submitCurrentStep()
  await screen.findByText(/Research estimate of primary wildfire emissions/)
}

describe('SmokeRunBuilder', () => {
  afterEach(() => {
    cleanup()
    vi.clearAllMocks()
  })

  it('uses the complete GFS window and keeps submission gated during validation', async () => {
    renderBuilder(false)
    await advanceToReview()

    expect(screen.getByText('24 hours')).toBeTruthy()
    expect(screen.getByText(/SIMULATION_WRITES_ENABLED/)).toBeTruthy()
    expect(
      (screen.getByRole('button', { name: 'Submit run' }) as HTMLButtonElement)
        .disabled,
    ).toBe(true)
  })

  it('explains the required CFFDRS codes and their units', async () => {
    renderBuilder(false)
    await screen.findByText(/2026-07-22T06:00:00Z/)
    const form = screen.getByRole('button', { name: 'Continue' }).closest('form')
    if (!form) throw new Error('smoke builder form is missing')
    fireEvent.submit(form)
    fireEvent.click(
      await screen.findByRole('radio', {
        name: 'Manual override for all fires',
      }),
    )

    expect(screen.getByText('Fine Fuel Moisture Code')).toBeTruthy()
    expect(screen.getByText('Duff Moisture Code')).toBeTruthy()
    expect(screen.getByText('Drought Code')).toBeTruthy()
    expect(screen.getAllByText('unitless code')).toHaveLength(3)
    expect(
      screen.getByText(/applied to every selected fire/i),
    ).toBeTruthy()
    expect(
      screen.getByText(/defaults \(92 \/ 45 \/ 320\) are only a research example/i),
    ).toBeTruthy()
  })

  it('submits the frozen event IDs and bounded scientific settings', async () => {
    smokeMocks.createScenarioAndRun.mockResolvedValue({
      runId: '220d9bad-781a-4883-addc-0bc63c496f68',
      status: 'queued',
      statusUrl: '/api/v1/smoke/runs/220d9bad-781a-4883-addc-0bc63c496f68',
      reused: false,
      estimate: { maximumRuntimeSeconds: 10800, maximumOutputBytes: 1024 },
    })
    renderBuilder(true, 2)
    await advanceToReview()
    fireEvent.click(screen.getByRole('button', { name: 'Submit run' }))

    await waitFor(() =>
      expect(smokeMocks.createScenarioAndRun).toHaveBeenCalledOnce(),
    )
    const config = smokeMocks.createScenarioAndRun.mock.calls[0]?.[1]
    expect(config).toMatchObject({
      event_ids: ['event-0', 'event-1'],
      species: ['PM25', 'CO', 'BC'],
      area_mode: 'cffeps_native_growth',
      fire_weather_mode: 'automatic_cwfis',
      fire_weather: null,
      particle_budget: 260_000,
    })
  })
})
