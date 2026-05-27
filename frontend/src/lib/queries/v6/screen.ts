// frontend/src/lib/queries/v6/screen.ts
//
// Multi-criteria stock screener query for /v6/screening.
// All filter clauses are parameterized via postgres-js template literals —
// no string interpolation is used in WHERE conditions.
//
// Sources:
//   atlas_universe_stocks  ← symbol / company_name / sector / tier
//   atlas_conviction_daily ← per-tenure verdict + IC (aggregated to dominant action + max IC)
//   atlas_stock_metrics_daily ← rs_pctile_3m
//   atlas_cell_definitions ← drift_status (via atlas_conviction_daily.cell_id join)
//
// Sector rank is computed within this query using RANK() OVER (ORDER BY rs_pctile_3m DESC)
// partitioned by sector, so sector_rank_max=3 means "top 3 within their sector".
//
// v6.0 scope: stocks only. Funds + ETFs deferred to v6.1.

import 'server-only'
import sql from '@/lib/db'
import type { StockV6Row } from './stocks'
import type { ConvictionTape, ConvictionVerdict } from '@/lib/api/v1'

// ---------------------------------------------------------------------------
// Public types
// ---------------------------------------------------------------------------

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

// ---------------------------------------------------------------------------
// Internal types
// ---------------------------------------------------------------------------

type ScreenRow = {
  iid: string
  symbol: string
  company_name: string | null
  sector: string | null
  tier: string | null
  rs_state: string | null
  engine_state: string | null
  is_investable: boolean | null
  ret_1d: string | null
  ret_1w: string | null
  ret_1m: string | null
  ret_3m: string | null
  ret_6m: string | null
  ret_12m: string | null
  rs_pctile_3m: string | null
  // conviction aggregate columns
  dominant_action: string | null
  max_ic: string | null
  drift_status: string | null
  sector_rank: string | null
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const EMPTY_VERDICT: ConvictionVerdict = {
  direction: 'NEUTRAL',
  ic: null,
  rule_count: 0,
  top_rule_id: null,
}

const EMPTY_TAPE: ConvictionTape = {
  '1m': EMPTY_VERDICT,
  '3m': EMPTY_VERDICT,
  '6m': EMPTY_VERDICT,
  '12m': EMPTY_VERDICT,
}

// ---------------------------------------------------------------------------
// Main export
// ---------------------------------------------------------------------------

/**
 * Multi-criteria screener: returns StockV6Row[] matching ALL active filter criteria.
 * Empty filter = full universe (up to 10000 rows).
 * All WHERE clauses use SQL bind variables; no string interpolation.
 */
export async function screenStocks(
  filter: ScreenFilter,
  snapshotDate?: string,
): Promise<StockV6Row[]> {
  // Resolve snapshot date: use provided date or latest available.
  let targetDate = snapshotDate ?? null
  if (!targetDate) {
    const dateRows = await sql<Array<{ d: string | null }>>`
      SELECT MAX(snapshot_date)::text AS d
      FROM atlas.atlas_conviction_daily
    `
    targetDate = dateRows[0]?.d ?? new Date().toISOString().slice(0, 10)
  }

  // Resolve "latest signal_unified date" ≤ targetDate once.
  const signalDateRows = await sql<Array<{ d: string | null }>>`
    SELECT MAX(date)::text AS d
    FROM atlas.atlas_stock_signal_unified
    WHERE date <= ${targetDate}
  `
  const signalDate = signalDateRows[0]?.d ?? targetDate

  // Normalised filter values
  const sectors: string[] | null =
    filter.sectors && filter.sectors.length > 0 ? filter.sectors : null
  const driftStatuses: string[] | null =
    filter.drift_statuses && filter.drift_statuses.length > 0
      ? filter.drift_statuses
      : null
  const actions: string[] | null =
    filter.actions && filter.actions.length > 0 ? filter.actions : null
  const capTiers: string[] | null =
    filter.cap_tiers && filter.cap_tiers.length > 0 ? filter.cap_tiers : null

  // rs_pct_min: UI passes 0-100; DB stores 0-1 scale
  const rsPctMin: number | null =
    filter.rs_pct_min != null ? filter.rs_pct_min / 100 : null
  const icMin: number | null = filter.ic_min ?? null
  const icMax: number | null = filter.ic_max ?? null
  const sectorRankMax: number | null = filter.sector_rank_max ?? null

  // Build conviction aggregate + sector rank in SQL (avoids Python GROUP BY on large table).
  // conviction CTE: per-iid dominant action (most POSITIVE wins), max IC across tenures,
  // worst drift_status (healthy < drift_warn < deprecated priority order).
  const rows = await sql<ScreenRow[]>`
    WITH conv AS (
      SELECT
        cd.instrument_id,
        -- dominant action: majority vote across tenures; POSITIVE > NEUTRAL > NEGATIVE
        CASE
          WHEN SUM(CASE WHEN cd.verdict = 'POSITIVE' THEN 1 ELSE 0 END) >
               SUM(CASE WHEN cd.verdict = 'NEGATIVE' THEN 1 ELSE 0 END)
               AND SUM(CASE WHEN cd.verdict = 'POSITIVE' THEN 1 ELSE 0 END) >= 2
          THEN 'POSITIVE'
          WHEN SUM(CASE WHEN cd.verdict = 'NEGATIVE' THEN 1 ELSE 0 END) >
               SUM(CASE WHEN cd.verdict = 'POSITIVE' THEN 1 ELSE 0 END)
               AND SUM(CASE WHEN cd.verdict = 'NEGATIVE' THEN 1 ELSE 0 END) >= 2
          THEN 'NEGATIVE'
          ELSE 'NEUTRAL'
        END                                         AS dominant_action,
        MAX(cd.ic::numeric)                         AS max_ic
      FROM atlas.atlas_conviction_daily cd
      WHERE cd.snapshot_date = ${targetDate}::date
      GROUP BY cd.instrument_id
    ),
    -- drift_status from the cell that fired most recently for each stock
    drift AS (
      SELECT DISTINCT ON (sc.instrument_id)
        sc.instrument_id,
        cel.drift_status
      FROM atlas.atlas_signal_calls sc
      JOIN atlas.atlas_cell_definitions cel ON cel.cell_id = sc.cell_id
      WHERE sc.exit_date IS NULL
      ORDER BY sc.instrument_id, sc.date DESC
    ),
    -- sector rank by rs_pctile_3m within sector
    ranked AS (
      SELECT
        u.instrument_id,
        RANK() OVER (
          PARTITION BY u.sector
          ORDER BY m.rs_pctile_3m DESC NULLS LAST
        ) AS sector_rank
      FROM atlas.atlas_universe_stocks u
      LEFT JOIN atlas.atlas_stock_metrics_daily m
        ON m.instrument_id = u.instrument_id
       AND m.date = ${targetDate}::date
      WHERE u.effective_to IS NULL
    )
    SELECT
      u.instrument_id::text                     AS iid,
      u.symbol,
      u.company_name,
      u.sector,
      u.tier,
      ls.rs_state,
      ls.engine_state,
      ls.is_investable,
      m.ret_1d::text                            AS ret_1d,
      m.ret_1w::text                            AS ret_1w,
      m.ret_1m::text                            AS ret_1m,
      m.ret_3m::text                            AS ret_3m,
      m.ret_6m::text                            AS ret_6m,
      m.ret_12m::text                           AS ret_12m,
      m.rs_pctile_3m::text                      AS rs_pctile_3m,
      conv.dominant_action,
      conv.max_ic::text                         AS max_ic,
      drift.drift_status,
      ranked.sector_rank::text                  AS sector_rank
    FROM atlas.atlas_universe_stocks u
    LEFT JOIN atlas.atlas_stock_signal_unified ls
      ON ls.instrument_id = u.instrument_id
     AND ls.date          = ${signalDate}::date
    LEFT JOIN atlas.atlas_stock_metrics_daily m
      ON m.instrument_id  = u.instrument_id
     AND m.date           = ${targetDate}::date
    LEFT JOIN conv
      ON conv.instrument_id = u.instrument_id
    LEFT JOIN drift
      ON drift.instrument_id = u.instrument_id
    LEFT JOIN ranked
      ON ranked.instrument_id = u.instrument_id
    WHERE u.effective_to IS NULL
      -- tier filter
      AND (${capTiers}::text[] IS NULL OR u.tier::text = ANY(${capTiers}::text[]))
      -- sector filter
      AND (${sectors}::text[] IS NULL OR u.sector = ANY(${sectors}::text[]))
      -- drift_status filter
      AND (${driftStatuses}::text[] IS NULL OR COALESCE(drift.drift_status::text, 'healthy') = ANY(${driftStatuses}::text[]))
      -- rs_pct filter (DB stores 0-1)
      AND (${rsPctMin}::numeric IS NULL OR COALESCE(m.rs_pctile_3m, 0) >= ${rsPctMin}::numeric)
      -- ic_min filter
      AND (${icMin}::numeric IS NULL OR COALESCE(conv.max_ic, 0) >= ${icMin}::numeric)
      -- ic_max filter
      AND (${icMax}::numeric IS NULL OR COALESCE(conv.max_ic, 0) <= ${icMax}::numeric)
      -- action filter
      AND (${actions}::text[] IS NULL OR COALESCE(conv.dominant_action, 'NEUTRAL') = ANY(${actions}::text[]))
      -- sector rank filter
      AND (${sectorRankMax}::int IS NULL OR COALESCE(ranked.sector_rank, 9999) <= ${sectorRankMax}::int)
    ORDER BY
      (m.rs_pctile_3m IS NULL),
      m.rs_pctile_3m DESC
    LIMIT 10000
  `

  if (rows.length === 0) return []

  // Apply in_book filter post-query (requires calling getHeldIidSet which is already cached).
  // We keep this in TypeScript to avoid a complex SQL subquery on an empty table at v6.0.
  let filtered: ScreenRow[] = [...rows]
  if (filter.in_book !== undefined) {
    const { getHeldIidSet } = await import('./portfolio_holdings')
    const heldSet = await getHeldIidSet()
    filtered = filter.in_book
      ? filtered.filter(r => heldSet.has(r.iid))
      : filtered.filter(r => !heldSet.has(r.iid))
  }

  return filtered.map(mapScreenRow)
}

// ---------------------------------------------------------------------------
// URL encode / decode helpers
// ---------------------------------------------------------------------------

/**
 * Serialize a ScreenFilter to a URLSearchParams-compatible record.
 * All values are strings for URL safety; arrays are comma-separated.
 */
export function filterToParams(f: ScreenFilter): Record<string, string> {
  const p: Record<string, string> = {}
  if (f.ic_min != null) p.ic_min = String(f.ic_min)
  if (f.ic_max != null) p.ic_max = String(f.ic_max)
  if (f.sectors?.length)        p.sectors = f.sectors.join(',')
  if (f.sector_rank_max != null) p.sector_rank_max = String(f.sector_rank_max)
  if (f.drift_statuses?.length) p.drift_statuses = f.drift_statuses.join(',')
  if (f.rs_pct_min != null)     p.rs_pct_min = String(f.rs_pct_min)
  if (f.in_book != null)        p.in_book = f.in_book ? '1' : '0'
  if (f.actions?.length)        p.actions = f.actions.join(',')
  if (f.cap_tiers?.length)      p.cap_tiers = f.cap_tiers.join(',')
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

// ---------------------------------------------------------------------------
// Row mapper
// ---------------------------------------------------------------------------

function mapScreenRow(r: ScreenRow): StockV6Row {
  const tier =
    r.tier === 'Large' || r.tier === 'Mid' || r.tier === 'Small' ? r.tier : 'Large'
  const dominantDir =
    r.dominant_action === 'POSITIVE' || r.dominant_action === 'NEGATIVE'
      ? r.dominant_action
      : 'NEUTRAL'
  const maxIc = r.max_ic != null ? Number(r.max_ic) : null

  // Build a single-verdict tape using the dominant action for each tenure slot.
  const verdict: ConvictionVerdict = {
    direction: dominantDir,
    ic: maxIc,
    rule_count: 0,
    top_rule_id: null,
  }
  const tape: ConvictionTape = {
    '1m': dominantDir !== 'NEUTRAL' ? verdict : EMPTY_VERDICT,
    '3m': dominantDir !== 'NEUTRAL' ? verdict : EMPTY_VERDICT,
    '6m': verdict,   // always show something for the IC display column
    '12m': EMPTY_VERDICT,
  }

  return {
    iid: r.iid,
    symbol: r.symbol,
    company_name: r.company_name,
    sector: r.sector,
    tier,
    mcap_inr: null,
    rs_state: r.rs_state,
    stage: r.engine_state,
    conviction_tape: tape,
    ret_1d: r.ret_1d != null ? Number(r.ret_1d) : null,
    ret_1w: r.ret_1w != null ? Number(r.ret_1w) : null,
    ret_1m: r.ret_1m != null ? Number(r.ret_1m) : null,
    ret_3m: r.ret_3m != null ? Number(r.ret_3m) : null,
    ret_6m: r.ret_6m != null ? Number(r.ret_6m) : null,
    ret_12m: r.ret_12m != null ? Number(r.ret_12m) : null,
    rs_pctile_3m: r.rs_pctile_3m != null ? Number(r.rs_pctile_3m) : null,
    is_investable: r.is_investable ?? true,
  }
}
