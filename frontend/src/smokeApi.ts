import { z } from 'zod'
import { ApiError } from './api'
import {
  fireEventCollectionSchema,
  runSubmissionSchema,
  scenarioCreateResponseSchema,
  smokeCapabilitiesSchema,
  smokeRunSchema,
  type SmokeScenarioConfigInput,
} from './smokeSchemas'

async function jsonRequest<T>(
  path: string,
  schema: z.ZodType<T>,
  options: RequestInit = {},
): Promise<T> {
  const response = await fetch(path, {
    ...options,
    headers: {
      Accept: 'application/json',
      ...(options.body ? { 'Content-Type': 'application/json' } : {}),
      ...options.headers,
    },
  })
  if (!response.ok) {
    let message = `Request failed (${response.status})`
    try {
      const body = (await response.json()) as { detail?: string }
      message = body.detail ?? message
    } catch {
      // Keep the stable fallback for proxy-generated error pages.
    }
    throw new ApiError(message, response.status)
  }
  return schema.parse(await response.json())
}

export const smokeApi = {
  capabilities: (signal?: AbortSignal) =>
    jsonRequest('/api/v1/smoke/capabilities', smokeCapabilitiesSchema, {
      signal,
    }),

  listEvents: (
    bbox: [number, number, number, number],
    start: string,
    end: string,
    signal?: AbortSignal,
  ) => {
    const query = new URLSearchParams({
      bbox: bbox.join(','),
      start,
      end,
    })
    return jsonRequest(
      `/api/v1/fire-events?${query}`,
      fireEventCollectionSchema,
      { signal },
    )
  },

  createScenarioAndRun: async (
    name: string,
    config: SmokeScenarioConfigInput,
  ) => {
    const created = await jsonRequest(
      '/api/v1/smoke/scenarios',
      scenarioCreateResponseSchema,
      {
        method: 'POST',
        body: JSON.stringify({
          name,
          description: 'Created from the map smoke-run builder.',
          config,
        }),
      },
    )
    return jsonRequest(
      `/api/v1/smoke/scenarios/${created.scenario.id}/runs`,
      runSubmissionSchema,
      {
        method: 'POST',
        body: JSON.stringify({
          revisionId: created.revision.id,
          runKind: 'interactive',
        }),
      },
    )
  },

  getRun: (runId: string, signal?: AbortSignal) =>
    jsonRequest(`/api/v1/smoke/runs/${runId}`, smokeRunSchema, { signal }),

  cancelRun: (runId: string) =>
    jsonRequest(`/api/v1/smoke/runs/${runId}/cancel`, smokeRunSchema, {
      method: 'POST',
    }),
}
