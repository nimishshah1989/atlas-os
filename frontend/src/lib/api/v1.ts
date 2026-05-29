// frontend/src/lib/api/v1.ts
//
// /v1 API client for Atlas v6 endpoints. Graceful-fallback pattern:
//   1. Try the real endpoint.
//   2. On 404 / network error → fall back to demo fixtures (no throw).
//   3. The returned `source` field tells the UI whether to render the
//      <DataSourceBanner> as "Live API" or "Demo data (backend not yet wired)".
//
// All requests are server-side only. Add `cache: 'no-store'` so Next.js
// doesn't memoize stale fixtures.

import { getDemoCellDefinitions, getDemoCellDefinition } from './demo-cells'
import { getDemoStocks } from './demo-stocks'
import { getDemoEtfs, getDemoFunds, getDemoSectors, getDemoRegime } from './demo-misc'

const API_BASE = process.env.ATLAS_V1_API_BASE ?? 'http://localhost:8002'

export type DataSource = 'live' | 'demo'

export interface ApiEnvelope<T> {
  data: T
  meta: {
    data_as_of: string
    fetched_at: string
    source: string
    next_cursor?: string | null
    total?: number
  }
  /** Local-only: which path was taken. */
  source_kind: DataSource
}

// ────────────────────────────────────────────────────────────────────────────
// Types
// ────────────────────────────────────────────────────────────────────────────

export type Tier = 'Large' | 'Mid' | 'Small'
export type Tenure = '1m' | '3m' | '6m' | '12m'
export type Direction = 'POSITIVE' | 'NEGATIVE'
export type Verdict = 'POSITIVE' | 'NEGATIVE' | 'NEUTRAL'

export interface ConvictionVerdict {
  direction: Verdict
  ic: number | null
  rule_count: number
  top_rule_id: string | null
}

export type ConvictionTape = Record<Tenure, ConvictionVerdict>

export interface ScreenStock {
  iid: string
  symbol: string
  company_name: string | null
  sector: string | null
  tier: Tier
  mcap_inr: number | null
  rs_state: string | null
  stage: string | null
  conviction_tape: ConvictionTape
  ret_1m: number | null
  ret_3m: number | null
  ret_6m: number | null
  ret_12m: number | null
  rs_pctile_3m: number | null
  is_investable: boolean
}

export interface ScreenEtf {
  iid: string
  ticker: string
  name: string | null
  category: string | null
  aum_inr: number | null
  conviction_tape: ConvictionTape
  ret_1m: number | null
  ret_3m: number | null
  ret_6m: number | null
  ret_12m: number | null
  rs_state: string | null
}

export type StyleSize = 'Large' | 'Mid' | 'Small'
export type StyleAxis = 'Value' | 'Blend' | 'Growth'

export interface ScreenFund {
  iid: string
  code: string
  name: string
  category: string | null
  aum_inr: number | null
  style_box: { size: StyleSize; style: StyleAxis } | null
  conviction_tape: ConvictionTape | null
  ret_1m: number | null
  ret_3m: number | null
  ret_6m: number | null
  ret_12m: number | null
  rs_state: string | null
}

export interface ScreenSector {
  sector_iid: string
  sector_name: string
  rank: number
  rank_change: number
  days_in_state: number
  sector_state: string
  breadth_pct_stage_2: number | null
  vol_regime: string
  rs_pct_cross_sector: number | null
  ret_1m: number | null
  ret_3m: number | null
  rrg_quadrant: string | null
  cells_favored_today: string[]
}

export interface MarketRegime {
  regime_state: string
  deployment_pct: number
  pct_above_ema_50: number | null
  net_stage_2_5d: number | null
  participation: number | null
  history: { date: string; pct_above_ema_50: number | null; regime_state: string }[]
  cells_favored: { cell_id: string; ic_in_regime: number }[]
}

export interface CellRule {
  rule_id: string
  name: string
  archetype: string
  eli5: string
  predicates_natural: string[]
  predicates_dsl: Record<string, unknown>
  ic_mean: number | null
  ic_ir: number | null
  q_value: number | null
  fric_adj_excess_mean_ann: number | null
  gate_pass_count: number
  gate_total: number
  per_window_stability: number[]
  population_today: number
  population_today_iids: string[]
}

export interface CellDefinition {
  cell_id: string
  tier: Tier
  tenure: Tenure
  direction: Direction
  n_candidates: number
  n_gate_pass: number
  grade: 'green' | 'amber' | 'red' | 'unknown'
  ship_or_park: string
  reason: string
  disclaimers_applicable: string[]
  best_rule_id: string | null
  best_rule_ic: number | null
  best_rule_fric_adj_ann: number | null
  best_archetype: string | null
  rules: CellRule[]
}

// ────────────────────────────────────────────────────────────────────────────
// Internal: tryFetch
// ────────────────────────────────────────────────────────────────────────────

async function tryFetch<T>(path: string): Promise<{ data: T; meta: ApiEnvelope<T>['meta'] } | null> {
  try {
    const res = await fetch(`${API_BASE}${path}`, {
      cache: 'no-store',
      headers: { 'accept': 'application/json' },
    })
    if (!res.ok) return null
    const json = (await res.json()) as { data: T; meta: ApiEnvelope<T>['meta'] }
    return json
  } catch {
    return null
  }
}

function nowEnvelope(source: string): ApiEnvelope<unknown>['meta'] {
  const now = new Date().toISOString()
  return { data_as_of: now, fetched_at: now, source }
}

// ────────────────────────────────────────────────────────────────────────────
// Public API — every fn falls back gracefully
// ────────────────────────────────────────────────────────────────────────────

export async function getScreenStocks(params: {
  tier?: Tier
  sector?: string
  limit?: number
} = {}): Promise<ApiEnvelope<ScreenStock[]>> {
  const qs = new URLSearchParams()
  if (params.tier) qs.set('tier', params.tier)
  if (params.sector) qs.set('sector', params.sector)
  if (params.limit) qs.set('limit', String(params.limit))
  const path = `/v1/screen.stocks${qs.toString() ? `?${qs}` : ''}`
  const live = await tryFetch<ScreenStock[]>(path)
  if (live) {
    return { data: live.data, meta: live.meta, source_kind: 'live' }
  }
  const demo = getDemoStocks(params)
  return {
    data: demo,
    meta: { ...nowEnvelope('demo_fixture'), total: demo.length },
    source_kind: 'demo',
  }
}

export async function getScreenEtfs(): Promise<ApiEnvelope<ScreenEtf[]>> {
  const live = await tryFetch<ScreenEtf[]>('/v1/screen.etfs')
  if (live) return { data: live.data, meta: live.meta, source_kind: 'live' }
  const demo = getDemoEtfs()
  return { data: demo, meta: { ...nowEnvelope('demo_fixture'), total: demo.length }, source_kind: 'demo' }
}

export async function getScreenFunds(): Promise<ApiEnvelope<ScreenFund[]>> {
  const live = await tryFetch<ScreenFund[]>('/v1/screen.funds')
  if (live) return { data: live.data, meta: live.meta, source_kind: 'live' }
  const demo = getDemoFunds()
  return { data: demo, meta: { ...nowEnvelope('demo_fixture'), total: demo.length }, source_kind: 'demo' }
}

export async function getScreenSectors(): Promise<ApiEnvelope<ScreenSector[]>> {
  const live = await tryFetch<ScreenSector[]>('/v1/screen.sectors')
  if (live) return { data: live.data, meta: live.meta, source_kind: 'live' }
  const demo = getDemoSectors()
  return { data: demo, meta: { ...nowEnvelope('demo_fixture'), total: demo.length }, source_kind: 'demo' }
}

export async function getMarketRegime(): Promise<ApiEnvelope<MarketRegime>> {
  const live = await tryFetch<MarketRegime>('/v1/market.regime')
  if (live) return { data: live.data, meta: live.meta, source_kind: 'live' }
  const demo = getDemoRegime()
  return { data: demo, meta: nowEnvelope('demo_fixture'), source_kind: 'demo' }
}

export async function getCellDefinitions(): Promise<ApiEnvelope<CellDefinition[]>> {
  const live = await tryFetch<CellDefinition[]>('/v1/cell.definitions')
  if (live) return { data: live.data, meta: live.meta, source_kind: 'live' }
  const demo = getDemoCellDefinitions()
  return { data: demo, meta: { ...nowEnvelope('demo_fixture'), total: demo.length }, source_kind: 'demo' }
}

export async function getCellDefinition(cellId: string): Promise<ApiEnvelope<CellDefinition | null>> {
  const live = await tryFetch<CellDefinition>(`/v1/cell.definitions?cell=${encodeURIComponent(cellId)}`)
  if (live) return { data: live.data, meta: live.meta, source_kind: 'live' }
  const demo = getDemoCellDefinition(cellId)
  return { data: demo, meta: nowEnvelope('demo_fixture'), source_kind: 'demo' }
}

export async function getInstrument(iid: string): Promise<ApiEnvelope<ScreenStock | null>> {
  const live = await tryFetch<ScreenStock>(`/v1/instrument/${encodeURIComponent(iid)}`)
  if (live) return { data: live.data, meta: live.meta, source_kind: 'live' }
  // Demo: find in stocks fixture.
  const stocks = getDemoStocks({})
  const found = stocks.find(s => s.iid === iid || s.symbol === iid) ?? null
  return { data: found, meta: nowEnvelope('demo_fixture'), source_kind: 'demo' }
}

// ────────────────────────────────────────────────────────────────────────────
// TV metrics (TV-05)
// ────────────────────────────────────────────────────────────────────────────

/**
 * All Decimal-serialized numeric fields arrive as strings from the backend.
 * Do NOT convert to float — pass strings to components and let them render.
 * is_stale is computed by the backend (>2 days since fetch).
 */
export interface TVMetricsRow {
  symbol: string
  tv_recommend_label: string | null
  recommend_all: string | null
  recommend_ma: string | null
  recommend_other: string | null
  rsi_14: string | null
  macd_macd: string | null
  ema_20: string | null
  ema_50: string | null
  ema_200: string | null
  atr_14: string | null
  price: string | null
  high_52w: string | null
  low_52w: string | null
  fetched_at: string | null
  is_stale: boolean
  // TV-fundamentals (migration 118 — may be null until backend deployed to EC2)
  pe_ttm: number | null
  ps_current: number | null
  pb_fbs: number | null
  debt_to_equity: number | null
  roe: number | null
}

/**
 * Fetch TV screener metrics for a single NSE symbol.
 * Returns null on 404 (symbol not in tv_metrics table) or network failure.
 * No demo fallback — graceful null is the right empty state.
 */
export async function getTVMetrics(symbol: string): Promise<TVMetricsRow | null> {
  const live = await tryFetch<TVMetricsRow>(`/v1/tv/metrics/${encodeURIComponent(symbol)}`)
  if (!live) return null
  // The backend wraps data + meta; is_stale lives in meta.
  const row = live.data
  const isStale = (live.meta as unknown as { is_stale?: boolean }).is_stale ?? false
  return { ...row, is_stale: isStale }
}
