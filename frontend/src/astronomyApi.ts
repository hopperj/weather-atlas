import { z } from 'zod'

export const observingSiteSchema = z.object({
  latitude: z.number().min(-90).max(90),
  longitude: z.number().min(-180).max(180),
  name: z.string().max(120),
})
export type ObservingSite = z.infer<typeof observingSiteSchema>
const number = z.number().finite().nullable()
const interval = z.object({
  start: z.iso.datetime(),
  end: z.iso.datetime(),
  minutes: z.number(),
})
export const astronomySchema = z.object({
  schemaVersion: z.literal(1),
  generatedAt: z.iso.datetime(),
  preview: z.boolean(),
  latitude: z.number(),
  longitude: z.number(),
  timeZone: z.string(),
  product: z.string(),
  source: z.string(),
  runTime: z.iso.datetime().nullable(),
  stale: z.boolean(),
  mode: z.enum(['deep_sky', 'lunar_planetary']),
  ruleVersion: z.string(),
  method: z.string(),
  limitations: z.array(z.string()),
  unavailableFields: z.array(z.string()),
  sample: z
    .object({
      latitude: z.number(),
      longitude: z.number(),
      crs: z.string(),
      pixelSize: z.array(z.number()),
    })
    .nullable(),
  frames: z.array(
    z.object({
      time: z.iso.datetime(),
      cloudPercent: number,
      temperatureC: number,
      humidityPercent: number,
      windKmh: number,
      gustKmh: number,
      dewPointC: number,
      dewRisk: z.boolean().nullable(),
      rainMm: number,
      rainStart: z.iso.datetime().nullable(),
      sunAltitudeDegrees: z.number(),
      moonAltitudeDegrees: z.number(),
      moonIlluminatedPercent: z.number(),
      moonPhaseDegrees: z.number(),
      moonPhaseName: z.string().optional(),
    }),
  ),
  nights: z.array(
    z.object({
      date: z.string(),
      start: z.iso.datetime(),
      end: z.iso.datetime(),
      state: z.enum(['window', 'no_window', 'insufficient_data']),
      summary: z.string(),
      events: z.record(z.string(), z.iso.datetime().nullable()),
      darkness: z.array(interval),
      moonlessDarkness: z.array(interval),
      windows: z.array(interval),
      moonIlluminatedPercent: z.number(),
      moonPhaseDegrees: z.number(),
      moonPhaseName: z.string().optional(),
    }),
  ),
})
export type AstronomyForecast = z.infer<typeof astronomySchema>
export type AstronomyFrame = AstronomyForecast['frames'][number]
export type AstronomyOptions = {
  product: string
  mode: 'deep_sky' | 'lunar_planetary'
  maxCloud: number
  maxWind: number
}
export function initialAstronomyOptions(): AstronomyOptions {
  try {
    return z
      .object({
        product: z.enum(['gdps', 'rdps', 'hrdps']),
        mode: z.enum(['deep_sky', 'lunar_planetary']),
        maxCloud: z.number().int().min(0).max(100),
        maxWind: z.number().int().min(0).max(150),
      })
      .parse(
        JSON.parse(
          localStorage.getItem('weather-atlas.astronomy.options') ?? 'null',
        ),
      )
  } catch {
    return { product: 'gdps', mode: 'deep_sky', maxCloud: 30, maxWind: 25 }
  }
}
export async function astronomyForecast(
  site: ObservingSite,
  options: AstronomyOptions,
  signal?: AbortSignal,
) {
  const query = new URLSearchParams({
    latitude: String(site.latitude),
    longitude: String(site.longitude),
    product: options.product,
    mode: options.mode,
    max_cloud_percent: String(options.maxCloud),
    max_wind_kmh: String(options.maxWind),
  })
  const response = await fetch(`/api/v1/astronomy/forecast?${query}`, {
    signal,
    cache: 'no-store',
  })
  if (!response.ok)
    throw new Error(
      `Astronomy forecast unavailable (${response.status}). Try again.`,
    )
  const result = astronomySchema.parse(await response.json())
  if (
    Math.abs(result.latitude - site.latitude) > 1e-7 ||
    Math.abs(result.longitude - site.longitude) > 1e-7 ||
    result.product !== options.product ||
    result.mode !== options.mode
  ) {
    throw new Error(
      'The server returned a forecast for a different site or selection.',
    )
  }
  return result
}

export function restoreSites(key: string): ObservingSite[] {
  try {
    return z
      .array(observingSiteSchema)
      .max(30)
      .parse(JSON.parse(localStorage.getItem(key) ?? '[]'))
  } catch {
    return []
  }
}
export function initialObservingSite(): ObservingSite {
  const saved = restoreSites('weather-atlas.astronomy.site')[0]
  if (saved) return saved
  const query = new URLSearchParams(location.search)
  if (query.has('latitude') && query.has('longitude')) {
    const seed = observingSiteSchema.safeParse({
      latitude: Number(query.get('latitude')),
      longitude: Number(query.get('longitude')),
      name: query.get('name') ?? 'Forecast location',
    })
    if (seed.success) return seed.data
  }
  return { latitude: 44.65, longitude: -63.57, name: 'Halifax (default)' }
}
