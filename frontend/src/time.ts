export function formatForecastHour(hour: number): string {
  if (!Number.isInteger(hour) || hour < 0) {
    throw new RangeError('Forecast hour must be a non-negative integer')
  }
  return `F${hour.toString().padStart(3, '0')}`
}

export function formatUtcTimestamp(value: string): string {
  return new Date(value).toISOString().slice(0, 19).replace('T', ' ')
}
