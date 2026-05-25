// frontend/src/lib/queries/v6/screen-filter.ts
//
// Pure filter type + URL serialization helpers for /v6/screening.
// No DB access, no server-only marker — safe to import from client components.
// The server-only query (screenStocks) lives in screen.ts.

export type ScreenFilter = {
  /** IC range [min, max]. Applied against the dominant tenure's IC. */
  ic_min?: number
  ic_max?: number
  /** Sector names (exact match). Empty / undefined = all sectors. */
  sectors?: string[]
  /**
   * Maximum within-sector RS rank. 1 = top stock per sector only.
   * Rank is computed by rs_pctile_3m DESC within each sector.
   */
  sector_rank_max?: number
  /** Cell drift_status values to include. */
  drift_statuses?: Array<'healthy' | 'drift_warn' | 'deprecated'>
  /** Minimum RS percentile (0-1 scale in DB; UI passes 0-100 and we divide). */
  rs_pct_min?: number
  /** true = only stocks in the paper portfolio book, false = only stocks not in book. */
  in_book?: boolean
  /** Dominant action filter. */
  actions?: Array<'POSITIVE' | 'NEUTRAL' | 'NEGATIVE'>
  /** Cap tier filter. */
  cap_tiers?: Array<'Small' | 'Mid' | 'Large'>
}

/**
 * Serialize a ScreenFilter to a URLSearchParams-compatible record.
 * All values are strings for URL safety; arrays are comma-separated.
 */
export function filterToParams(f: ScreenFilter): Record<string, string> {
  const p: Record<string, string> = {}
  if (f.ic_min != null) p.ic_min = String(f.ic_min)
  if (f.ic_max != null) p.ic_max = String(f.ic_max)
  if (f.sectors?.length) p.sectors = f.sectors.join(',')
  if (f.sector_rank_max != null) p.sector_rank_max = String(f.sector_rank_max)
  if (f.drift_statuses?.length) p.drift_statuses = f.drift_statuses.join(',')
  if (f.rs_pct_min != null) p.rs_pct_min = String(f.rs_pct_min)
  if (f.in_book != null) p.in_book = f.in_book ? '1' : '0'
  if (f.actions?.length) p.actions = f.actions.join(',')
  if (f.cap_tiers?.length) p.cap_tiers = f.cap_tiers.join(',')
  return p
}

/**
 * Parse a URLSearchParams (or plain object) back into a ScreenFilter.
 * Unknown / invalid values are silently ignored.
 */
export function paramsToFilter(
  params: URLSearchParams | Record<string, string>,
): ScreenFilter {
  const get = (k: string): string | null =>
    params instanceof URLSearchParams ? params.get(k) : (params[k] ?? null)

  const f: ScreenFilter = {}

  const icMin = get('ic_min')
  if (icMin !== null && icMin !== '' && !isNaN(Number(icMin))) f.ic_min = Number(icMin)

  const icMax = get('ic_max')
  if (icMax !== null && icMax !== '' && !isNaN(Number(icMax))) f.ic_max = Number(icMax)

  const sectors = get('sectors')
  if (sectors) f.sectors = sectors.split(',').filter(Boolean)

  const srm = get('sector_rank_max')
  if (srm !== null && !isNaN(Number(srm))) f.sector_rank_max = Number(srm)

  const ds = get('drift_statuses')
  if (ds) {
    f.drift_statuses = ds.split(',').filter(
      (v): v is 'healthy' | 'drift_warn' | 'deprecated' =>
        v === 'healthy' || v === 'drift_warn' || v === 'deprecated',
    )
  }

  const rsp = get('rs_pct_min')
  if (rsp !== null && !isNaN(Number(rsp))) f.rs_pct_min = Number(rsp)

  const inBook = get('in_book')
  if (inBook === '1') f.in_book = true
  if (inBook === '0') f.in_book = false

  const actions = get('actions')
  if (actions) {
    f.actions = actions.split(',').filter(
      (v): v is 'POSITIVE' | 'NEUTRAL' | 'NEGATIVE' =>
        v === 'POSITIVE' || v === 'NEUTRAL' || v === 'NEGATIVE',
    )
  }

  const ct = get('cap_tiers')
  if (ct) {
    f.cap_tiers = ct.split(',').filter(
      (v): v is 'Small' | 'Mid' | 'Large' =>
        v === 'Small' || v === 'Mid' || v === 'Large',
    )
  }

  return f
}
