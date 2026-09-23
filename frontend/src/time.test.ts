import { describe, expect, it } from 'vitest'
import { formatForecastHour, formatUtcTimestamp } from './time'

describe('formatForecastHour', () => {
  it('formats forecast lead times with three digits', () => {
    expect(formatForecastHour(0)).toBe('F000')
    expect(formatForecastHour(12)).toBe('F012')
    expect(formatForecastHour(240)).toBe('F240')
  })

  it('rejects invalid forecast hours', () => {
    expect(() => formatForecastHour(-1)).toThrow(RangeError)
  })
})

describe('formatUtcTimestamp', () => {
  it('formats the displayed valid time with seconds in UTC', () => {
    expect(formatUtcTimestamp('2026-07-21T23:00:05Z')).toBe(
      '2026-07-21 23:00:05',
    )
    expect(formatUtcTimestamp('2026-07-21T20:30:05-03:00')).toBe(
      '2026-07-21 23:30:05',
    )
  })
})
