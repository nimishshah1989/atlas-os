import type { SectorSnapshot } from '@/lib/queries/sectors'

// Non-actionable buckets: kept in DB but excluded from positioning views.
// These are NSE catch-all classifications that don't map to a tradeable
// sector theme and have no dedicated NSE sector index to benchmark against.
// Reclassification at the data layer (using de_instrument.industry as fallback)
// is the long-term fix — tracked in decisions.jsonl.
export const EXCLUDED_SECTORS: readonly string[] = [
  'Conglomerate',  // multi-business holding companies (Bajaj Holdings etc.)
  'Diversified',   // NSE catch-all; stocks are better classified by industry
  'MNC',           // not a sector — these stocks belong to their primary industry
  'Services',      // too heterogeneous — covers 3 unrelated businesses
]

// Below this count, breadth and RS-participation aren't statistically
// meaningful and the bubble's position is dominated by a single name.
export const MIN_CONSTITUENT_COUNT = 5

export type SectorFilterResult<T extends SectorSnapshot> = {
  actionable: T[]
  excluded: Array<{ sector_name: string; reason: 'non_actionable' | 'too_small'; constituent_count: number }>
}

export function filterSectors<T extends SectorSnapshot>(sectors: T[]): SectorFilterResult<T> {
  const actionable: T[] = []
  const excluded: SectorFilterResult<T>['excluded'] = []
  for (const s of sectors) {
    if (EXCLUDED_SECTORS.includes(s.sector_name)) {
      excluded.push({ sector_name: s.sector_name, reason: 'non_actionable', constituent_count: s.constituent_count })
      continue
    }
    if (s.constituent_count < MIN_CONSTITUENT_COUNT) {
      excluded.push({ sector_name: s.sector_name, reason: 'too_small', constituent_count: s.constituent_count })
      continue
    }
    actionable.push(s)
  }
  return { actionable, excluded }
}
