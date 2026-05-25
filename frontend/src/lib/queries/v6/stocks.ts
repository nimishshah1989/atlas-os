// frontend/src/lib/queries/v6/stocks.ts
//
// Direct Supabase query for the v6 Stocks page (and sector-detail constituent
// table). Builds the 4-tenure ConvictionTape from atlas_conviction_daily rows.
//
// Joins:
//   atlas_universe_stocks     ← symbol / company_name / sector / tier
//   atlas_conviction_daily    ← per-tenure verdict + IC + cell id (4 rows / iid)
//   atlas_stock_metrics_daily ← ret_1m / 3m / 6m / 12m + rs_pctile_3m
//   atlas_stock_signal_unified ← rs_state / engine_state (Stage) / is_investable
//
// Returns ScreenStock[] (same shape the page consumes from api/v1).

import 'server-only'
import sql from '@/lib/db'
import type {
  ScreenStock,
  ConvictionTape,
  ConvictionVerdict,
  Tenure,
  Tier,
  Verdict,
} from '@/lib/api/v1'

type StockRow = {
  iid: string
  symbol: string
  company_name: string | null
  sector: string | null
  tier: string | null
  rs_state: string | null
  engine_state: string | null
  is_investable: boolean | null
  ret_1m: string | null
  ret_3m: string | null
  ret_6m: string | null
  ret_12m: string | null
  rs_pctile_3m: string | null
}

type ConvictionRow = {
  iid: string
  tenure: string
  verdict: string
  ic: string | null
  best_rule_id: string | null
}

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

export type GetStocksForDateParams = {
  /** Optional sector filter (matches atlas_universe_stocks.sector exact). */
  sector?: string
  /** Optional tier filter. */
  tier?: Tier
  /** Soft limit on rows returned. */
  limit?: number
}

/**
 * Return one ScreenStock row per stock in the universe for a snapshot_date.
 *
 * The conviction_tape is built by zipping the 4-tenure rows from
 * atlas_conviction_daily into a single per-iid object. Stocks with no
 * conviction rows get the all-NEUTRAL tape.
 */
export async function getStocksForDate(
  snapshotDate: string,
  params: GetStocksForDateParams = {},
): Promise<ScreenStock[]> {
  const sector = params.sector ?? null
  const tier = params.tier ?? null
  // 10000 is effectively "no limit" for the v6 universe (~750 stocks).
  const limit = params.limit ?? 10000

  // Stock metrics are at snapshot_date; stock signal_unified may lag by a day
  // or two — pin to a single most-recent signal_date via subquery (much
  // faster than DISTINCT ON across the full table).
  const stockRows = await sql<StockRow[]>`
    SELECT
      u.instrument_id::text          AS iid,
      u.symbol,
      u.company_name,
      u.sector,
      u.tier,
      ls.rs_state,
      ls.engine_state,
      ls.is_investable,
      m.ret_1m::text                 AS ret_1m,
      m.ret_3m::text                 AS ret_3m,
      m.ret_6m::text                 AS ret_6m,
      m.ret_12m::text                AS ret_12m,
      m.rs_pctile_3m::text           AS rs_pctile_3m
    FROM atlas.atlas_universe_stocks u
    LEFT JOIN atlas.atlas_stock_signal_unified ls
      ON ls.instrument_id = u.instrument_id
     AND ls.date = (
       SELECT MAX(date)
       FROM atlas.atlas_stock_signal_unified
       WHERE date <= ${snapshotDate}
     )
    LEFT JOIN atlas.atlas_stock_metrics_daily m
      ON m.instrument_id = u.instrument_id
     AND m.date          = ${snapshotDate}
    WHERE u.effective_to IS NULL
      AND (${sector}::text IS NULL OR u.sector = ${sector})
      AND (${tier}::text   IS NULL OR u.tier   = ${tier})
    ORDER BY
      (m.rs_pctile_3m IS NULL),
      m.rs_pctile_3m DESC
    LIMIT ${limit}
  `

  if (stockRows.length === 0) return []

  const iids = stockRows.map(r => r.iid)
  const convRows = await sql<ConvictionRow[]>`
    SELECT
      c.instrument_id::text   AS iid,
      c.tenure,
      c.verdict,
      c.ic::text              AS ic,
      c.best_rule_id::text    AS best_rule_id
    FROM atlas.atlas_conviction_daily c
    WHERE c.snapshot_date = ${snapshotDate}
      AND c.instrument_id::text = ANY(${iids}::text[])
  `

  const byIid = new Map<string, ConvictionTape>()
  for (const cr of convRows) {
    if (!isTenure(cr.tenure)) continue
    let tape = byIid.get(cr.iid)
    if (!tape) {
      tape = { ...EMPTY_TAPE }
      byIid.set(cr.iid, tape)
    }
    tape[cr.tenure] = {
      direction: toVerdict(cr.verdict),
      ic: cr.ic != null ? Number(cr.ic) : null,
      rule_count: cr.best_rule_id ? 1 : 0,
      top_rule_id: cr.best_rule_id,
    }
  }

  return stockRows.map((r): ScreenStock => ({
    iid: r.iid,
    symbol: r.symbol,
    company_name: r.company_name,
    sector: r.sector,
    tier: toTier(r.tier),
    mcap_inr: null,
    rs_state: r.rs_state,
    stage: r.engine_state,
    conviction_tape: byIid.get(r.iid) ?? EMPTY_TAPE,
    ret_1m: r.ret_1m != null ? Number(r.ret_1m) : null,
    ret_3m: r.ret_3m != null ? Number(r.ret_3m) : null,
    ret_6m: r.ret_6m != null ? Number(r.ret_6m) : null,
    ret_12m: r.ret_12m != null ? Number(r.ret_12m) : null,
    rs_pctile_3m: r.rs_pctile_3m != null ? Number(r.rs_pctile_3m) : null,
    // is_investable defaults to true on missing — page filters that count it.
    is_investable: r.is_investable ?? true,
  }))
}

function isTenure(t: string): t is Tenure {
  return t === '1m' || t === '3m' || t === '6m' || t === '12m'
}

function toVerdict(v: string): Verdict {
  if (v === 'POSITIVE' || v === 'NEGATIVE' || v === 'NEUTRAL') return v
  return 'NEUTRAL'
}

function toTier(t: string | null): Tier {
  if (t === 'Large' || t === 'Mid' || t === 'Small') return t
  return 'Large'
}
