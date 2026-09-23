import { z } from 'zod'

const isoDateTime = z.string().datetime({ offset: true })

export const productSchema = z.object({
  code: z.string(),
  name: z.string(),
  description: z.string().nullable().default(null),
  kind: z.enum(['forecast', 'analysis', 'ensemble_analysis']),
  priority: z.number().int(),
  latestRunTime: isoDateTime.nullable().default(null),
})

export const domainSchema = z.object({
  code: z.string(),
  name: z.string(),
  bounds: z.tuple([z.number(), z.number(), z.number(), z.number()]).nullable(),
})

const paletteStopSchema = z.object({
  value: z.number(),
  color: z.string(),
  label: z.string().nullable().optional(),
})

export const fieldSchema = z.object({
  code: z.string(),
  variableCode: z.string(),
  name: z.string(),
  variableClass: z.string(),
  levelCode: z.string(),
  levelName: z.string(),
  unit: z.string(),
  palette: z.array(paletteStopSchema).min(1),
  defaultMin: z.number(),
  defaultMax: z.number(),
})

export const variableSchema = z.object({
  code: z.string(),
  variableCode: z.string(),
  name: z.string(),
  variableClass: z.string(),
  levelCode: z.string(),
  levelName: z.string(),
  unit: z.string(),
  products: z.array(z.string()).min(1),
})

export const runSchema = z.object({
  runTime: isoDateTime,
  status: z.string(),
  availableTimeCount: z.number().int().nonnegative(),
})

export const productTimeSchema = z.object({
  validTime: isoDateTime,
  forecastHour: z.number().int().nonnegative().nullable(),
  intervalStart: isoDateTime.nullable(),
  intervalEnd: isoDateTime.nullable(),
  timeKind: z.enum(['instant', 'accumulation', 'average', 'maximum']),
})

export const timelineFrameSchema = productTimeSchema.extend({
  runTime: isoDateTime,
})

export const layerSchema = z.object({
  product: z.string(),
  domain: z.string(),
  runTime: isoDateTime,
  validTime: isoDateTime,
  forecastHour: z.number().int().nonnegative().nullable(),
  field: z.string(),
  variable: z.string(),
  level: z.string(),
  unit: z.string(),
  tileUrl: z.string(),
  token: z.string(),
  bounds: z.tuple([z.number(), z.number(), z.number(), z.number()]).nullable(),
  legend: z.object({
    minimum: z.number(),
    maximum: z.number(),
    palette: z.array(paletteStopSchema).min(1),
  }),
})

export const sampleValueSchema = z.object({
  field: z.string(),
  variable: z.string(),
  level: z.string(),
  value: z.number().nullable(),
  unit: z.string(),
  nodata: z.boolean(),
})

export const sampleSchema = z.object({
  longitude: z.number(),
  latitude: z.number(),
  runTime: isoDateTime,
  validTime: isoDateTime,
  values: z.array(sampleValueSchema),
})

export const windVectorCollectionSchema = z.object({
  type: z.literal('FeatureCollection'),
  product: z.string(),
  domain: z.string(),
  runTime: isoDateTime,
  validTime: isoDateTime,
  unit: z.string(),
  bbox: z.tuple([z.number(), z.number(), z.number(), z.number()]),
  columns: z.number().int().positive(),
  rows: z.number().int().positive(),
  featureCount: z.number().int().nonnegative(),
  features: z.array(
    z.object({
      type: z.literal('Feature'),
      geometry: z.object({
        type: z.literal('Point'),
        coordinates: z.tuple([z.number(), z.number()]),
      }),
      properties: z.object({
        u: z.number(),
        v: z.number(),
        speed: z.number().nonnegative(),
        bearing: z.number().min(0).lt(360),
      }),
    }),
  ),
})

export const cityForecastCollectionSchema = z.object({
  type: z.literal('FeatureCollection'),
  provider: z.literal('eccc'),
  product: z.literal('citypage_weather'),
  generatedAt: isoDateTime,
  issuedAt: isoDateTime,
  validTime: isoDateTime,
  availableStart: isoDateTime,
  availableEnd: isoDateTime,
  featureCount: z.number().int().nonnegative(),
  attribution: z.string(),
  licenseUrl: z.string().url(),
  features: z.array(
    z.object({
      type: z.literal('Feature'),
      id: z.string(),
      geometry: z.object({
        type: z.literal('Point'),
        coordinates: z.tuple([z.number(), z.number()]),
      }),
      properties: z.object({
        areaId: z.string(),
        name: z.string(),
        locality: z.string(),
        province: z.string(),
        issuedAt: isoDateTime,
        sourceSite: z.string(),
        period: z.string(),
        validStart: isoDateTime,
        validEnd: isoDateTime,
        temperatureC: z.number().nullable(),
        temperatureClass: z.string().nullable(),
        relativeHumidityPercent: z.number().nullable(),
        popPercent: z.number().nullable(),
        precipitationAmount: z.string().nullable(),
        condition: z.string(),
      }),
    }),
  ),
})

export const hotspotCollectionSchema = z
  .object({
    type: z.literal('FeatureCollection'),
    bbox: z.tuple([z.number(), z.number(), z.number(), z.number()]).optional(),
    data_date: z.string().regex(/^\d{4}-\d{2}-\d{2}$/),
    generated_at: isoDateTime,
    sensor: z.string(),
    nominal_resolution_metres: z.number().int().positive(),
    feature_count: z.number().int().nonnegative(),
    features: z.array(
      z
        .object({
          type: z.literal('Feature'),
          id: z.union([z.string(), z.number()]).optional(),
          geometry: z.object({
            type: z.literal('Point'),
            coordinates: z.tuple([z.number(), z.number()]),
          }),
          properties: z
            .object({
              observed_at: isoDateTime,
              fwi: z.number().nullable().optional(),
              sensor: z.string().optional(),
            })
            .passthrough(),
        })
        .passthrough(),
    ),
  })
  .passthrough()

const isoDate = z.string().regex(/^\d{4}-\d{2}-\d{2}$/)

export const hotspotDateSummarySchema = z.object({
  dataDate: isoDate,
  featureCount: z.number().int().nonnegative(),
  firstObservation: isoDateTime.nullable(),
  lastObservation: isoDateTime.nullable(),
  bbox: z.tuple([z.number(), z.number(), z.number(), z.number()]).nullable(),
})

export const hotspotDateCollectionSchema = z.object({
  items: z.array(hotspotDateSummarySchema),
  availableStart: isoDate.nullable(),
  availableEnd: isoDate.nullable(),
})

const collection = <T extends z.ZodType>(item: T) =>
  z.object({
    items: z.array(item),
    nextCursor: z.string().nullable().optional(),
  })

export type Product = z.infer<typeof productSchema>
export type Domain = z.infer<typeof domainSchema>
export type Field = z.infer<typeof fieldSchema>
export type Variable = z.infer<typeof variableSchema>
export type ProductRun = z.infer<typeof runSchema>
export type ProductTime = z.infer<typeof productTimeSchema>
export type TimelineFrame = z.infer<typeof timelineFrameSchema>
export type ResolvedLayer = z.infer<typeof layerSchema>
export type Sample = z.infer<typeof sampleSchema>
export type WindVectorCollection = z.infer<typeof windVectorCollectionSchema>
export type CityForecastCollection = z.infer<
  typeof cityForecastCollectionSchema
>
export type HotspotCollection = z.infer<typeof hotspotCollectionSchema>
export type HotspotDateSummary = z.infer<typeof hotspotDateSummarySchema>

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

async function getJson<T>(
  path: string,
  schema: z.ZodType<T>,
  signal?: AbortSignal,
): Promise<T> {
  const response = await fetch(path, {
    headers: { Accept: 'application/json' },
    signal,
  })

  if (!response.ok) {
    let message = `Request failed (${response.status})`
    try {
      const body = (await response.json()) as {
        detail?: string
        message?: string
      }
      message = body.detail ?? body.message ?? message
    } catch {
      // A proxy may return a non-JSON error page. Keep the stable fallback.
    }
    throw new ApiError(message, response.status)
  }

  return schema.parse(await response.json())
}

export const api = {
  cityForecasts: (
    validTime?: string,
    province?: string,
    signal?: AbortSignal,
  ) => {
    const query = new URLSearchParams()
    if (validTime) query.set('valid_time', validTime)
    if (province) query.set('province', province)
    const suffix = query.size > 0 ? `?${query}` : ''
    return getJson(
      `/api/v1/city-forecasts${suffix}`,
      cityForecastCollectionSchema,
      signal,
    )
  },

  getHotspots: (dataDate?: string, signal?: AbortSignal) => {
    const query = dataDate ? `?date=${encodeURIComponent(dataDate)}` : ''
    return getJson(`/api/v1/hotspots${query}`, hotspotCollectionSchema, signal)
  },

  listHotspotDates: (signal?: AbortSignal) =>
    getJson('/api/v1/hotspots/dates', hotspotDateCollectionSchema, signal),

  listProducts: (signal?: AbortSignal) =>
    getJson('/api/v1/products', collection(productSchema), signal).then(
      (value) => value.items,
    ),

  listVariables: (signal?: AbortSignal) =>
    getJson('/api/v1/variables', collection(variableSchema), signal).then(
      (value) => value.items,
    ),

  listDomains: (product: string, signal?: AbortSignal) =>
    getJson(
      `/api/v1/products/${encodeURIComponent(product)}/domains`,
      collection(domainSchema),
      signal,
    ).then((value) => value.items),

  listFields: (product: string, runTime?: string, signal?: AbortSignal) => {
    const query = runTime ? `?run=${encodeURIComponent(runTime)}` : ''
    return getJson(
      `/api/v1/products/${encodeURIComponent(product)}/fields${query}`,
      collection(fieldSchema),
      signal,
    ).then((value) => value.items)
  },

  listRuns: (
    product: string,
    field: string,
    before?: string,
    signal?: AbortSignal,
  ) => {
    const query = new URLSearchParams({ limit: '100' })
    query.set('field', field)
    if (before) query.set('before', before)
    return getJson(
      `/api/v1/products/${encodeURIComponent(product)}/runs?${query}`,
      collection(runSchema),
      signal,
    )
  },

  listTimes: (
    product: string,
    runTime: string,
    field: string,
    signal?: AbortSignal,
  ) =>
    getJson(
      `/api/v1/products/${encodeURIComponent(product)}/runs/${encodeURIComponent(runTime)}/times?field=${encodeURIComponent(field)}`,
      collection(productTimeSchema),
      signal,
    ).then((value) => value.items),

  listTimeline: (
    product: string,
    domain: string,
    field: string,
    range?: { start: string; end: string },
    signal?: AbortSignal,
  ) => {
    const query = new URLSearchParams({
      domain,
      field,
      limit: '1000',
    })
    if (range) {
      query.set('start', range.start)
      query.set('end', range.end)
    }
    return getJson(
      `/api/v1/products/${encodeURIComponent(product)}/timeline?${query}`,
      z.object({
        items: z.array(timelineFrameSchema),
        truncated: z.boolean(),
      }),
      signal,
    )
  },

  resolveLayer: (
    selection: {
      product: string
      domain: string
      run: string
      field: string
      validTime: string
      style?: string
      minimum?: number
      maximum?: number
      opacityCutoff?: number
    },
    signal?: AbortSignal,
  ) => {
    const query = new URLSearchParams({
      product: selection.product,
      domain: selection.domain,
      run: selection.run,
      field: selection.field,
      valid_time: selection.validTime,
      style: selection.style ?? 'default',
    })
    if (selection.minimum !== undefined && selection.maximum !== undefined) {
      query.set('minimum', selection.minimum.toString())
      query.set('maximum', selection.maximum.toString())
    }
    if (selection.opacityCutoff !== undefined) {
      query.set('opacity_cutoff', selection.opacityCutoff.toString())
    }
    return getJson(`/api/v1/layers/resolve?${query}`, layerSchema, signal)
  },

  sample: (
    selection: {
      product: string
      domain: string
      run: string
      validTime: string
      longitude: number
      latitude: number
      fields: string[]
    },
    signal?: AbortSignal,
  ) => {
    const query = new URLSearchParams({
      product: selection.product,
      domain: selection.domain,
      run: selection.run,
      valid_time: selection.validTime,
      longitude: selection.longitude.toString(),
      latitude: selection.latitude.toString(),
    })
    for (const field of selection.fields) query.append('field', field)
    return getJson(`/api/v1/sample?${query}`, sampleSchema, signal)
  },

  windVectors: (
    selection: {
      product: string
      domain: string
      run: string
      validTime: string
      bbox: [number, number, number, number]
      columns: number
      rows: number
    },
    signal?: AbortSignal,
  ) => {
    const query = new URLSearchParams({
      product: selection.product,
      domain: selection.domain,
      run: selection.run,
      valid_time: selection.validTime,
      west: selection.bbox[0].toString(),
      south: selection.bbox[1].toString(),
      east: selection.bbox[2].toString(),
      north: selection.bbox[3].toString(),
      columns: selection.columns.toString(),
      rows: selection.rows.toString(),
    })
    return getJson(
      `/api/v1/wind-vectors?${query}`,
      windVectorCollectionSchema,
      signal,
    )
  },
}
