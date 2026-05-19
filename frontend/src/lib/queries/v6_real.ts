// src/lib/queries/v6_real.ts
// REAL DB query layer for the v6 trading model command center.
// Source tables (all populated, 10y of data):
//   - atlas.atlas_stock_conviction_daily   → top picks + composite score + contributing_signals JSONB
//   - atlas.atlas_universe_stocks          → symbol/name/sector/in_nifty_500 resolver
//   - atlas.atlas_stock_metrics_daily      → returns + close prices (10y)
//   - atlas.atlas_market_regime_daily      → regime_state, deployment_multiplier, VIX, breadth (10y)
//   - atlas.atlas_etf_metrics_daily        → sleeve ETF TSMOM (GOLDBEES, LIQUIDBEES, GILT5YBEES)
//
// Backtest metrics (CAGR/MDD/Sharpe/Calmar) are null until Plan 2 (backend trading engine)
// produces atlas_v6_strategy_runs rows. The UI shows "—" or "Plan 2 pending" for these.
//
// IMPORTANT: this file replaces the older v6.ts mock layer. Pages import from here.

import 'server-only'
import sql from '@/lib/db'

export type ConfidenceBand = 'HIGH' | 'MED' | 'LOW'
export type RegimeLevel = 'calm' | 'normal' | 'yellow' | 'orange' | 'red' | 'crash'

export type V6Holding = {
  symbol: string
  name: string
  weight_pct: number
  composite_score: number
  days_held: number
  pnl_since_entry_pct: number
  confidence: ConfidenceBand
  sector: string
  hrp_cluster: string
}

export type V6RegimeSignal = {
  name: string
  firing: boolean
  reading: string
  threshold: string
}

export type V6CrisisSleeveLeg = {
  symbol: string
  name: string
  weight_pct: number
  tsmom_12m_return_pct: number
}

export type V6BookSnapshot = {
  as_of: string
  cagr_net_pct: number | null
  vol_annualized_pct: number | null
  max_drawdown_pct: number | null
  sharpe_net: number | null
  calmar: number | null
  win_rate_pct: number | null
  capacity_cr: number | null
  gross_exposure_pct: number
  cash_pct: number
  holdings: V6Holding[]
  regime: {
    score: number
    level: RegimeLevel
    gross_multiplier: number
    signals: V6RegimeSignal[]
    raw_state: string
  }
  crisis_sleeve: {
    total_pct: number
    legs: V6CrisisSleeveLeg[]
  }
  goal_post: {
    passes_all_constraints: boolean | null
    constraints: { name: string; target: string; actual: string; pass: boolean | null }[]
  }
  last_rebalance: {
    date: string | null
    entered: { symbol: string; weight_pct: number; reason: string }[]
    exited: { symbol: string; reason: string }[]
  }
}

function mapConfidence(label: string): ConfidenceBand {
  if (label === 'industry_grade') return 'HIGH'
  if (label === 'baseline') return 'MED'
  return 'LOW'
}

function mapRegime(state: string, deployment: number): { level: RegimeLevel; score: number } {
  const s = (state || '').toLowerCase()
  if (s.includes('risk-on') || s.includes('risk_on') || s.includes('aggressive')) return { level: 'calm', score: 0 }
  if (s.includes('constructive') || deployment >= 0.9) return { level: 'normal', score: 1 }
  if (s.includes('cautious')) return { level: 'yellow', score: 2 }
  if (s.includes('defensive')) return { level: 'orange', score: 3 }
  if (s.includes('crisis') || s.includes('crash')) return { level: 'red', score: 4 }
  return { level: 'normal', score: 1 }
}

type ConvictionRowRaw = {
  symbol: string
  company_name: string | null
  sector: string | null
  tier: string
  conviction_score: string
  confidence_label: string
  date: Date
  ret_1m: string | null
}

type RegimeRowRaw = {
  date: Date
  regime_state: string
  deployment_multiplier: string
  india_vix: string | null
  pct_above_ema_200: string | null
  nifty500_above_ema_200: boolean | null
  ad_ratio: string | null
  dislocation_active: boolean | null
  realized_vol_5d_nifty500: string | null
}

type EtfTsmomRow = {
  ticker: string
  ret_12m: string | null
  date: Date
}

async function fetchLatestRegime(): Promise<RegimeRowRaw | null> {
  const rows = await sql<RegimeRowRaw[]>`
    SELECT
      date,
      regime_state,
      deployment_multiplier::text                AS deployment_multiplier,
      india_vix::text                            AS india_vix,
      pct_above_ema_200::text                    AS pct_above_ema_200,
      nifty500_above_ema_200,
      ad_ratio::text                             AS ad_ratio,
      dislocation_active,
      realized_vol_5d_nifty500::text             AS realized_vol_5d_nifty500
    FROM atlas.atlas_market_regime_daily
    ORDER BY date DESC
    LIMIT 1
  `
  return rows[0] ?? null
}

async function fetchTopConviction(limit: number): Promise<ConvictionRowRaw[]> {
  return sql<ConvictionRowRaw[]>`
    WITH latest AS (
      SELECT MAX(date) AS d FROM atlas.atlas_stock_conviction_daily
    )
    SELECT
      u.symbol,
      u.company_name,
      u.sector,
      c.tier,
      c.conviction_score::text   AS conviction_score,
      c.confidence_label,
      c.date,
      m.ret_1m::text             AS ret_1m
    FROM atlas.atlas_stock_conviction_daily c
    JOIN atlas.atlas_universe_stocks u USING (instrument_id)
    LEFT JOIN atlas.atlas_stock_metrics_daily m
      ON m.instrument_id = c.instrument_id AND m.date = c.date
    WHERE c.date = (SELECT d FROM latest)
      AND c.confidence_label IN ('industry_grade', 'baseline')
      AND u.in_nifty_500 = true
    ORDER BY c.conviction_score DESC NULLS LAST
    LIMIT ${limit}
  `
}

async function fetchSleeveTsmom(): Promise<EtfTsmomRow[]> {
  return sql<EtfTsmomRow[]>`
    WITH latest AS (
      SELECT ticker, MAX(date) AS d
        FROM atlas.atlas_etf_metrics_daily
       WHERE ticker IN ('GOLDBEES', 'LIQUIDBEES', 'GILT5YBEES', 'SETFGOLD')
       GROUP BY ticker
    )
    SELECT e.ticker, e.ret_12m::text AS ret_12m, e.date
      FROM atlas.atlas_etf_metrics_daily e
      JOIN latest l ON l.ticker = e.ticker AND l.d = e.date
     ORDER BY e.ticker
  `
}

function deriveHoldingsWeights(rows: ConvictionRowRaw[]): V6Holding[] {
  if (rows.length === 0) return []
  const scores = rows.map((r) => parseFloat(r.conviction_score))
  const sum = scores.reduce((a, b) => a + b, 0)
  return rows.map((r) => {
    const score = parseFloat(r.conviction_score)
    let weight = (score / sum) * 100
    if (weight > 5.0) weight = 5.0
    return {
      symbol: r.symbol,
      name: r.company_name ?? r.symbol,
      weight_pct: Number(weight.toFixed(2)),
      composite_score: Number(score.toFixed(2)),
      days_held: 0,
      pnl_since_entry_pct: r.ret_1m ? Number((parseFloat(r.ret_1m) * 100).toFixed(1)) : 0,
      confidence: mapConfidence(r.confidence_label),
      sector: r.sector ?? '—',
      hrp_cluster: r.sector ? `S-${r.sector.slice(0, 6).toUpperCase()}` : 'S-UNK',
    } satisfies V6Holding
  })
}

function buildRegimeSignals(r: RegimeRowRaw): V6RegimeSignal[] {
  const vix = r.india_vix ? parseFloat(r.india_vix) : null
  const breadth = r.pct_above_ema_200 ? parseFloat(r.pct_above_ema_200) * 100 : null
  const ad = r.ad_ratio ? parseFloat(r.ad_ratio) : null
  return [
    {
      name: 'Nifty 500 trend',
      firing: r.nifty500_above_ema_200 === false,
      reading: r.nifty500_above_ema_200 ? 'Above 200dEMA' : 'Below 200dEMA',
      threshold: 'close < 200dEMA',
    },
    {
      name: 'Breadth',
      firing: breadth !== null && breadth < 30,
      reading: breadth !== null ? `${breadth.toFixed(1)}% above 200dEMA` : '—',
      threshold: '< 30%',
    },
    {
      name: 'India VIX',
      firing: vix !== null && vix > 22,
      reading: vix !== null ? `${vix.toFixed(2)}` : '—',
      threshold: '> 22',
    },
    {
      name: 'A/D ratio',
      firing: ad !== null && ad < 0.40,
      reading: ad !== null ? ad.toFixed(2) : '—',
      threshold: '< 0.40',
    },
    {
      name: 'Dislocation',
      firing: r.dislocation_active === true,
      reading: r.dislocation_active ? 'Active' : 'Inactive',
      threshold: 'flag set',
    },
  ]
}

function buildSleeveLegs(rows: EtfTsmomRow[]): V6CrisisSleeveLeg[] {
  const NAMES: Record<string, string> = {
    GOLDBEES: 'Nippon India Gold BeES',
    LIQUIDBEES: 'Nippon India Liquid BeES',
    GILT5YBEES: 'Nippon India 5Y G-Sec BeES',
    SETFGOLD: 'SBI ETF Gold',
  }
  const scored = rows
    .map((r) => ({ ticker: r.ticker, ret: r.ret_12m ? parseFloat(r.ret_12m) : 0 }))
    .filter((r) => r.ret > 0)
  if (scored.length === 0) return []
  const priority = ['GOLDBEES', 'GILT5YBEES', 'LIQUIDBEES', 'SETFGOLD']
  const chosen = priority
    .map((t) => scored.find((r) => r.ticker === t))
    .filter((r): r is { ticker: string; ret: number } => Boolean(r))
    .slice(0, 2)
  if (chosen.length === 0) return []
  const chosenSum = chosen.reduce((s, r) => s + r.ret, 0)
  return chosen.map((r) => ({
    symbol: r.ticker,
    name: NAMES[r.ticker] ?? r.ticker,
    weight_pct: Number(((r.ret / chosenSum) * 100).toFixed(1)),
    tsmom_12m_return_pct: Number((r.ret * 100).toFixed(1)),
  }))
}

export async function getV6Book(): Promise<V6BookSnapshot> {
  const [regimeRow, convictionRows, sleeveRows] = await Promise.all([
    fetchLatestRegime(),
    fetchTopConviction(28),
    fetchSleeveTsmom(),
  ])
  const regimeState = regimeRow?.regime_state ?? 'Unknown'
  const deployment = regimeRow ? parseFloat(regimeRow.deployment_multiplier) : 1.0
  const { level, score } = mapRegime(regimeState, deployment)
  const holdings = deriveHoldingsWeights(convictionRows)
  const sleeveLegs = buildSleeveLegs(sleeveRows)
  const sleevePct = 5 + 2 * score
  const grossEquity = deployment * 100 - sleevePct
  const cashPct = Math.max(0, 100 - grossEquity - sleevePct)
  return {
    as_of: regimeRow ? regimeRow.date.toISOString().slice(0, 10) : new Date().toISOString().slice(0, 10),
    cagr_net_pct: null,
    vol_annualized_pct: regimeRow?.realized_vol_5d_nifty500
      ? Number((parseFloat(regimeRow.realized_vol_5d_nifty500) * Math.sqrt(252) * 100).toFixed(1))
      : null,
    max_drawdown_pct: null,
    sharpe_net: null,
    calmar: null,
    win_rate_pct: null,
    capacity_cr: null,
    gross_exposure_pct: Number((grossEquity + sleevePct).toFixed(1)),
    cash_pct: Number(cashPct.toFixed(1)),
    holdings,
    regime: {
      score,
      level,
      gross_multiplier: deployment,
      signals: regimeRow ? buildRegimeSignals(regimeRow) : [],
      raw_state: regimeState,
    },
    crisis_sleeve: {
      total_pct: Number(sleevePct.toFixed(1)),
      legs: sleeveLegs,
    },
    goal_post: {
      passes_all_constraints: null,
      constraints: [
        { name: 'Calmar', target: '≥ 1.0', actual: '—', pass: null },
        { name: 'Vol vs benchmark', target: '≤ 0.9× bench', actual: '—', pass: null },
        { name: 'MDD vs benchmark', target: '≤ 0.7× bench', actual: '—', pass: null },
        { name: 'Monthly win-rate', target: '≥ 50%', actual: '—', pass: null },
        { name: 'Alpha t-stat', target: '≥ 1.5', actual: '—', pass: null },
        { name: 'OOS-IC retention', target: '≥ 70%', actual: '—', pass: null },
        { name: 'Capacity', target: '≥ ₹1,500 cr', actual: '—', pass: null },
        { name: 'Turnover (annual)', target: '≤ 200%', actual: '—', pass: null },
        { name: 'DD compliance', target: '≥ 60% of OOS years', actual: '—', pass: null },
      ],
    },
    last_rebalance: { date: null, entered: [], exited: [] },
  }
}

export type V6BadgeStatus =
  | { state: 'IN_BOOK'; weight_pct: number; composite: number }
  | { state: 'TOP_PICK'; rank: number; composite: number }
  | { state: 'EXCLUDED'; reason: string }
  | { state: 'BENCH_HOLD'; composite: number }
  | { state: 'NOT_IN_UNIVERSE' }

export async function getV6BadgeStatus(symbol: string): Promise<V6BadgeStatus> {
  const rows = await sql<{ composite: string; rank: number; in_nifty_500: boolean }[]>`
    WITH latest AS (
      SELECT MAX(date) AS d FROM atlas.atlas_stock_conviction_daily
    ),
    ranked AS (
      SELECT
        u.symbol,
        u.in_nifty_500,
        c.conviction_score::text AS composite,
        ROW_NUMBER() OVER (ORDER BY c.conviction_score DESC) AS rank
      FROM atlas.atlas_stock_conviction_daily c
      JOIN atlas.atlas_universe_stocks u USING (instrument_id)
      WHERE c.date = (SELECT d FROM latest)
        AND c.confidence_label IN ('industry_grade', 'baseline')
    )
    SELECT composite, rank, in_nifty_500
      FROM ranked
     WHERE symbol = ${symbol.toUpperCase()}
     LIMIT 1
  `
  const r = rows[0]
  if (!r) {
    const inUni = await sql<{ in_nifty_500: boolean }[]>`
      SELECT in_nifty_500 FROM atlas.atlas_universe_stocks
       WHERE symbol = ${symbol.toUpperCase()} LIMIT 1
    `
    if (!inUni[0]) return { state: 'NOT_IN_UNIVERSE' }
    return { state: 'BENCH_HOLD', composite: 0 }
  }
  const composite = parseFloat(r.composite)
  if (r.rank <= 28) return { state: 'IN_BOOK', weight_pct: 100 / 28, composite }
  if (r.rank <= 50) return { state: 'TOP_PICK', rank: r.rank, composite }
  return { state: 'BENCH_HOLD', composite }
}
