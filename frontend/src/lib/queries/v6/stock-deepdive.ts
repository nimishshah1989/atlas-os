// frontend/src/lib/queries/v6/stock-deepdive.ts
//
// Reads atlas.mv_stock_deepdive for a single symbol. Returns scalars +
// 5 JSONB sections (scorecard_features, conviction_tape, open_signal_calls,
// composite_30d_trajectory, macro_overlays).
//
// MV refreshed nightly via pg_cron (Phase D).

import 'server-only'
import sql from '@/lib/db'

export type ConvictionTape = {
  '1m': string | null
  '3m': string | null
  '6m': string | null
  '12m': string | null
}

export type OpenSignalCall = {
  cell_id: string
  cell_name: string
  tenure: string
  cap_tier: string
  action: string
  confidence: number
  entry_date: string
  cell_explain: string | null
  predicted_excess: number | null
  fired_predicates: unknown
}

export type CompositeTrajectoryPoint = {
  date: string
  composite: number
  confidence: string
}

export type StockDeepdive = {
  instrument_id: string
  symbol: string
  company_name: string
  sector: string | null
  industry: string | null
  tier: string | null
  in_nifty_50: boolean
  in_nifty_100: boolean
  in_nifty_500: boolean
  listing_date: string | null
  composite_score: number | null
  confidence_band: string | null
  backing_ic: number | null
  family_trend: string | null
  family_volatility: string | null
  family_volume: string | null
  family_path: string | null
  family_sector: string | null
  rs_residual_6m: number | null
  realized_vol_60d: number | null
  formation_max_dd: number | null
  listing_age_days: number | null
  log_price: number | null
  ret_1m: number | null
  ret_3m: number | null
  ret_6m: number | null
  ret_12m: number | null
  rs_1m_nifty500: number | null
  rs_3m_nifty500: number | null
  rs_pctile_3m: number | null
  realized_vol_63: number | null
  atr_21: number | null
  max_drawdown_252: number | null
  drawdown_ratio_252: number | null
  ema_10_stock: number | null
  ema_20_stock: number | null
  ema_50_stock: number | null
  ema_200_stock: number | null
  weinstein_gate_pass: boolean
  stage1_base_qualifies: boolean
  volume_expansion: number | null
  avg_volume_20: number | null
  effort_ratio_63: number | null
  rs_state: string | null
  momentum_state: string | null
  risk_state: string | null
  volume_state: string | null
  history_gate_pass: boolean
  liquidity_gate_pass: boolean
  state_weinstein_pass: boolean
  state_since_date: string | null
  scorecard_features: Record<string, unknown> | null
  conviction_tape: ConvictionTape | Record<string, never>
  open_signal_calls: OpenSignalCall[]
  composite_30d_trajectory: CompositeTrajectoryPoint[]
  macro_overlays: Record<string, unknown> | null
  refreshed_at: string | null
}

type Row = {
  instrument_id: string
  symbol: string
  company_name: string
  sector: string | null
  industry: string | null
  tier: string | null
  in_nifty_50: boolean
  in_nifty_100: boolean
  in_nifty_500: boolean
  listing_date: string | null
  composite_score: string | null
  confidence_band: string | null
  backing_ic: string | null
  family_trend: string | null
  family_volatility: string | null
  family_volume: string | null
  family_path: string | null
  family_sector: string | null
  rs_residual_6m: string | null
  realized_vol_60d: string | null
  formation_max_dd: string | null
  listing_age_days: number | string | null
  log_price: string | null
  ret_1m: string | null; ret_3m: string | null; ret_6m: string | null; ret_12m: string | null
  rs_1m_nifty500: string | null; rs_3m_nifty500: string | null; rs_pctile_3m: string | null
  realized_vol_63: string | null
  atr_21: string | null
  max_drawdown_252: string | null; drawdown_ratio_252: string | null
  ema_10_stock: string | null; ema_20_stock: string | null
  ema_50_stock: string | null; ema_200_stock: string | null
  weinstein_gate_pass: boolean
  stage1_base_qualifies: boolean
  volume_expansion: string | null
  avg_volume_20: number | string | null
  effort_ratio_63: string | null
  rs_state: string | null
  momentum_state: string | null
  risk_state: string | null
  volume_state: string | null
  history_gate_pass: boolean
  liquidity_gate_pass: boolean
  state_weinstein_pass: boolean
  state_since_date: string | null
  scorecard_features: Record<string, unknown> | null
  conviction_tape: ConvictionTape | null
  open_signal_calls: OpenSignalCall[] | null
  composite_30d_trajectory: CompositeTrajectoryPoint[] | null
  macro_overlays: Record<string, unknown> | null
  refreshed_at: string | null
}

function toNumber(s: string | number | null | undefined): number | null {
  if (s == null) return null
  const n = typeof s === 'number' ? s : Number(s)
  return Number.isFinite(n) ? n : null
}

export async function getStockDeepdive(symbol: string): Promise<StockDeepdive | null> {
  const rows = await sql<Row[]>`
    SELECT
      instrument_id, symbol, company_name, sector, industry, tier,
      in_nifty_50, in_nifty_100, in_nifty_500,
      listing_date::text AS listing_date,
      composite_score::text AS composite_score,
      confidence_band,
      backing_ic::text AS backing_ic,
      family_trend, family_volatility, family_volume, family_path, family_sector,
      rs_residual_6m::text AS rs_residual_6m,
      realized_vol_60d::text AS realized_vol_60d,
      formation_max_dd::text AS formation_max_dd,
      listing_age_days,
      log_price::text AS log_price,
      ret_1m::text AS ret_1m, ret_3m::text AS ret_3m,
      ret_6m::text AS ret_6m, ret_12m::text AS ret_12m,
      rs_1m_nifty500::text AS rs_1m_nifty500,
      rs_3m_nifty500::text AS rs_3m_nifty500,
      rs_pctile_3m::text   AS rs_pctile_3m,
      realized_vol_63::text AS realized_vol_63,
      atr_21::text AS atr_21,
      max_drawdown_252::text AS max_drawdown_252,
      drawdown_ratio_252::text AS drawdown_ratio_252,
      ema_10_stock::text AS ema_10_stock,
      ema_20_stock::text AS ema_20_stock,
      ema_50_stock::text AS ema_50_stock,
      ema_200_stock::text AS ema_200_stock,
      weinstein_gate_pass, stage1_base_qualifies,
      volume_expansion::text AS volume_expansion,
      avg_volume_20,
      effort_ratio_63::text AS effort_ratio_63,
      rs_state, momentum_state, risk_state, volume_state,
      history_gate_pass, liquidity_gate_pass, state_weinstein_pass,
      state_since_date::text AS state_since_date,
      scorecard_features, conviction_tape, open_signal_calls,
      composite_30d_trajectory, macro_overlays,
      refreshed_at::text AS refreshed_at
    FROM atlas.mv_stock_deepdive
    WHERE symbol = ${symbol}
    LIMIT 1
  `
  const r = rows[0]
  if (!r) return null

  return {
    instrument_id: r.instrument_id,
    symbol: r.symbol,
    company_name: r.company_name,
    sector: r.sector,
    industry: r.industry,
    tier: r.tier,
    in_nifty_50: r.in_nifty_50,
    in_nifty_100: r.in_nifty_100,
    in_nifty_500: r.in_nifty_500,
    listing_date: r.listing_date,
    composite_score: toNumber(r.composite_score),
    confidence_band: r.confidence_band,
    backing_ic: toNumber(r.backing_ic),
    family_trend: r.family_trend,
    family_volatility: r.family_volatility,
    family_volume: r.family_volume,
    family_path: r.family_path,
    family_sector: r.family_sector,
    rs_residual_6m: toNumber(r.rs_residual_6m),
    realized_vol_60d: toNumber(r.realized_vol_60d),
    formation_max_dd: toNumber(r.formation_max_dd),
    listing_age_days: toNumber(r.listing_age_days),
    log_price: toNumber(r.log_price),
    ret_1m: toNumber(r.ret_1m), ret_3m: toNumber(r.ret_3m),
    ret_6m: toNumber(r.ret_6m), ret_12m: toNumber(r.ret_12m),
    rs_1m_nifty500: toNumber(r.rs_1m_nifty500),
    rs_3m_nifty500: toNumber(r.rs_3m_nifty500),
    rs_pctile_3m: toNumber(r.rs_pctile_3m),
    realized_vol_63: toNumber(r.realized_vol_63),
    atr_21: toNumber(r.atr_21),
    max_drawdown_252: toNumber(r.max_drawdown_252),
    drawdown_ratio_252: toNumber(r.drawdown_ratio_252),
    ema_10_stock: toNumber(r.ema_10_stock),
    ema_20_stock: toNumber(r.ema_20_stock),
    ema_50_stock: toNumber(r.ema_50_stock),
    ema_200_stock: toNumber(r.ema_200_stock),
    weinstein_gate_pass: r.weinstein_gate_pass,
    stage1_base_qualifies: r.stage1_base_qualifies,
    volume_expansion: toNumber(r.volume_expansion),
    avg_volume_20: toNumber(r.avg_volume_20),
    effort_ratio_63: toNumber(r.effort_ratio_63),
    rs_state: r.rs_state,
    momentum_state: r.momentum_state,
    risk_state: r.risk_state,
    volume_state: r.volume_state,
    history_gate_pass: r.history_gate_pass,
    liquidity_gate_pass: r.liquidity_gate_pass,
    state_weinstein_pass: r.state_weinstein_pass,
    state_since_date: r.state_since_date,
    scorecard_features: r.scorecard_features,
    conviction_tape: r.conviction_tape ?? {},
    open_signal_calls: r.open_signal_calls ?? [],
    composite_30d_trajectory: r.composite_30d_trajectory ?? [],
    macro_overlays: r.macro_overlays,
    refreshed_at: r.refreshed_at,
  }
}
