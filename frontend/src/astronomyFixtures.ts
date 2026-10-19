import type { AstronomyForecast } from './astronomyApi'

/** Synthetic test data; never used as a weather fallback. */
export const astronomyFixture: AstronomyForecast = {
  schemaVersion: 1,
  generatedAt: '2026-10-19T16:00:00Z',
  preview: true,
  latitude: 44.65,
  longitude: -63.57,
  timeZone: 'America/Halifax',
  product: 'gdps',
  source: 'ECCC GDPS',
  runTime: '2026-10-19T12:00:00Z',
  stale: false,
  mode: 'deep_sky',
  ruleVersion: 'preview-v1',
  method: 'Nearest cell',
  limitations: ['Seeing and transparency unavailable.'],
  unavailableFields: ['seeing'],
  sample: null,
  frames: [
    {
      time: '2026-10-20T04:00:00Z',
      cloudPercent: 10,
      temperatureC: 8,
      humidityPercent: null,
      windKmh: 5,
      gustKmh: 10,
      dewPointC: null,
      dewRisk: null,
      rainMm: 0,
      rainStart: '2026-10-20T03:00:00Z',
      sunAltitudeDegrees: -40,
      moonAltitudeDegrees: -10,
      moonIlluminatedPercent: 25,
      moonPhaseDegrees: 60,
    },
  ],
  nights: [
    {
      date: '2026-10-19',
      start: '2026-10-19T15:00:00Z',
      end: '2026-10-20T15:00:00Z',
      state: 'window',
      summary: 'Cloud, wind and rain meet your limits.',
      events: {
        sunset: '2026-10-19T21:00:00Z',
        sunrise: '2026-10-20T10:00:00Z',
        moonrise: null,
        moonset: '2026-10-19T23:00:00Z',
      },
      darkness: [
        {
          start: '2026-10-19T23:00:00Z',
          end: '2026-10-20T09:00:00Z',
          minutes: 600,
        },
      ],
      moonlessDarkness: [],
      windows: [
        {
          start: '2026-10-20T04:00:00Z',
          end: '2026-10-20T06:00:00Z',
          minutes: 120,
        },
      ],
      moonIlluminatedPercent: 25,
      moonPhaseDegrees: 60,
    },
  ],
}
