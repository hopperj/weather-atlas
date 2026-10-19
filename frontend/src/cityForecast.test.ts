import { describe, expect, it } from 'vitest'
import {
  cityForecastInBounds,
  cityForecastTimes,
  forecastMetric,
  hasPrecipitationRisk,
  issuedPrecipitationAmountLabel,
  precipitationAmountLabel,
  precipitationLikelihood,
} from './cityForecast'
import type { MapBounds } from './mapBounds'

describe('city forecast presentation', () => {
  const towns: [number, number][] = [
    [-66.12, 43.84], // Yarmouth
    [-63.6, 44.65], // Halifax
    [-63.28, 45.36], // Truro
    [-60.18, 46.13], // Sydney
  ]

  it('shows the provincial overview and narrows to just the towns in a close-up', () => {
    const overview: MapBounds = [-66.7, 43.2, -59.5, 47.2]
    const closeUp: MapBounds = [-63.7, 44.6, -63.5, 44.7]
    expect(
      towns.filter((town) => cityForecastInBounds(town, overview)),
    ).toEqual(towns)
    expect(towns.filter((town) => cityForecastInBounds(town, closeUp))).toEqual(
      [towns[1]],
    )
  })

  it('does not retain offscreen towns within the old 0.6-degree margin', () => {
    expect(
      cityForecastInBounds([-63.6, 44.65], [-63.5, 44.7, -63.4, 44.8]),
    ).toBe(false)
    expect(
      cityForecastInBounds([-63.5, 44.7], [-63.5, 44.7, -63.4, 44.8]),
    ).toBe(true)
  })

  it('builds a bounded seven-day half-day timeline', () => {
    const times = cityForecastTimes(
      {
        availableStart: '2026-07-28T09:00:00Z',
        availableEnd: '2026-08-04T09:00:00Z',
      },
      new Date('2026-07-28T19:00:00Z'),
    )

    expect(times[0]).toBe('2026-07-28T19:00:00.000Z')
    expect(times.at(-1)).toBe('2026-08-04T07:00:00.000Z')
    expect(times).toHaveLength(14)
  })

  it('formats issued values while preserving missing data', () => {
    expect(forecastMetric(24, '°C')).toBe('24°C')
    expect(forecastMetric(null, '%')).toBe('—')
  })

  it.each([
    ['Periods of rain', 'Rain expected'],
    ['Showers', 'Rain expected'],
    ['A few showers.', 'Rain expected'],
    [' Periods of drizzle or rain. ', 'Rain expected'],
    ['Chance of showers', 'Rain possible'],
    ['Risk of thunderstorms', 'Thunderstorms possible'],
    ['Snow', 'Snow expected'],
    ['Periods of snow', 'Snow expected'],
    ['Rain mixed with snow', 'Rain or snow expected'],
    ['Chance of rain showers or wet flurries', 'Rain or snow possible'],
    ['Freezing rain', 'Freezing rain expected'],
    ['Ice pellets', 'Ice pellets expected'],
    ['Sunny', null],
    ['Cloudy', null],
    ['', null],
    ['No rain', null],
    ['Blowing snow', null],
    ['Rain ending then clearing', null],
  ])(
    'restates unpublished probability conservatively: %s',
    (condition, expected) => {
      expect(precipitationLikelihood(null, condition!)).toBe(expected)
    },
  )

  it('preserves numeric probabilities, including zero, without inferring 100%', () => {
    for (const pop of [0, 30, 80, 100]) {
      expect(precipitationLikelihood(pop, 'Rain')).toBe(`${pop}%`)
    }
    for (const pop of [-1, 101, NaN, Infinity]) {
      expect(precipitationLikelihood(pop, 'Rain')).toBe('Rain expected')
    }
  })

  it('never invents an amount from POP or rounds a positive trace to zero', () => {
    for (const pop of [1, 30, 80, 100]) {
      for (const amount of [0, null, -1, NaN, Infinity]) {
        expect(precipitationAmountLabel(amount, pop)).toBe('Amount uncertain')
      }
      expect(precipitationAmountLabel(0.001, pop)).toBe('<0.1 mm')
      expect(precipitationAmountLabel(0.1, pop)).toBe('0.1 mm')
      expect(precipitationAmountLabel(1.24, pop)).toBe('1.2 mm')
    }
    expect(precipitationAmountLabel(0, 0, 'Rain')).toBe('0.0 mm')
    expect(precipitationAmountLabel(null, 0, 'Rain')).toBe('—')
    expect(precipitationAmountLabel(0, null, 'Sunny')).toBe('0.0 mm')
    expect(precipitationAmountLabel(null, null)).toBe('—')
    expect(precipitationAmountLabel(0, null, 'Chance of showers')).toBe(
      'Amount uncertain',
    )
    expect(hasPrecipitationRisk(0, 'Rain')).toBe(false)
    expect(hasPrecipitationRisk(NaN, 'Rain')).toBe(true)
    expect(hasPrecipitationRisk(null, 'No rain')).toBe(false)
  })

  it('preserves issued ranges and snow units but avoids a risk paired with a pure zero', () => {
    for (const amount of ['0 mm', '0.0 mm', '0 cm', ' 0.00 MM ', '0']) {
      expect(issuedPrecipitationAmountLabel(amount, 30)).toBe(
        'Amount uncertain',
      )
      expect(issuedPrecipitationAmountLabel(amount, 0, 'Showers')).toBe(amount)
    }
    for (const amount of [
      '0 to 2 mm',
      '5 to 10 mm',
      '2 cm',
      '<0.1 mm',
      'Trace',
    ]) {
      expect(issuedPrecipitationAmountLabel(amount, 30)).toBe(amount)
    }
  })
})
