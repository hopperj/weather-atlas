import { z } from 'zod'

const periodSchema = z.object({
  name: z.string(),
  start: z.iso.datetime(),
  end: z.iso.datetime(),
  temperatureC: z.number().nullable(),
  temperatureClass: z.string().nullable(),
  relativeHumidityPercent: z.number().nullable(),
  popPercent: z.number().nullable(),
  precipitationAmount: z.string().nullable(),
  condition: z.string(),
})
export const regionSchema = z.object({
  id: z.string(),
  name: z.string(),
  latitude: z.number(),
  province: z.enum([
    'AB',
    'BC',
    'MB',
    'NB',
    'NL',
    'NS',
    'NT',
    'NU',
    'ON',
    'PE',
    'QC',
    'SK',
    'YT',
  ]),
  provinceName: z.string(),
  longitude: z.number(),
  issuedAt: z.iso.datetime(),
  stale: z.boolean(),
  periods: z.array(periodSchema),
})
export const regionsSchema = z.object({
  generatedAt: z.iso.datetime(),
  timeZone: z.literal('America/Halifax'),
  regions: z.array(regionSchema),
})
export const hourlySchema = z.object({
  regionId: z.string(),
  source: z.literal('ECCC GDPS'),
  generatedAt: z.iso.datetime(),
  start: z.iso.datetime(),
  end: z.iso.datetime(),
  availableHours: z.number().int(),
  completeHours: z.number().int(),
  hours: z
    .array(
      z.object({
        time: z.iso.datetime(),
        runTime: z.iso.datetime().nullable(),
        precipitationStart: z.iso.datetime(),
        status: z.enum(['complete', 'partial', 'missing']),
        temperatureC: z.number().nullable(),
        relativeHumidityPercent: z.number().nullable(),
        precipitationMm: z.number().nullable(),
        windKmh: z.number().nullable(),
        gustKmh: z.number().nullable(),
      }),
    )
    .length(72),
})
export type ForecastRegion = z.infer<typeof regionSchema>
export type HourlyForecast = z.infer<typeof hourlySchema>

export const precipitationSchema = z.object({
  regionId: z.string(),
  issuedAt: z.iso.datetime(),
  source: z.literal('ECCC GDPS'),
  generatedAt: z.iso.datetime(),
  periods: z.array(
    z.object({
      start: z.iso.datetime(),
      end: z.iso.datetime(),
      status: z.enum(['official', 'complete', 'missing']),
      precipitationMm: z.number().nonnegative().nullable(),
      runTime: z.iso.datetime().nullable(),
    }),
  ),
})
export type PrecipitationForecast = z.infer<typeof precipitationSchema>

async function request<T>(
  url: string,
  schema: z.ZodType<T>,
  signal?: AbortSignal,
) {
  const response = await fetch(url, { signal })
  if (!response.ok) {
    let message = `Forecast service unavailable (${response.status})`
    try {
      const body = await response.json()
      if (typeof body.detail === 'string') message = body.detail
    } catch {
      /* Keep a readable message for proxy errors. */
    }
    throw new Error(message)
  }
  return schema.parse(await response.json())
}

export const forecastApi = {
  regions: (signal?: AbortSignal) =>
    request('/api/v1/forecast/regions', regionsSchema, signal),
  hourly: (id: string, signal?: AbortSignal) =>
    request(
      `/api/v1/forecast/hourly?area_id=${encodeURIComponent(id)}`,
      hourlySchema,
      signal,
    ),
  precipitation: (id: string, signal?: AbortSignal) =>
    request(
      `/api/v1/forecast/precipitation?area_id=${encodeURIComponent(id)}`,
      precipitationSchema,
      signal,
    ),
}
