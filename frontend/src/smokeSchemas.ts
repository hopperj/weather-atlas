import { z } from 'zod'

const isoDateTime = z.string().datetime({ offset: true })

export const smokeCapabilitiesSchema = z.object({
  writesEnabled: z.boolean(),
  latestCompleteGfsCycle: isoDateTime.nullable(),
  availableStart: isoDateTime.nullable(),
  availableEnd: isoDateTime.nullable(),
  maximumHorizonHours: z.number().int().positive(),
  species: z.array(z.enum(['PM25', 'CO', 'BC'])),
  uncertaintyModes: z.array(z.enum(['low', 'central', 'high'])),
  gridSpacingDegrees: z.array(z.number().positive()),
  maximumParticles: z.number().int().positive(),
  maximumReleaseGroupsPerEventHour: z.number().int().positive(),
  minimumParticlesPerRelease: z.number().int().positive(),
  primaryEmissionsOnly: z.literal(true),
})

export const fireEventSchema = z
  .object({
    event_id: z.string(),
    first_observed_at: isoDateTime,
    last_observed_at: isoDateTime,
    latitude: z.number(),
    longitude: z.number(),
    fuel_types: z.array(z.string()),
    maximum_estimated_area_ha: z.number().nonnegative(),
    model_eligible: z.boolean().default(false),
    warnings: z.array(z.string()),
  })
  .passthrough()

export const fireEventCollectionSchema = z.object({
  schemaVersion: z.number().int().nullable(),
  algorithmVersion: z.string().nullable(),
  items: z.array(fireEventSchema),
})

export const scenarioSummarySchema = z.object({
  id: z.string().uuid(),
  name: z.string(),
  description: z.string(),
  ownerLabel: z.string(),
  createdAt: isoDateTime,
  updatedAt: isoDateTime,
  archivedAt: isoDateTime.nullable().optional(),
  revisionCount: z.number().int().nullable().optional(),
})

export const revisionSummarySchema = z.object({
  id: z.string().uuid(),
  scenarioId: z.string().uuid(),
  revisionNumber: z.number().int().positive(),
  canonicalConfig: z.record(z.string(), z.unknown()),
  configSha256: z.string(),
  createdAt: isoDateTime,
})

export const scenarioCreateResponseSchema = z.object({
  scenario: scenarioSummarySchema,
  revision: revisionSummarySchema,
})

export const smokeRunSchema = z.object({
  id: z.string().uuid(),
  scenarioRevisionId: z.string().uuid(),
  scenarioId: z.string().uuid().nullable().optional(),
  runKind: z.string(),
  status: z.string(),
  requestedAt: isoDateTime,
  queuedAt: isoDateTime,
  startedAt: isoDateTime.nullable().optional(),
  completedAt: isoDateTime.nullable().optional(),
  requestedBy: z.string().nullable().optional(),
  gfsCycleTime: isoDateTime.nullable().optional(),
  metrics: z.record(z.string(), z.unknown()).default({}),
  warnings: z.array(z.unknown()).default([]),
  errorClass: z.string().nullable().optional(),
  errorMessage: z.string().nullable().optional(),
  cancellationRequestedAt: isoDateTime.nullable().optional(),
})

export const runSubmissionSchema = z.object({
  runId: z.string().uuid(),
  status: z.string(),
  statusUrl: z.string(),
  reused: z.boolean(),
  estimate: z.object({
    maximumRuntimeSeconds: z.number().int().positive(),
    maximumOutputBytes: z.number().int().positive(),
  }),
})

export type SmokeCapabilities = z.infer<typeof smokeCapabilitiesSchema>
export type SmokeRun = z.infer<typeof smokeRunSchema>
export type RunSubmission = z.infer<typeof runSubmissionSchema>

export type SmokeScenarioConfigInput = {
  name: string
  start_time: string
  end_time: string
  bbox: [number, number, number, number]
  event_ids: string[]
  area_mode: 'cffeps_native_growth'
  area_curve: []
  fire_weather_mode: 'automatic_cwfis' | 'manual'
  fire_weather: { ffmc: number; dmc: number; dc: number } | null
  species: ('PM25' | 'CO' | 'BC')[]
  uncertainty: 'low' | 'central' | 'high'
  grid_spacing_degrees: 0.25 | 0.5 | 1
  particle_budget: number
  random_seed: number
}
