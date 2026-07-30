// What the FM needs to see the moment he picks an instrument: the price he is acting
// on, the momentum and relative-strength ladder, the trend/technical state, and the
// conviction the engine already computed — with anything worth cross-checking marked.
//
// Conviction reaches an instrument by TWO different routes, because Atlas scores the two
// asset classes differently:
//  - a STOCK is scored directly in atlas_lens_scores_daily (composite + tier + lenses).
//  - an ETF has no row there; it is scored as a holdings-weighted roll-up of the stock
//    atom, headlined by LEADERSHIP-BREADTH (share of holdings weight that are top-decile
//    leaders) rather than a cap-weighted composite. That definition lives in etf_lens.ts
//    and is reused here, so ETF conviction has exactly one definition in the codebase.
//
// Absence is therefore not one thing, and the three cases must not be conflated:
//  - commodity/debt/international ETF: no equity holdings, so breadth is UNDEFINED;
//  - equity ETF whose Morningstar name-bridge fails (~35% of NSE ETFs): identity gap;
//  - stock newly added by the 750-name widening: no lens row until the next compute.
// A neutral-looking score standing in for any of these is what rule #0 forbids.
import 'server-only'

import sql from '@/lib/db'
import { toPp } from '@/lib/insight'
import { getEtfLensByNseTicker } from './etf_lens'

export type ReturnLadder = { window: string; retPp: number | null; rsPp: number | null }

export type Conviction = {
  /** Stock: the engine composite. ETF: the holdings-weighted composite. */
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
  /** ETFs only — the headline metric for a basket. Percent of holdings weight. */
  breadthPct: number | null
  nHoldings: number | null
  nLeaders: number | null
  /** Which route produced this, so the UI can label it honestly. */
  basis: 'stock-lens' | 'etf-holdings-rollup'
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
  /** For the price-vs-moving-average stack the FM reads as long/short alignment. */
  ema21: number | null
  ema50: number | null
  ema200: number | null
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
           t.ema_21, t.ema_50, t.ema_200,
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

  let conviction: Conviction | null =
    r.composite == null
      ? null
      : {
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
          breadthPct: null,
          nHoldings: null,
          nLeaders: null,
          basis: 'stock-lens',
        }

  // An ETF has no lens row of its own — its conviction is the holdings roll-up.
  let absent: string | null = null
  if (conviction == null && cls === 'etf') {
    const roll = await getEtfLensByNseTicker(symbol)
    if (roll) {
      conviction = {
        // The weighted lens vector is the descriptive part; breadth is the headline.
        composite: null,
        tier: null,
        technical: roll.v_tech,
        fundamental: roll.v_fund,
        flow: roll.v_flow,
        valuation: roll.v_val,
        catalyst: roll.v_cat,
        valuationZone: null,
        degradation: null,
        smartMoney: null,
        riskFlags: [],
        // breadth is NULL when the basket holds no top-decile leader at all; that is a
        // real zero, not missing data, so report it as 0%.
        breadthPct: roll.breadth == null ? 0 : roll.breadth * 100,
        nHoldings: roll.n_holdings,
        nLeaders: roll.n_leaders,
        basis: 'etf-holdings-rollup',
      }
    } else {
      absent =
        'No holdings roll-up for this ETF — either it holds no equities (gold, silver, debt) ' +
        'or its Morningstar identity did not bridge to this NSE ticker.'
    }
  } else if (conviction == null) {
    absent = 'No lens score yet — a newly covered name gets one on the next nightly compute.'
  }

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
    ema21: num(r.ema_21),
    ema50: num(r.ema_50),
    ema200: num(r.ema_200),
    conviction,
    convictionAbsentReason: absent,
  }
}
