export type TimeRange = '1W' | '1M' | '3M' | '6M' | '1Y'

export function rangeToDays(range: TimeRange): number {
  const map: Record<TimeRange, number> = {
    '1W': 7,
    '1M': 30,
    '3M': 90,
    '6M': 180,
    '1Y': 365,
  }
  return map[range]
}
