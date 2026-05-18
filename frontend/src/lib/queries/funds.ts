import 'server-only'
import sql from '@/lib/db'

export type FundRow = {
  // Identity
  mstar_id: string
  scheme_name: string
  amc: string
  category_name: string
  broad_category: string
  data_as_of: string | null
  // Metrics (all ::text casts → string | null)
  ret_1m: string | null
  ret_3m: string | null
  ret_6m: string | null
  ret_12m: string | null
  rs_1m_category: string | null
  rs_3m_category: string | null
  rs_6m_category: string | null
  rs_pctile_1m: string | null
  rs_pctile_3m: string | null
  rs_pctile_6m: string | null
  realized_vol_63: string | null
  drawdown_ratio_252: string | null
  nav_date: Date | null
  // States
  nav_state: string | null
  composition_state: string | null
  holdings_state: string | null
  // Decisions
  recommendation: string | null
  weeks_in_current_state: string | null
  // Phase 7: gate columns will be removed in Phase 8 (page-level cleanup).
  performance_gate: boolean | null
  sectors_gate: boolean | null
  stocks_gate: boolean | null
  market_gate: boolean | null
  entry_trigger: boolean | null
  exit_trigger: boolean | null
  reduce_trigger: boolean | null
  // AUM
  aum_cr: string | null
  aum_as_of: string | null
  // Lens (LEFT JOIN — all nullable)
  aligned_aum_pct: string | null
  avoid_aum_pct: string | null
  neutral_aum_pct: string | null   // computed in SQL
  strong_aum_pct: string | null
  weak_aum_pct: string | null
  unknown_aum_pct: string | null   // computed in SQL
  lens_as_of_date: Date | null
}

export type FundMasterRow = {
  mstar_id: string
  scheme_name: string
  amc: string
  category_name: string
  broad_category: string
  inception_date: Date | null
  data_as_of: string | null
  aum_cr: string | null
  aum_as_of: string | null
  nav_state: string | null
  nav_state_as_of: Date | null
  composition_state: string | null
  composition_as_of: Date | null
  holdings_state: string | null
  holdings_as_of: Date | null
  recommendation: string | null
  weeks_in_current_state: string | null
  // Phase 7: gate columns will be removed in Phase 8 (page-level cleanup).
  performance_gate: boolean | null
  sectors_gate: boolean | null
  stocks_gate: boolean | null
  market_gate: boolean | null
  entry_trigger: boolean | null
  exit_trigger: boolean | null
  reduce_trigger: boolean | null
  add_trigger: boolean | null
}

export type FundMetricHistoryRow = {
  nav_date: Date
  ret_1m: string | null
  ret_3m: string | null
  ret_6m: string | null
  ret_12m: string | null
  rs_pctile_1m: string | null
  rs_pctile_3m: string | null
  rs_pctile_6m: string | null
  rs_1m_category: string | null
  rs_3m_category: string | null
  rs_6m_category: string | null
  realized_vol_63: string | null
  drawdown_ratio_252: string | null
}

export type FundLensRow = {
  aligned_aum_pct: string | null
  avoid_aum_pct: string | null
  neutral_aum_pct: string | null
  strong_aum_pct: string | null
  weak_aum_pct: string | null
  unknown_aum_pct: string | null
  sector_concentration: string | null
  holdings_concentration: string | null
  last_disclosed_date: Date | null
  as_of_date: Date | null
}

export type FundDecisionRow = {
  date: Date
  recommendation: string | null
  entry_trigger: boolean | null
  exit_trigger: boolean | null
  reduce_trigger: boolean | null
  add_trigger: boolean | null
  performance_gate: boolean | null
  sectors_gate: boolean | null
  stocks_gate: boolean | null
  market_gate: boolean | null
  weeks_in_current_state: string | null
}

// LEFT JOINs on metrics/states/decisions so all universe funds appear even if not yet computed.
// lens aum_pct values are stored as fractions (0-1); multiply by 100 for the LensBar component.
// Phase 7: rewired to atlas_fund_signal_unified.
// nav_state is retained via the view's LEFT JOIN to atlas_fund_states_daily.
// Gate columns (performance_gate, sectors_gate, stocks_gate, market_gate) return TRUE.
// entry_trigger / exit_trigger / reduce_trigger return NULL pending Phase 8 removal.
export async function getAllFunds(): Promise<FundRow[]> {
  return sql<FundRow[]>`
    WITH latest AS (
      SELECT
        (SELECT MAX(date)     FROM atlas.atlas_fund_signal_unified)    AS states_date,
        (SELECT MAX(as_of_date) FROM atlas.atlas_fund_lens_monthly)    AS lens_date
    )
    SELECT
      uf.mstar_id, uf.scheme_name, uf.amc, uf.category_name, uf.broad_category,
      fm.nav_date::text AS data_as_of,
      uf.aum_cr::text AS aum_cr, uf.aum_as_of::text AS aum_as_of,
      fm.ret_1m::text AS ret_1m, fm.ret_3m::text AS ret_3m,
      fm.ret_6m::text AS ret_6m, fm.ret_12m::text AS ret_12m,
      fm.rs_1m_category::text AS rs_1m_category,
      fm.rs_3m_category::text AS rs_3m_category,
      fm.rs_6m_category::text AS rs_6m_category,
      fm.rs_pctile_1m::text AS rs_pctile_1m,
      fm.rs_pctile_3m::text AS rs_pctile_3m,
      fm.rs_pctile_6m::text AS rs_pctile_6m,
      fm.realized_vol_63::text AS realized_vol_63,
      fm.drawdown_ratio_252::text AS drawdown_ratio_252,
      fm.nav_date,
      fu.nav_state, fu.composition_state, fu.holdings_state,
      fu.recommendation,
      NULL::text AS weeks_in_current_state,
      -- Phase 7: gate columns will be removed in Phase 8 (page-level cleanup).
      TRUE AS performance_gate,
      TRUE AS sectors_gate,
      TRUE AS stocks_gate,
      TRUE AS market_gate,
      NULL::boolean AS entry_trigger,
      NULL::boolean AS exit_trigger,
      NULL::boolean AS reduce_trigger,
      (fl.aligned_aum_pct * 100)::text AS aligned_aum_pct,
      (fl.avoid_aum_pct   * 100)::text AS avoid_aum_pct,
      GREATEST(0, 100 - COALESCE(fl.aligned_aum_pct * 100, 0) - COALESCE(fl.avoid_aum_pct * 100, 0))::text AS neutral_aum_pct,
      (fl.strong_aum_pct * 100)::text AS strong_aum_pct,
      (fl.weak_aum_pct   * 100)::text AS weak_aum_pct,
      GREATEST(0, 100 - COALESCE(fl.strong_aum_pct * 100, 0) - COALESCE(fl.weak_aum_pct * 100, 0))::text AS unknown_aum_pct,
      fl.as_of_date AS lens_as_of_date
    FROM atlas.atlas_universe_funds uf
    LEFT JOIN LATERAL (
      SELECT * FROM atlas.atlas_fund_metrics_daily
      WHERE mstar_id = uf.mstar_id
      ORDER BY nav_date DESC LIMIT 1
    ) fm ON TRUE
    LEFT JOIN atlas.atlas_fund_signal_unified fu
      ON fu.mstar_id = uf.mstar_id AND fu.date = (SELECT states_date FROM latest)
    LEFT JOIN atlas.atlas_fund_lens_monthly fl
      ON fl.mstar_id = uf.mstar_id AND fl.as_of_date = (SELECT lens_date FROM latest)
    WHERE uf.plan_type = 'Regular'
    ORDER BY fm.rs_pctile_3m DESC NULLS LAST
  `
}

// Phase 7: rewired to atlas_fund_signal_unified.
// nav_state + nav_state_as_of retained via view LEFT JOIN to atlas_fund_states_daily.
// composition_as_of / holdings_as_of are not in the unified view; return NULL.
// Gate columns return TRUE; triggers return NULL.
export async function getFundMaster(mstar_id: string): Promise<FundMasterRow | null> {
  const rows = await sql<FundMasterRow[]>`
    SELECT
      uf.mstar_id, uf.scheme_name, uf.amc, uf.category_name, uf.broad_category,
      uf.inception_date,
      (SELECT MAX(nav_date)::text FROM atlas.atlas_fund_metrics_daily WHERE mstar_id = ${mstar_id}) AS data_as_of,
      uf.aum_cr::text AS aum_cr, uf.aum_as_of::text AS aum_as_of,
      fu.nav_state, fu.nav_state_as_of,
      fu.composition_state,
      NULL::date AS composition_as_of,
      fu.holdings_state,
      NULL::date AS holdings_as_of,
      fu.recommendation,
      NULL::text AS weeks_in_current_state,
      -- Phase 7: gate columns will be removed in Phase 8 (page-level cleanup).
      TRUE AS performance_gate,
      TRUE AS sectors_gate,
      TRUE AS stocks_gate,
      TRUE AS market_gate,
      NULL::boolean AS entry_trigger,
      NULL::boolean AS exit_trigger,
      NULL::boolean AS reduce_trigger,
      NULL::boolean AS add_trigger
    FROM atlas.atlas_universe_funds uf
    LEFT JOIN atlas.atlas_fund_signal_unified fu
      ON fu.mstar_id = uf.mstar_id
      AND fu.date = (SELECT MAX(date) FROM atlas.atlas_fund_signal_unified)
    WHERE uf.mstar_id = ${mstar_id}
      AND uf.plan_type = 'Regular'
    LIMIT 1
  `
  return rows[0] ?? null
}

export async function getFundMetricHistory(
  mstar_id: string,
  days = 180,
): Promise<FundMetricHistoryRow[]> {
  if (!Number.isInteger(days) || days < 1 || days > 3650) {
    throw new Error(`days must be an integer between 1 and 3650, got: ${days}`)
  }
  return sql<FundMetricHistoryRow[]>`
    SELECT
      nav_date,
      ret_1m::text, ret_3m::text, ret_6m::text, ret_12m::text,
      rs_pctile_1m::text AS rs_pctile_1m,
      rs_pctile_3m::text AS rs_pctile_3m,
      rs_pctile_6m::text AS rs_pctile_6m,
      rs_1m_category::text AS rs_1m_category,
      rs_3m_category::text AS rs_3m_category,
      rs_6m_category::text AS rs_6m_category,
      realized_vol_63::text AS realized_vol_63,
      drawdown_ratio_252::text AS drawdown_ratio_252
    FROM atlas.atlas_fund_metrics_daily
    WHERE mstar_id = ${mstar_id}
      AND nav_date >= CURRENT_DATE - (${days} || ' days')::interval
    ORDER BY nav_date ASC
  `
}

export async function getFundLens(mstar_id: string): Promise<FundLensRow | null> {
  const rows = await sql<FundLensRow[]>`
    SELECT
      (aligned_aum_pct * 100)::text AS aligned_aum_pct,
      (avoid_aum_pct   * 100)::text AS avoid_aum_pct,
      GREATEST(0, 100 - COALESCE(aligned_aum_pct * 100, 0) - COALESCE(avoid_aum_pct * 100, 0))::text AS neutral_aum_pct,
      (strong_aum_pct * 100)::text AS strong_aum_pct,
      (weak_aum_pct   * 100)::text AS weak_aum_pct,
      GREATEST(0, 100 - COALESCE(strong_aum_pct * 100, 0) - COALESCE(weak_aum_pct * 100, 0))::text AS unknown_aum_pct,
      sector_concentration::text AS sector_concentration,
      holdings_concentration::text AS holdings_concentration,
      last_disclosed_date,
      as_of_date
    FROM atlas.atlas_fund_lens_monthly
    WHERE mstar_id = ${mstar_id}
    ORDER BY as_of_date DESC
    LIMIT 1
  `
  return rows[0] ?? null
}

// getFundDecisionHistory reads from atlas_fund_decisions_daily (historical decision log).
// This is a genuine decision audit log, not a signal read — retained as-is.
export async function getFundDecisionHistory(mstar_id: string): Promise<FundDecisionRow[]> {
  return sql<FundDecisionRow[]>`
    SELECT
      date,
      recommendation,
      entry_trigger, exit_trigger, reduce_trigger, add_trigger,
      performance_gate, sectors_gate, stocks_gate, market_gate,
      weeks_in_current_state::text AS weeks_in_current_state
    FROM atlas.atlas_fund_decisions_daily
    WHERE mstar_id = ${mstar_id}
    ORDER BY date DESC
    LIMIT 52
  `
}

export type FundNavHistoryRow = {
  nav_date: Date
  nav: string
  nav_adj: string
  nav_change: string | null
}

export type FundLensHistoryRow = {
  as_of_date: Date
  last_disclosed_date: Date | null
  aligned_aum_pct: string | null
  avoid_aum_pct: string | null
  neutral_aum_pct: string | null
  strong_aum_pct: string | null
  weak_aum_pct: string | null
  unknown_aum_pct: string | null
  sector_concentration: string | null
  holdings_concentration: string | null
}

export type FundHoldingRow = {
  symbol: string | null
  company_name: string | null
  weight: string | null
  sector: string | null
  rs_state: string | null
  momentum_state: string | null
  risk_state: string | null
  ret_1m: string | null
  ret_3m: string | null
  holdings_date: string | null
}

export async function getFundNavHistory(
  mstar_id: string,
  days = 365,
): Promise<FundNavHistoryRow[]> {
  if (!Number.isInteger(days) || days < 1 || days > 1825) {
    throw new Error(`days must be between 1 and 1825, got: ${days}`)
  }
  return sql<FundNavHistoryRow[]>`
    SELECT
      nav_date,
      nav::text AS nav,
      COALESCE(nav_adj, nav)::text AS nav_adj,
      nav_change::text AS nav_change
    FROM public.de_mf_nav_daily
    WHERE mstar_id = ${mstar_id}
      AND nav_date >= CURRENT_DATE - (${days} || ' days')::interval
    ORDER BY nav_date ASC
  `
}

export async function getFundLensHistory(mstar_id: string): Promise<FundLensHistoryRow[]> {
  return sql<FundLensHistoryRow[]>`
    SELECT
      as_of_date,
      last_disclosed_date,
      (aligned_aum_pct * 100)::text AS aligned_aum_pct,
      (avoid_aum_pct   * 100)::text AS avoid_aum_pct,
      GREATEST(0, 100 - COALESCE(aligned_aum_pct * 100, 0) - COALESCE(avoid_aum_pct * 100, 0))::text AS neutral_aum_pct,
      (strong_aum_pct * 100)::text AS strong_aum_pct,
      (weak_aum_pct   * 100)::text AS weak_aum_pct,
      GREATEST(0, 100 - COALESCE(strong_aum_pct * 100, 0) - COALESCE(weak_aum_pct * 100, 0))::text AS unknown_aum_pct,
      sector_concentration::text AS sector_concentration,
      holdings_concentration::text AS holdings_concentration
    FROM atlas.atlas_fund_lens_monthly
    WHERE mstar_id = ${mstar_id}
    ORDER BY as_of_date ASC
  `
}

// Phase 7: getFundHoldings rewired — stock rs_state/momentum_state from atlas_stock_signal_unified.
export async function getFundHoldings(mstar_id: string, limit = 20): Promise<FundHoldingRow[]> {
  if (!Number.isInteger(limit) || limit < 1 || limit > 100) {
    throw new Error(`limit must be between 1 and 100, got: ${limit}`)
  }
  return sql<FundHoldingRow[]>`
    WITH latest_holdings AS (
      SELECT MAX(as_of_date) AS as_of_date
      FROM public.de_mf_holdings
      WHERE mstar_id = ${mstar_id}
    ),
    latest_states_date AS (
      SELECT MAX(date) AS d
      FROM atlas.atlas_stock_signal_unified
      WHERE date <= COALESCE((SELECT as_of_date FROM latest_holdings), CURRENT_DATE)
    )
    SELECT
      u.symbol,
      u.company_name,
      (h.weight_pct / 100.0)::text  AS weight,
      u.sector,
      su.rs_state,
      su.momentum_state,
      NULL::text                     AS risk_state,
      m.ret_1m::text                AS ret_1m,
      m.ret_3m::text                AS ret_3m,
      lh.as_of_date::text           AS holdings_date
    FROM public.de_mf_holdings h
    JOIN latest_holdings lh ON h.mstar_id = ${mstar_id}
      AND h.as_of_date = lh.as_of_date
    LEFT JOIN atlas.atlas_universe_stocks u
      ON u.instrument_id = h.instrument_id
      AND u.effective_to IS NULL
    LEFT JOIN atlas.atlas_stock_signal_unified su
      ON su.instrument_id = u.instrument_id
      AND su.date = (SELECT d FROM latest_states_date)
    LEFT JOIN atlas.atlas_stock_metrics_daily m
      ON m.instrument_id = u.instrument_id
      AND m.date = (SELECT d FROM latest_states_date)
    WHERE h.mstar_id = ${mstar_id}
    ORDER BY h.weight_pct DESC
    LIMIT ${limit}
  `
}
