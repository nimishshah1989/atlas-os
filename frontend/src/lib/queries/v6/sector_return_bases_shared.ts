// frontend/src/lib/queries/v6/sector_return_bases_shared.ts
//
// Client-safe types + pure helpers for the dual-basis sector returns.
// NO 'server-only' / no DB import here, so client components (toggles, tables)
// can import these. The DB query lives in sector_return_bases.ts.
//
// All return values are decimal fractions (0.074 = +7.4%).

export type ReturnWindow = '1d' | '1w' | '1m' | '3m' | '6m' | '12m'

export type ReturnSet = {
  ret_1d: number | null
  ret_1w: number | null
  ret_1m: number | null
  ret_3m: number | null
  ret_6m: number | null
  ret_12m: number | null
}

export type ReturnBasis = 'index' | 'bottomup'

export type SectorReturnBases = {
  sector_name: string
  index_code: string | null
  index: ReturnSet
  bottomup: ReturnSet
}

export type ReturnBasesPayload = {
  sectors: SectorReturnBases[]
  nifty500: ReturnSet
  as_of: string | null
}

export const NULL_RETURN_SET: ReturnSet = {
  ret_1d: null, ret_1w: null, ret_1m: null, ret_3m: null, ret_6m: null, ret_12m: null,
}

const FIELD: Record<ReturnWindow, keyof ReturnSet> = {
  '1d': 'ret_1d', '1w': 'ret_1w', '1m': 'ret_1m', '3m': 'ret_3m', '6m': 'ret_6m', '12m': 'ret_12m',
}

/** Active-basis return for a window. */
export function basisReturn(s: SectorReturnBases, basis: ReturnBasis, w: ReturnWindow): number | null {
  return s[basis][FIELD[w]]
}

/** RS (pp vs Nifty 500) for a window under a basis = basis_return − nifty500_return. */
export function basisRs(
  s: SectorReturnBases, nifty500: ReturnSet, basis: ReturnBasis, w: ReturnWindow,
): number | null {
  const r = s[basis][FIELD[w]]
  const b = nifty500[FIELD[w]]
  if (r == null || b == null) return null
  return r - b
}
