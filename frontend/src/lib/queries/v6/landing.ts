// frontend/src/lib/queries/v6/landing.ts
//
// Landing-page–specific queries for Page 01 (Market Regime).
//
// Provides two functions:
//   getRegimeJourney12w() — last 84 days downsampled to weekly (12 cells)
//   getTopConvictionCalls() — active signal calls split across Stocks/ETFs/Funds tabs
//
// Data sources:
//   atlas_market_regime_daily  — regime_state + breadth/vix/dispersion per day
//   atlas_signal_calls         — active stock conviction calls
//   atlas_etf_signal_calls     — active ETF conviction calls
//   atlas_fund_scorecard       — fund leader/avoid snapshot

import 'server-only'
import sql from '@/lib/db'
import { toNumber, toNumberOr } from '@/lib/v6/decimal'

// ---------------------------------------------------------------------------
// 12-week journey types
// ---------------------------------------------------------------------------

// 2026-05-29 (Batch 4): swapped smallcap_rs + dispersion for the actual
// regime classifier inputs (mcclellan + trend slope) so the trailing-12w
// panel SHOWS what the classifier USES. The four inputs match
// atlas/compute/regime.py classify_regime_state — see also
// RegimeClassifierInputs (the LC chart pilot above this panel).
export type WeeklyRegimeCell = {
  /** ISO date of the last trading day in this week (displayed label). */
  week_end_date: string
  /** Regime state for the week (majority vote within window). */
  regime_state: string
  /** Breadth: % of Nifty 500 above 50D EMA — matches classifier input. */
  breadth_pct: number | null
  /** India VIX — matches classifier input. */
  india_vix: number | null
  /** McClellan Oscillator (breadth momentum) — matches classifier input. */
  mcclellan: number | null
  /** Nifty 500 50D EMA slope as % per day — trend proxy used by classifier. */
  trend_slope: number | null
  /** True for the most recent (current) week. */
  is_current: boolean
}

type RawRegimeRow = {
  date: string
  regime_state: string
  pct_above_ema_50: string | null
  india_vix: string | null
  mcclellan_oscillator: string | null
  nifty500_ema_50_slope: string | null
}

/**
 * Fetch last 84 days of regime data (daily) and downsample to 12 weekly cells.
 *
 * Downsampling strategy: group days into 7-day buckets (oldest → newest).
 * For each bucket: use the last day's regime_state (most recent read).
 * Breadth/VIX/Dispersion: use the last non-null value in the bucket.
 *
 * Returns exactly 12 cells (may be fewer if DB has <84 days).
 */
export async function getRegimeJourney12w(): Promise<WeeklyRegimeCell[]> {
  const rows = await sql<RawRegimeRow[]>`
    SELECT
      date::text                                  AS date,
      regime_state,
      pct_above_ema_50::text                      AS pct_above_ema_50,
      india_vix::text                             AS india_vix,
      mcclellan_oscillator::text                  AS mcclellan_oscillator,
      nifty500_ema_50_slope::text                 AS nifty500_ema_50_slope
    FROM atlas.atlas_market_regime_daily
    WHERE date >= CURRENT_DATE - INTERVAL '84 days'
    ORDER BY date ASC
  `

  if (rows.length === 0) return []

  // Group into 7-day buckets: assign each row to a bucket index.
  // Bucket 0 = oldest 7 rows, bucket 11 = newest 7 rows.
  const totalRows = rows.length
  const bucketCount = Math.min(12, Math.ceil(totalRows / 7))

  const buckets: RawRegimeRow[][] = Array.from({ length: bucketCount }, () => [])

  rows.forEach((row, i) => {
    // Distribute rows evenly across buckets (floor-based bucket assignment)
    const bucketIdx = Math.min(
      bucketCount - 1,
      Math.floor((i * bucketCount) / totalRows),
    )
    buckets[bucketIdx].push(row)
  })

  const cells: WeeklyRegimeCell[] = buckets.map((bucket, idx) => {
    if (bucket.length === 0) {
      return {
        week_end_date: '',
        regime_state: 'Neutral',
        breadth_pct: null,
        india_vix: null,
        mcclellan: null,
        trend_slope: null,
        is_current: false,
      }
    }
    // Use last row in bucket as the "representative" for the week
    const last = bucket[bucket.length - 1]

    // Find last non-null value for each metric within the bucket
    let breadthPct: number | null = null
    let indiaVix: number | null = null
    let mcclellan: number | null = null
    let trendSlope: number | null = null

    for (const r of bucket) {
      const bval = toNumber(r.pct_above_ema_50)
      if (bval != null) breadthPct = Math.round(bval * 100)
      const vixVal = toNumber(r.india_vix)
      if (vixVal != null) indiaVix = vixVal
      const mcVal = toNumber(r.mcclellan_oscillator)
      if (mcVal != null) mcclellan = mcVal
      const slopeVal = toNumber(r.nifty500_ema_50_slope)
      if (slopeVal != null) trendSlope = slopeVal
    }

    return {
      week_end_date: last.date,
      regime_state: last.regime_state,
      breadth_pct: breadthPct,
      india_vix: indiaVix != null ? Math.round(indiaVix * 10) / 10 : null,
      mcclellan: mcclellan != null ? Math.round(mcclellan * 10) / 10 : null,
      // slope is a fraction like 0.0006 → show as % per day (×100)
      trend_slope: trendSlope != null ? Math.round(trendSlope * 10000) / 100 : null,
      is_current: idx === buckets.length - 1,
    }
  })

  return cells
}

// ---------------------------------------------------------------------------
// Today's conviction tabs types
// ---------------------------------------------------------------------------

export type ConvictionCallRow = {
  symbol: string
  company_name: string | null
  /** e.g. "Mid 12m" or "ETF 6m" */
  cell_label: string
  sector: string | null
  cap_tier: string | null
  /** 0–1 float. For funds this is composite_score, not signal confidence — use is_fund flag to switch display. */
  confidence: number
  /** 'POSITIVE' | 'NEGATIVE' | 'NEUTRAL' */
  action: string
  /** Stringified decimal e.g. "+5.3" — null when not computed */
  predicted_excess: string | null
  /** True if the call was fired today (date = CURRENT_DATE) */
  is_new: boolean
  /** True for rows from atlas_fund_scorecard (confidence = composite_score, not signal probability) */
  is_fund: boolean
  /** For fund rows: true = Atlas Leader designation, false otherwise */
  is_atlas_leader: boolean
  /** ISO date when the underlying signal_call first fired. Null for fund rows. */
  entry_date: string | null
  /** Number of trading days the call has been open. Null for fund rows. */
  days_held: number | null
}

export type ConvictionCallsResult = {
  stocks: ConvictionCallRow[]
  /** Count of new stock calls fired today */
  stocks_new_count: number
  etfs: ConvictionCallRow[]
  etfs_new_count: number
  funds: ConvictionCallRow[]
  funds_new_count: number
}

type RawStockCallRow = {
  symbol: string | null
  company_name: string | null
  sector: string | null
  cap_tier: string
  tenure: string
  action: string
  confidence_unconditional: string
  predicted_excess: string | null
  entry_date: string
}

type RawEtfCallRow = {
  ticker: string | null
  etf_name: string | null
  category: string | null
  tenure: string
  action: string
  confidence_unconditional: string
  predicted_excess: string | null
  entry_date: string
}

type RawFundRow = {
  scheme_name: string | null
  fund_category: string | null
  amc: string | null
  composite_score: string | null
  is_atlas_leader: boolean | null
  is_avoid: boolean | null
}

/**
 * Fetch the three conviction-tab datasets in one Promise.all call.
 *
 * Stocks: active signal_calls ordered by confidence DESC.
 * ETFs: active etf_signal_calls ordered by confidence DESC.
 * Funds: fund scorecard leaders (is_atlas_leader=true, not avoid),
 *        ordered by composite_score DESC. Funds don't have a "call" paradigm,
 *        so we synthesize an action label from is_atlas_leader / is_avoid.
 *
 * Row counts are small (<100 per tab) — in-process processing is fine.
 */
export async function getTopConvictionCalls(): Promise<ConvictionCallsResult> {
  const today = new Date().toISOString().slice(0, 10)

  const [stockRows, etfRows, fundRows] = await Promise.all([
    // Stocks: active signal calls (exit_date IS NULL), newest entries first
    sql<RawStockCallRow[]>`
      SELECT
        u.symbol,
        u.company_name,
        u.sector,
        sc.cap_tier_at_trigger::text                  AS cap_tier,
        sc.tenure::text                               AS tenure,
        sc.action::text                               AS action,
        sc.confidence_unconditional::text             AS confidence_unconditional,
        sc.predicted_excess::text                     AS predicted_excess,
        sc.date::text                                 AS entry_date
      FROM atlas.atlas_signal_calls sc
      LEFT JOIN atlas.atlas_universe_stocks u
             ON u.instrument_id = sc.instrument_id
      WHERE sc.exit_date IS NULL
      ORDER BY sc.confidence_unconditional DESC NULLS LAST
      LIMIT 20
    `,

    // ETFs: active ETF signal calls
    // Join through atlas_etf_scorecard (which has instrument_id + ticker)
    // to get ticker and name. atlas_universe_etfs has no instrument_id column.
    sql<RawEtfCallRow[]>`
      SELECT
        s.ticker,
        COALESCE(s.etf_name, u.etf_name)             AS etf_name,
        s.etf_category                               AS category,
        esc.tenure::text                              AS tenure,
        esc.action::text                              AS action,
        esc.confidence_unconditional::text            AS confidence_unconditional,
        esc.predicted_excess::text                    AS predicted_excess,
        esc.date::text                                AS entry_date
      FROM atlas.atlas_etf_signal_calls esc
      JOIN atlas.atlas_etf_scorecard s
             ON s.instrument_id = esc.etf_instrument_id
            AND s.snapshot_date = (SELECT MAX(snapshot_date) FROM atlas.atlas_etf_scorecard)
      LEFT JOIN atlas.atlas_universe_etfs u
             ON u.ticker = s.ticker
            AND u.effective_to IS NULL
      WHERE esc.exit_date IS NULL
      ORDER BY esc.confidence_unconditional DESC NULLS LAST
      LIMIT 15
    `.catch(() => [] as RawEtfCallRow[]),

    // Funds: latest fund scorecard snapshot (leaders + avoids for context)
    sql<RawFundRow[]>`
      SELECT
        COALESCE(fs.fund_name, uf.scheme_name)       AS scheme_name,
        fs.fund_category,
        fs.amc,
        fs.composite_score::text                     AS composite_score,
        fs.is_atlas_leader,
        fs.is_avoid
      FROM atlas.atlas_fund_scorecard fs
      LEFT JOIN atlas.atlas_universe_funds uf
             ON uf.mstar_id = fs.scheme_code
      WHERE fs.snapshot_date = (
        SELECT MAX(snapshot_date) FROM atlas.atlas_fund_scorecard
      )
      ORDER BY fs.composite_score DESC NULLS LAST
      LIMIT 15
    `.catch(() => [] as RawFundRow[]),
  ])

  // Compute days_held from entry_date — naive calendar-day count is good
  // enough for a "day N on the conviction list" UI affordance. We don't
  // bother with NSE-trading-day-only math; weekends + holidays bias the
  // number by a couple days at most, which doesn't matter for "this call
  // is on day 3 vs day 30".
  const daysHeld = (entryDate: string): number => {
    const entry = new Date(entryDate + 'T00:00:00Z').getTime()
    const now = new Date(today + 'T00:00:00Z').getTime()
    if (!Number.isFinite(entry) || !Number.isFinite(now)) return 0
    return Math.max(0, Math.round((now - entry) / (1000 * 60 * 60 * 24)))
  }

  const stocks: ConvictionCallRow[] = stockRows.map(r => ({
    symbol: r.symbol ?? 'UNKNOWN',
    company_name: r.company_name,
    sector: r.sector,
    cap_tier: r.cap_tier,
    cell_label: `${r.cap_tier} ${r.tenure}`,
    confidence: toNumberOr(r.confidence_unconditional, 0),
    action: r.action,
    predicted_excess: formatExcess(r.predicted_excess),
    is_new: r.entry_date === today,
    is_fund: false,
    is_atlas_leader: false,
    entry_date: r.entry_date,
    days_held: daysHeld(r.entry_date),
  }))

  const etfs: ConvictionCallRow[] = etfRows.map(r => ({
    symbol: r.ticker ?? 'ETF',
    company_name: r.etf_name,
    sector: r.category,
    cap_tier: null,
    cell_label: `ETF ${r.tenure}`,
    confidence: toNumberOr(r.confidence_unconditional, 0),
    action: r.action,
    predicted_excess: formatExcess(r.predicted_excess),
    is_new: r.entry_date === today,
    is_fund: false,
    is_atlas_leader: false,
    entry_date: r.entry_date,
    days_held: daysHeld(r.entry_date),
  }))

  const funds: ConvictionCallRow[] = fundRows.map(r => ({
    symbol: r.amc?.slice(0, 8) ?? 'FUND',
    company_name: r.scheme_name,
    sector: r.fund_category,
    cap_tier: null,
    cell_label: r.is_avoid ? 'AVOID' : r.is_atlas_leader ? 'Atlas Leader' : 'Neutral',
    // composite_score is a quality score (not signal conviction probability).
    // is_fund=true tells the render layer to display a quality badge instead of confidence bar.
    confidence: Math.min(toNumberOr(r.composite_score, 0), 1),
    action: r.is_avoid ? 'NEGATIVE' : r.is_atlas_leader ? 'POSITIVE' : 'NEUTRAL',
    predicted_excess: null,
    is_new: false,
    is_fund: true,
    is_atlas_leader: r.is_atlas_leader ?? false,
    entry_date: null,
    days_held: null,
  }))

  return {
    stocks,
    stocks_new_count: stocks.filter(s => s.is_new).length,
    etfs,
    etfs_new_count: etfs.filter(e => e.is_new).length,
    funds,
    funds_new_count: 0, // funds have no "new" concept — no daily signals
  }
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatExcess(raw: string | null | undefined): string | null {
  if (raw == null) return null
  const n = toNumber(raw)
  if (n == null) return null
  const sign = n >= 0 ? '+' : ''
  return `${sign}${(n * 100).toFixed(1)}%`
}
