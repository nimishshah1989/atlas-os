// src/lib/queries/v6.ts
// v0.1 mock query layer for the v6 trading model command center.
// Returns realistic deterministic mock data anchored to the v6 spec's expected
// values (CAGR 20-24%, MDD 22-28%, vol 13-15%, Sharpe 1.1-1.4, Calmar 0.8-1.1,
// win-rate 52-56%, capacity ₹1,500-2,000cr).
//
// Replace the implementations with real DB queries against atlas_v6_* tables
// once Plan 2 (backend trading engine) lands. Public shape stays stable.

export type ConfidenceBand = 'HIGH' | 'MED' | 'LOW'
export type RegimeLevel = 'calm' | 'normal' | 'yellow' | 'orange' | 'red' | 'crash'

export type V6Holding = {
  symbol: string
  name: string
  weight_pct: number          // 0..100
  composite_score: number     // approx -3.5..+3.5
  days_held: number
  pnl_since_entry_pct: number // signed
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
  tsmom_12m_return_pct: number  // signed
}

export type V6BookSnapshot = {
  as_of: string                 // ISO date
  cagr_net_pct: number
  vol_annualized_pct: number
  max_drawdown_pct: number
  sharpe_net: number
  calmar: number
  win_rate_pct: number
  capacity_cr: number
  gross_exposure_pct: number
  cash_pct: number
  holdings: V6Holding[]
  regime: {
    score: number              // 0..5
    level: RegimeLevel
    gross_multiplier: number
    signals: V6RegimeSignal[]
  }
  crisis_sleeve: {
    total_pct: number
    legs: V6CrisisSleeveLeg[]
  }
  goal_post: {
    passes_all_constraints: boolean
    constraints: {
      name: string
      target: string
      actual: string
      pass: boolean
    }[]
  }
  last_rebalance: {
    date: string
    entered: { symbol: string; weight_pct: number; reason: string }[]
    exited: { symbol: string; reason: string }[]
  }
}

// Mock book snapshot — deterministic, matches v0.1 spec expectations.
const MOCK_BOOK: V6BookSnapshot = {
  as_of: '2026-05-19',
  cagr_net_pct: 22.4,
  vol_annualized_pct: 14.1,
  max_drawdown_pct: 24.3,
  sharpe_net: 1.23,
  calmar: 0.92,
  win_rate_pct: 54,
  capacity_cr: 1820,
  gross_exposure_pct: 96.5,
  cash_pct: 3.5,
  regime: {
    score: 1,
    level: 'normal',
    gross_multiplier: 1.0,
    signals: [
      { name: 'Nifty 500 trend',  firing: false, reading: 'Above 200dMA (+4.2%)',  threshold: '< 200dMA' },
      { name: 'Breadth',          firing: false, reading: '58% above 200dMA',       threshold: '< 30%' },
      { name: 'VIX term',         firing: false, reading: '1m 13.4 / 3m 14.8',     threshold: '1m > 3m' },
      { name: 'FII flow (3w)',    firing: true,  reading: '-₹11,240 cr (3w cum)',  threshold: '< -₹10,000 cr' },
      { name: 'DXY 20d',          firing: false, reading: '+0.8σ',                  threshold: '> +2σ' },
    ],
  },
  crisis_sleeve: {
    total_pct: 7.0,
    legs: [
      { symbol: 'GOLDBEES',   name: 'Nippon India Gold BeES',    weight_pct: 4.2, tsmom_12m_return_pct: 22.7 },
      { symbol: 'LIQUIDBEES', name: 'Nippon India Liquid BeES',  weight_pct: 2.8, tsmom_12m_return_pct: 6.4 },
    ],
  },
  goal_post: {
    passes_all_constraints: true,
    constraints: [
      { name: 'Calmar',            target: '≥ 1.0',                  actual: '0.92',    pass: false },
      { name: 'Vol vs benchmark',  target: '≤ 0.9× bench (15.3%)',   actual: '14.1%',   pass: true },
      { name: 'MDD vs benchmark',  target: '≤ 0.7× bench (28.7%)',   actual: '24.3%',   pass: true },
      { name: 'Monthly win-rate',  target: '≥ 50%',                  actual: '54%',     pass: true },
      { name: 'Alpha t-stat',      target: '≥ 1.5',                  actual: '1.62',    pass: true },
      { name: 'OOS-IC retention',  target: '≥ 70%',                  actual: '78%',     pass: true },
      { name: 'Capacity',          target: '≥ ₹1,500 cr',            actual: '₹1,820cr',pass: true },
      { name: 'Turnover (annual)', target: '≤ 200%',                 actual: '167%',    pass: true },
      { name: 'DD compliance',     target: '≥ 60% of OOS years',     actual: '75%',     pass: true },
    ],
  },
  last_rebalance: {
    date: '2026-04-30',
    entered: [
      { symbol: 'BHARATFORG', weight_pct: 3.6, reason: 'residual_mom z=+2.1; CTS Stage 2' },
      { symbol: 'POLYCAB',    weight_pct: 3.2, reason: 'industry_rs z=+1.9; 52WH proximity 0.97' },
      { symbol: 'COFORGE',    weight_pct: 2.9, reason: 'mom_low_vol z=+1.8; quality_proxy z=+1.4' },
    ],
    exited: [
      { symbol: 'ZOMATO', reason: 'composite rolled out of top quintile (rank 58)' },
      { symbol: 'BAJFINANCE', reason: 'breached 200dMA for 2 sessions' },
    ],
  },
  holdings: [
    { symbol: 'RELIANCE',   name: 'Reliance Industries',   weight_pct: 4.8, composite_score: 1.92, days_held: 124, pnl_since_entry_pct: 12.4, confidence: 'HIGH', sector: 'Energy',     hrp_cluster: 'C1' },
    { symbol: 'TCS',        name: 'Tata Consultancy',      weight_pct: 4.5, composite_score: 1.74, days_held: 98,  pnl_since_entry_pct: 8.1,  confidence: 'HIGH', sector: 'IT',         hrp_cluster: 'C2' },
    { symbol: 'INFY',       name: 'Infosys',               weight_pct: 4.1, composite_score: 1.68, days_held: 82,  pnl_since_entry_pct: 6.9,  confidence: 'HIGH', sector: 'IT',         hrp_cluster: 'C2' },
    { symbol: 'HDFCBANK',   name: 'HDFC Bank',             weight_pct: 4.0, composite_score: 1.55, days_held: 156, pnl_since_entry_pct: 14.8, confidence: 'HIGH', sector: 'Financials', hrp_cluster: 'C3' },
    { symbol: 'ICICIBANK',  name: 'ICICI Bank',            weight_pct: 3.8, composite_score: 1.49, days_held: 89,  pnl_since_entry_pct: 9.2,  confidence: 'HIGH', sector: 'Financials', hrp_cluster: 'C3' },
    { symbol: 'BHARTIARTL', name: 'Bharti Airtel',         weight_pct: 3.7, composite_score: 1.43, days_held: 71,  pnl_since_entry_pct: 11.5, confidence: 'HIGH', sector: 'Telecom',    hrp_cluster: 'C4' },
    { symbol: 'LT',         name: 'Larsen & Toubro',       weight_pct: 3.6, composite_score: 1.41, days_held: 102, pnl_since_entry_pct: 7.4,  confidence: 'HIGH', sector: 'Industrials',hrp_cluster: 'C5' },
    { symbol: 'BHARATFORG', name: 'Bharat Forge',          weight_pct: 3.6, composite_score: 2.10, days_held: 8,   pnl_since_entry_pct: 2.3,  confidence: 'HIGH', sector: 'Industrials',hrp_cluster: 'C5' },
    { symbol: 'POLYCAB',    name: 'Polycab India',         weight_pct: 3.2, composite_score: 1.88, days_held: 8,   pnl_since_entry_pct: 1.9,  confidence: 'HIGH', sector: 'Industrials',hrp_cluster: 'C5' },
    { symbol: 'TITAN',      name: 'Titan Company',         weight_pct: 3.2, composite_score: 1.35, days_held: 144, pnl_since_entry_pct: 5.6,  confidence: 'HIGH', sector: 'Consumer',   hrp_cluster: 'C6' },
    { symbol: 'ASIANPAINT', name: 'Asian Paints',          weight_pct: 3.0, composite_score: 1.21, days_held: 67,  pnl_since_entry_pct: 4.1,  confidence: 'MED',  sector: 'Materials',  hrp_cluster: 'C7' },
    { symbol: 'NESTLEIND',  name: 'Nestle India',          weight_pct: 3.0, composite_score: 1.17, days_held: 132, pnl_since_entry_pct: 3.8,  confidence: 'MED',  sector: 'Consumer',   hrp_cluster: 'C6' },
    { symbol: 'COFORGE',    name: 'Coforge',               weight_pct: 2.9, composite_score: 1.82, days_held: 8,   pnl_since_entry_pct: 2.7,  confidence: 'HIGH', sector: 'IT',         hrp_cluster: 'C2' },
    { symbol: 'ULTRACEMCO', name: 'UltraTech Cement',      weight_pct: 2.8, composite_score: 1.09, days_held: 78,  pnl_since_entry_pct: 6.2,  confidence: 'MED',  sector: 'Materials',  hrp_cluster: 'C7' },
    { symbol: 'TATAMOTORS', name: 'Tata Motors',           weight_pct: 2.7, composite_score: 1.05, days_held: 41,  pnl_since_entry_pct: 4.4,  confidence: 'MED',  sector: 'Auto',       hrp_cluster: 'C8' },
    { symbol: 'HCLTECH',    name: 'HCL Technologies',      weight_pct: 2.7, composite_score: 1.02, days_held: 105, pnl_since_entry_pct: 5.9,  confidence: 'MED',  sector: 'IT',         hrp_cluster: 'C2' },
    { symbol: 'MARUTI',     name: 'Maruti Suzuki',         weight_pct: 2.6, composite_score: 0.98, days_held: 53,  pnl_since_entry_pct: 3.5,  confidence: 'MED',  sector: 'Auto',       hrp_cluster: 'C8' },
    { symbol: 'AXISBANK',   name: 'Axis Bank',             weight_pct: 2.5, composite_score: 0.94, days_held: 47,  pnl_since_entry_pct: 2.8,  confidence: 'MED',  sector: 'Financials', hrp_cluster: 'C3' },
    { symbol: 'KOTAKBANK',  name: 'Kotak Mahindra Bank',   weight_pct: 2.5, composite_score: 0.92, days_held: 91,  pnl_since_entry_pct: 4.7,  confidence: 'MED',  sector: 'Financials', hrp_cluster: 'C3' },
    { symbol: 'TECHM',      name: 'Tech Mahindra',         weight_pct: 2.4, composite_score: 0.89, days_held: 62,  pnl_since_entry_pct: 4.2,  confidence: 'MED',  sector: 'IT',         hrp_cluster: 'C2' },
    { symbol: 'WIPRO',      name: 'Wipro',                 weight_pct: 2.3, composite_score: 0.87, days_held: 38,  pnl_since_entry_pct: 2.1,  confidence: 'MED',  sector: 'IT',         hrp_cluster: 'C2' },
    { symbol: 'DRREDDY',    name: 'Dr Reddys Labs',        weight_pct: 2.2, composite_score: 0.81, days_held: 71,  pnl_since_entry_pct: 3.6,  confidence: 'MED',  sector: 'Pharma',     hrp_cluster: 'C9' },
    { symbol: 'CIPLA',      name: 'Cipla',                 weight_pct: 2.1, composite_score: 0.79, days_held: 64,  pnl_since_entry_pct: 3.2,  confidence: 'MED',  sector: 'Pharma',     hrp_cluster: 'C9' },
    { symbol: 'SUNPHARMA',  name: 'Sun Pharmaceutical',    weight_pct: 2.1, composite_score: 0.76, days_held: 88,  pnl_since_entry_pct: 4.3,  confidence: 'MED',  sector: 'Pharma',     hrp_cluster: 'C9' },
    { symbol: 'HINDUNILVR', name: 'Hindustan Unilever',    weight_pct: 2.0, composite_score: 0.73, days_held: 117, pnl_since_entry_pct: 3.1,  confidence: 'MED',  sector: 'Consumer',   hrp_cluster: 'C6' },
    { symbol: 'ITC',        name: 'ITC',                   weight_pct: 2.0, composite_score: 0.71, days_held: 109, pnl_since_entry_pct: 5.1,  confidence: 'MED',  sector: 'Consumer',   hrp_cluster: 'C6' },
    { symbol: 'NTPC',       name: 'NTPC',                  weight_pct: 1.9, composite_score: 0.69, days_held: 75,  pnl_since_entry_pct: 4.8,  confidence: 'LOW',  sector: 'Utilities',  hrp_cluster: 'C10'},
    { symbol: 'POWERGRID',  name: 'Power Grid Corp',       weight_pct: 1.8, composite_score: 0.67, days_held: 81,  pnl_since_entry_pct: 4.2,  confidence: 'LOW',  sector: 'Utilities',  hrp_cluster: 'C10'},
  ],
}

export async function getV6Book(): Promise<V6BookSnapshot> {
  // TODO(plan-2): wire to atlas.atlas_v6_recommendations_daily + atlas_v6_strategy_runs
  return MOCK_BOOK
}

export type V6BadgeStatus =
  | { state: 'IN_BOOK'; weight_pct: number; composite: number }
  | { state: 'TOP_PICK'; rank: number; composite: number }
  | { state: 'EXCLUDED'; reason: string }
  | { state: 'BENCH_HOLD'; composite: number }
  | { state: 'NOT_IN_UNIVERSE' }

export async function getV6BadgeStatus(symbol: string): Promise<V6BadgeStatus> {
  // TODO(plan-2): wire to atlas.atlas_v6_recommendations_daily + atlas_v6_exclusions_log
  const book = MOCK_BOOK.holdings.find((h) => h.symbol === symbol)
  if (book) {
    return { state: 'IN_BOOK', weight_pct: book.weight_pct, composite: book.composite_score }
  }
  // Hardcoded mock exclusions / top-picks for demo
  const exclusions: Record<string, string> = {
    ADANIENT: 'auditor not in top-10 (Shah Dhandharia & Co)',
    ADANIPORTS: 'issuer-group cap (Adani >5%)',
    DHFL: 'promoter pledge 62% (>30% threshold)',
    SUZLON: 'F&O ban list',
  }
  if (exclusions[symbol]) {
    return { state: 'EXCLUDED', reason: exclusions[symbol] }
  }
  const topPicks: Record<string, { rank: number; composite: number }> = {
    PERSISTENT: { rank: 28, composite: 1.62 },
    TATATECH: { rank: 31, composite: 1.55 },
  }
  if (topPicks[symbol]) {
    return { state: 'TOP_PICK', rank: topPicks[symbol].rank, composite: topPicks[symbol].composite }
  }
  return { state: 'BENCH_HOLD', composite: 0.21 }
}
