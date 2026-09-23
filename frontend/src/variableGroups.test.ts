import { describe, expect, it } from 'vitest'
import { groupVariables } from './variableGroups'

describe('groupVariables', () => {
  it('builds stable weather, air-quality, and wildfire menu groups', () => {
    const variables = [
      ['air_temperature_2m', 'air_temperature', 'atmosphere'],
      ['relative_humidity_2m', 'relative_humidity', 'atmosphere'],
      ['wind_gust_10m', 'wind_gust', 'atmosphere'],
      ['surface_pressure', 'surface_pressure', 'atmosphere'],
      ['total_cloud_cover', 'total_cloud_cover', 'atmosphere'],
      ['snowfall_1h', 'snowfall', 'precipitation'],
      ['pm25_surface', 'pm25', 'air_quality'],
      ['wildfire_pm25_surface', 'wildfire_pm25', 'air_quality'],
      ['wildfire_hotspots', 'wildfire_hotspots', 'wildfire_observation'],
    ].map(([code, variableCode, variableClass]) => ({
      code,
      variableCode,
      variableClass,
    }))

    expect(
      groupVariables(variables).map((group) => [
        group.label,
        group.items.map((item) => item.code),
      ]),
    ).toEqual([
      [
        'Temperature & humidity',
        ['air_temperature_2m', 'relative_humidity_2m'],
      ],
      ['Wind', ['wind_gust_10m']],
      ['Pressure', ['surface_pressure']],
      ['Clouds & visibility', ['total_cloud_cover']],
      ['Precipitation & snow', ['snowfall_1h']],
      ['Air quality forecasts', ['pm25_surface']],
      ['Wildfire smoke & plume', ['wildfire_pm25_surface']],
      ['Wildfire observations', ['wildfire_hotspots']],
    ])
  })
})
