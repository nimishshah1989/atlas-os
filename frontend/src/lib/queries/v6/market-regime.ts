// frontend/src/lib/queries/v6/market-regime.ts
//
// Reads the single wide row from atlas.mv_market_regime_landing.
// JSONB columns are returned by postgres-js as already-parsed JS values,
// so this module only does:
//   1. numeric::text → number coercion for Decimal columns
//   2. NULL JSONB → [] or {} fallback
//   3. typed-shape tagging via TS interfaces
//
// Contract for JSONB scales (locked with the MV definition):
//   - next_state_probs        — integer percent (e.g. 56 = 56%)
//   - deployment_defaults     — fraction        (e.g. 0.6  = 60%)
//   - deployment_multiplier   — fraction        (column on the table)
//   - twelve_week_journey[].breadth_pct — fraction
//
// MV refreshed nightly via pg_cron (Phase D).

import 'server-only'
import sql from '@/lib/db'

export type RegimeJourneyWeek = {
  week_start: string
  regime_state: string
  breadth_pct: number | null
  india_vix: number | null
}

export type Regime60dSegment = {
  state: string
  days: number
}

export type CellFavored = {
  cell_id: string
  cap_tier: string
  tenure: string
  action: string
  confidence: 'HIGH' | 'MED' | 'LOW' | string
  display_name: string
  explain_text: string | null
  predicted_excess: number | null
  stocks_firing_today: number
}

export type ConvictionStock = {
  symbol: string
  company_name: string | null
  sector: string | null
  cap_tier: string | null
  action: string
  cell_name: string | null
  confidence: number | null
  predicted_excess: number | null
  is_new_today: boolean
}

export type ConvictionFund = {
  scheme_code: string
  fund_name: string
  category: string | null
  plan_type: string | null
  composite: number | null
  quartile: string | null
  recommendation: string | null
  is_atlas_leader: boolean
}

export type ConvictionEtf = {
  ticker: string
  etf_name: string
  category: string | null
  underlying_sector: string | null
  action: string
  cell_name: string | null
  composite: number | null
  predicted_excess: number | null
}

export type MarketRegimePage = {
  as_of_date: string
  regime_state: string
  deployment_multiplier: number | null
  days_in_regime: number
  entered_date: string | null
  prior_regime_state: string | null
  typical_length_days: number | null
  liquid_bees_yield_pct: number | null
  refreshed_at: string | null
  next_state_probs: Record<string, number>
  recent_60d_segments: Regime60dSegment[]
  twelve_week_journey: RegimeJourneyWeek[]
  cells_favored: CellFavored[]
  conviction_stocks: ConvictionStock[]
  conviction_funds: ConvictionFund[]
  conviction_etfs: ConvictionEtf[]
  deployment_defaults: Record<string, number>
}

type Row = {
  as_of_date: string
  regime_state: string
  deployment_multiplier: string | null
  days_in_regime: number | string
  entered_date: string | null
  prior_regime_state: string | null
  typical_length_days: number | null
  liquid_bees_yield_pct: string | null
  refreshed_at: string | null
  next_state_probs: Record<string, number> | null
  recent_60d_segments: Regime60dSegment[] | null
  twelve_week_journey: RegimeJourneyWeek[] | null
  cells_favored: CellFavored[] | null
  conviction_stocks: ConvictionStock[] | null
  conviction_funds: ConvictionFund[] | null
  conviction_etfs: ConvictionEtf[] | null
  deployment_defaults: Record<string, number> | null
}

function toNumber(s: string | number | null): number | null {
  if (s == null) return null
  const n = typeof s === 'number' ? s : Number(s)
  return Number.isFinite(n) ? n : null
}

export async function getMarketRegimePage(): Promise<MarketRegimePage | null> {
  const rows = await sql<Row[]>`
    SELECT
      as_of_date::text             AS as_of_date,
      regime_state,
      deployment_multiplier::text  AS deployment_multiplier,
      days_in_regime,
      entered_date::text           AS entered_date,
      prior_regime_state,
      typical_length_days,
      liquid_bees_yield_pct::text  AS liquid_bees_yield_pct,
      refreshed_at::text           AS refreshed_at,
      next_state_probs,
      recent_60d_segments,
      twelve_week_journey,
      cells_favored,
      conviction_stocks,
      conviction_funds,
      conviction_etfs,
      deployment_defaults
    FROM atlas.mv_market_regime_landing
    LIMIT 1
  `

  const r = rows[0]
  if (!r) return null

  return {
    as_of_date: r.as_of_date,
    regime_state: r.regime_state,
    deployment_multiplier: toNumber(r.deployment_multiplier),
    days_in_regime: typeof r.days_in_regime === 'string'
      ? Number(r.days_in_regime)
      : r.days_in_regime,
    entered_date: r.entered_date,
    prior_regime_state: r.prior_regime_state,
    typical_length_days: r.typical_length_days,
    liquid_bees_yield_pct: toNumber(r.liquid_bees_yield_pct),
    refreshed_at: r.refreshed_at,
    next_state_probs: r.next_state_probs ?? {},
    recent_60d_segments: r.recent_60d_segments ?? [],
    twelve_week_journey: r.twelve_week_journey ?? [],
    cells_favored: r.cells_favored ?? [],
    conviction_stocks: r.conviction_stocks ?? [],
    conviction_funds: r.conviction_funds ?? [],
    conviction_etfs: r.conviction_etfs ?? [],
    deployment_defaults: r.deployment_defaults ?? {},
  }
}
