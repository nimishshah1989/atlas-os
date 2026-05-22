// rs_state taxonomy: atlas_stock_signal_unified emits exactly these 5 (CASE on rs_rank_12m).
// "Consolidating"/"Emerging" were retired — do not re-add without a matching view change.
export const RS_ORDER    = ['Leader', 'Strong', 'Average', 'Weak', 'Laggard'] as const
export const MOM_ORDER   = ['Accelerating', 'Improving', 'Flat', 'Deteriorating', 'Collapsing'] as const
export const RISK_ORDER  = ['Low', 'Normal', 'Elevated', 'High', 'Below Trend'] as const
export const VOL_ORDER   = ['Accumulation', 'Steady-Buying', 'Neutral', 'Distribution', 'Heavy Distribution'] as const

export const NAV_STATE_ORDER = [
  'Leader NAV', 'Strong NAV', 'Emerging NAV', 'Consolidating NAV',
  'Average NAV', 'Weak NAV', 'Laggard NAV', 'DISLOCATION_SUSPENDED',
] as const

export const COMPOSITION_STATE_ORDER = [
  'Aligned', 'Mixed', 'Misaligned', 'NO_DISCLOSURE', 'DISLOCATION_SUSPENDED',
] as const

export const HOLDINGS_STATE_ORDER = [
  'Strong-Holdings', 'Mixed-Holdings', 'Weak-Holdings',
  'NO_DISCLOSURE', 'DISLOCATION_SUSPENDED',
] as const

export const RECOMMENDATION_ORDER = [
  'Recommended', 'Hold', 'Reduce', 'Exit',
] as const

/** Index of state in the given order array. Returns array length if unknown or null (sinks to bottom in ASC). */
export function stateRank(order: readonly string[], val: string | null): number {
  if (!val) return order.length
  const i = order.indexOf(val)
  return i === -1 ? order.length : i
}

/** True if the row matches a free-text search query (case-insensitive; empty = match all). */
export function matchesSearch(
  row: { symbol: string; companyName: string },
  query: string,
): boolean {
  if (!query.trim()) return true
  const q = query.trim().toLowerCase()
  return row.symbol.toLowerCase().includes(q) || row.companyName.toLowerCase().includes(q)
}

type AnyRow = Record<string, string | null | boolean | number | undefined>

/**
 * Returns a sort key for a screener column.
 * - State columns → stateRank index (Leader=0 sorts before Laggard in ASC)
 * - Numeric string columns → parseFloat; null → -Infinity (sinks in DESC)
 * - Boolean → 1/0
 */
export function buildSortKey(column: string, row: AnyRow): number | string {
  const v = row[column]
  if (column === 'rs_state')       return stateRank(RS_ORDER, v as string | null)
  if (column === 'momentum_state') return stateRank(MOM_ORDER, v as string | null)
  if (column === 'risk_state')     return stateRank(RISK_ORDER, v as string | null)
  if (column === 'volume_state')   return stateRank(VOL_ORDER, v as string | null)
  if (column === 'nav_state')         return stateRank(NAV_STATE_ORDER, v as string | null)
  if (column === 'composition_state') return stateRank(COMPOSITION_STATE_ORDER, v as string | null)
  if (column === 'holdings_state')    return stateRank(HOLDINGS_STATE_ORDER, v as string | null)
  if (column === 'recommendation')    return stateRank(RECOMMENDATION_ORDER, v as string | null)
  if (typeof v === 'boolean')      return v ? 1 : 0
  if (typeof v === 'number')       return v
  if (typeof v === 'string' && v !== '') return parseFloat(v)
  return -Infinity
}
