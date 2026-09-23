export type GroupableVariable = {
  code: string
  variableCode: string
  variableClass: string
}

export type VariableGroup<T extends GroupableVariable> = {
  code: string
  label: string
  items: T[]
}

const GROUPS = [
  { code: 'temperature_moisture', label: 'Temperature & humidity' },
  { code: 'wind', label: 'Wind' },
  { code: 'pressure', label: 'Pressure' },
  { code: 'clouds_visibility', label: 'Clouds & visibility' },
  { code: 'precipitation_snow', label: 'Precipitation & snow' },
  { code: 'air_quality', label: 'Air quality forecasts' },
  { code: 'wildfire_smoke', label: 'Wildfire smoke & plume' },
  { code: 'wildfire_observations', label: 'Wildfire observations' },
  { code: 'other', label: 'Other variables' },
] as const

function groupCode(variable: GroupableVariable): string {
  const identifier = `${variable.code} ${variable.variableCode}`.toLowerCase()

  if (variable.variableClass === 'wildfire_observation') {
    return 'wildfire_observations'
  }
  if (identifier.includes('wildfire_')) return 'wildfire_smoke'
  if (
    variable.variableClass === 'precipitation' ||
    identifier.includes('precipitation') ||
    identifier.includes('snowfall')
  ) {
    return 'precipitation_snow'
  }
  if (identifier.includes('wind')) return 'wind'
  if (identifier.includes('pressure')) return 'pressure'
  if (identifier.includes('cloud') || identifier.includes('visibility')) {
    return 'clouds_visibility'
  }
  if (identifier.includes('temperature') || identifier.includes('humidity')) {
    return 'temperature_moisture'
  }
  if (variable.variableClass === 'air_quality') return 'air_quality'
  return 'other'
}

/** Preserve catalogue order inside stable, two-level variable groups. */
export function groupVariables<T extends GroupableVariable>(
  variables: T[],
): VariableGroup<T>[] {
  const grouped = new Map<string, T[]>()
  for (const variable of variables) {
    const code = groupCode(variable)
    grouped.set(code, [...(grouped.get(code) ?? []), variable])
  }
  return GROUPS.flatMap((group) => {
    const items = grouped.get(group.code) ?? []
    return items.length > 0 ? [{ ...group, items }] : []
  })
}
