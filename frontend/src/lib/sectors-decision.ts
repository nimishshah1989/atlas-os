// src/lib/sectors-decision.ts
// Sector decision logic — shared between page and components

export type SectorDecision = 'ENTER' | 'ROTATE IN' | 'WATCH' | 'HOLD' | 'PASS' | 'EXIT'

export function getSectorDecision(
  state: string,
  rsState: string | null,
  momentumState: string | null,
): SectorDecision {
  if (state === 'Avoid') return 'EXIT'
  if (state === 'Underweight') return 'EXIT'
  if (state === 'Overweight' && momentumState === 'Improving') return 'ENTER'
  if (state === 'Overweight' && momentumState === 'Deteriorating') return 'HOLD'
  if (state === 'Neutral' && rsState === 'Overweight_RS' && momentumState === 'Improving') return 'ROTATE IN'
  if (state === 'Neutral' && momentumState === 'Improving') return 'WATCH'
  return 'PASS'
}
