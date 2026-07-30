// What the FM needs to see the moment he picks an instrument: the price he is acting
// on, the momentum and relative-strength ladder, the trend/technical state, and the
// conviction the engine already computed — with anything worth cross-checking marked.
//
// Two honest gaps, surfaced rather than papered over:
//  - the lens/conviction engine scores STOCKS ONLY (atlas_lens_scores_daily has no ETF
//    rows), so an ETF returns conviction: null with a reason. A neutral-looking score
//    standing in for no computation is exactly what rule #0 forbids.
//  - a stock added in the last universe widening has no lens row until the next nightly
//    compute; that is also conviction: null, with a different reason.
import 'server-only'

import sql from '@/lib/db'
import { toPp } from '@/lib/insight'

export type ReturnLadder = { window: string; retPp: number | null; rsPp: number | null }

export type Conviction = {
  composite: number | null
  tier: string | null
  technical: number | null
  fundamental: number | null
  flow: number | null
  valuation: number | null
  catalyst: number | null
  valuationZone: string | null
  degradation: number | null
  smartMoney: number | null
  riskFlags: string[]
}

export type InstrumentInsight = {
  key: string
  symbol: string
  name: string
  sector: string | null
  assetClass: 'stock' | 'etf'
  /** Last stored close and the session it belongs to — never a live tick. */
  lastClose: number | null
  closeAsOf: string | null
  metricsAsOf: string | null
  ladder: ReturnLadder[]
  rsi14: number | null
  aboveEma50: boolean | null
  aboveEma200: boolean | null
  pos52w: number | null
  volRatio30d: number | null
  conviction: Conviction | null
  /** Why conviction is absent, when it is. */
  convictionAbsentReason: string | null
}

const WINDOWS = ['1d', '1w', '1m', '3m', '6m', '12m'] as const
export type Benchmark = 'n50' | 'n500'

const num = (v: unknown): number | null => (v == null ? null : Number(v))
const bool = (v: unknown): boolean | null => (v == null ? null : Boolean(v))

/**
 * One instrument's decision panel. `key` is the search route's hit key
 * ("stock:BIOCON" / "etf:GOLDBEES"); benchmark picks the RS column family.
 */
export async function getInstrumentInsight(
  key: string,
  benchmark: Benchmark = 'n500',
): Promise<InstrumentInsight | null> {
  const [cls, symbol] = key.split(':')
  if ((cls !== 'stock' && cls !== 'etf') || !symbol) return null

  // RS column family is chosen here, not interpolated from caller input.
  const rsCols =
    benchmark === 'n50'
      ? sql`t.rs_1d_n50 AS rs_1d, t.rs_1w_n50 AS rs_1w, t.rs_1m_n50 AS rs_1m,
            t.rs_3m_n50 AS rs_3m, t.rs_6m_n50 AS rs_6m, t.rs_12m_n50 AS rs_12m`
      : sql`t.rs_1d_n500 AS rs_1d, t.rs_1w_n500 AS rs_1w, t.rs_1m_n500 AS rs_1m,
            t.rs_3m_n500 AS rs_3m, t.rs_6m_n500 AS rs_6m, t.rs_12m_n500 AS rs_12m`

  // Close lives in a different table per asset class (mirrors load_prices).
  const closeExpr =
    cls === 'etf'
      ? sql`(SELECT o.close_adj FROM atlas_foundation.ohlcv_etf o
             WHERE o.ticker = im.symbol AND o.close_adj > 0 ORDER BY o.date DESC LIMIT 1)`
      : sql`(SELECT o.close_adj FROM atlas_foundation.ohlcv_stock o
             WHERE o.instrument_id = im.instrument_id AND o.close_adj > 0 ORDER BY o.date DESC LIMIT 1)`
  const closeDateExpr =
    cls === 'etf'
      ? sql`(SELECT to_char(o.date,'YYYY-MM-DD') FROM atlas_foundation.ohlcv_etf o
             WHERE o.ticker = im.symbol AND o.close_adj > 0 ORDER BY o.date DESC LIMIT 1)`
      : sql`(SELECT to_char(o.date,'YYYY-MM-DD') FROM atlas_foundation.ohlcv_stock o
             WHERE o.instrument_id = im.instrument_id AND o.close_adj > 0 ORDER BY o.date DESC LIMIT 1)`

  const rows = await sql<Array<Record<string, unknown>>>`
    SELECT im.symbol, im.name, im.sector, im.asset_class,
           ${closeExpr} AS last_close,
           ${closeDateExpr} AS close_as_of,
           to_char(t.date,'YYYY-MM-DD') AS metrics_as_of,
           t.ret_1d, t.ret_1w, t.ret_1m, t.ret_3m, t.ret_6m, t.ret_12m,
           ${rsCols},
           t.rsi_14, t.above_ema_50, t.above_ema_200, t.pos_52w, t.vol_ratio_30d,
           l.composite, l.conviction_tier, l.technical, l.fundamental, l.flow,
           l.valuation, l.catalyst, l.valuation_zone, l.degradation_score,
           l.smart_money_score, l.risk_flags
    FROM atlas_foundation.instrument_master im
    LEFT JOIN atlas_foundation.technical_daily t
           ON t.instrument_id = im.instrument_id
          AND t.date = (SELECT max(date) FROM atlas_foundation.technical_daily
                        WHERE asset_class = ${cls})
    LEFT JOIN atlas_foundation.atlas_lens_scores_daily l
           ON l.instrument_id = im.instrument_id
          AND l.date = (SELECT max(date) FROM atlas_foundation.atlas_lens_scores_daily)
    WHERE im.symbol = ${symbol} AND im.asset_class = ${cls}
    LIMIT 1`

  const r = rows[0]
  if (!r) return null

  const ladder: ReturnLadder[] = WINDOWS.map((w) => ({
    window: w,
    retPp: toPp(num(r[`ret_${w}`])),
    rsPp: toPp(num(r[`rs_${w}`])),
  }))

  const scored = r.composite != null
  const conviction: Conviction | null = scored
    ? {
        composite: num(r.composite),
        tier: r.conviction_tier == null ? null : String(r.conviction_tier),
        technical: num(r.technical),
        fundamental: num(r.fundamental),
        flow: num(r.flow),
        valuation: num(r.valuation),
        catalyst: num(r.catalyst),
        valuationZone: r.valuation_zone == null ? null : String(r.valuation_zone),
        degradation: num(r.degradation_score),
        smartMoney: num(r.smart_money_score),
        riskFlags: Array.isArray(r.risk_flags) ? r.risk_flags.map(String) : [],
      }
    : null

  return {
    key,
    symbol: String(r.symbol),
    name: String(r.name ?? ''),
    sector: r.sector == null ? null : String(r.sector),
    assetClass: cls,
    lastClose: num(r.last_close),
    closeAsOf: r.close_as_of == null ? null : String(r.close_as_of),
    metricsAsOf: r.metrics_as_of == null ? null : String(r.metrics_as_of),
    ladder,
    rsi14: num(r.rsi_14),
    aboveEma50: bool(r.above_ema_50),
    aboveEma200: bool(r.above_ema_200),
    pos52w: num(r.pos_52w),
    volRatio30d: num(r.vol_ratio_30d),
    conviction,
    convictionAbsentReason: scored
      ? null
      : cls === 'etf'
        ? 'Index and commodity ETFs are not lens-scored — conviction applies to individual companies.'
        : 'No lens score yet — a newly covered name gets one on the next nightly compute.',
  }
}
