// frontend/src/lib/queries/v6/stock-list.ts
//
// Reads atlas.mv_stock_list_v6 — one row per stock with composite score,
// action, tape strip, returns/RS, and pattern families. ~750 rows total.
//
// MV refreshed nightly via pg_cron (Phase D).

import 'server-only'
import sql from '@/lib/db'

export type StockListRow = {
  instrument_id: string
  symbol: string
  company_name: string
  sector: string | null
  tier: string | null
  in_nifty_50: boolean
  in_nifty_100: boolean
  in_nifty_500: boolean
  composite_score: number | null
  confidence_band: string | null
  backing_ic: number | null
  action: string | null
  best_cell_name: string | null
  predicted_excess: number | null
  cross_cell_depth: number
  tape_1m: string | null
  tape_3m: string | null
  tape_6m: string | null
  tape_12m: string | null
  ret_1m: number | null
  ret_3m: number | null
  ret_6m: number | null
  ret_12m: number | null
  rs_1m_nifty500: number | null
  rs_3m_nifty500: number | null
  rs_pctile_3m: number | null
  realized_vol_63: number | null
  max_drawdown_252: number | null
  family_trend: string | null
  family_volatility: string | null
  family_volume: string | null
  family_path: string | null
  family_sector: string | null
  as_of_date: string | null
  refreshed_at: string | null
}

export type StockListPage = {
  as_of_date: string | null
  rows: StockListRow[]
}

type Row = Omit<
  StockListRow,
  | 'composite_score' | 'backing_ic' | 'predicted_excess'
  | 'ret_1m' | 'ret_3m' | 'ret_6m' | 'ret_12m'
  | 'rs_1m_nifty500' | 'rs_3m_nifty500' | 'rs_pctile_3m'
  | 'realized_vol_63' | 'max_drawdown_252'
  | 'cross_cell_depth'
> & {
  composite_score: string | null
  backing_ic: string | null
  predicted_excess: string | null
  ret_1m: string | null
  ret_3m: string | null
  ret_6m: string | null
  ret_12m: string | null
  rs_1m_nifty500: string | null
  rs_3m_nifty500: string | null
  rs_pctile_3m: string | null
  realized_vol_63: string | null
  max_drawdown_252: string | null
  cross_cell_depth: number | string
}

function toNumber(s: string | number | null): number | null {
  if (s == null) return null
  const n = typeof s === 'number' ? s : Number(s)
  return Number.isFinite(n) ? n : null
}

function toInt(s: number | string | null | undefined): number {
  if (s == null) return 0
  const n = typeof s === 'number' ? s : Number(s)
  return Number.isFinite(n) ? n : 0
}

export async function getStockListPage(): Promise<StockListPage> {
  const rows = await sql<Row[]>`
    SELECT
      instrument_id, symbol, company_name, sector, tier,
      in_nifty_50, in_nifty_100, in_nifty_500,
      composite_score::text   AS composite_score,
      confidence_band,
      backing_ic::text        AS backing_ic,
      action,
      best_cell_name,
      predicted_excess::text  AS predicted_excess,
      cross_cell_depth,
      tape_1m, tape_3m, tape_6m, tape_12m,
      ret_1m::text  AS ret_1m,
      ret_3m::text  AS ret_3m,
      ret_6m::text  AS ret_6m,
      ret_12m::text AS ret_12m,
      rs_1m_nifty500::text  AS rs_1m_nifty500,
      rs_3m_nifty500::text  AS rs_3m_nifty500,
      rs_pctile_3m::text    AS rs_pctile_3m,
      realized_vol_63::text AS realized_vol_63,
      max_drawdown_252::text AS max_drawdown_252,
      family_trend, family_volatility, family_volume, family_path, family_sector,
      as_of_date::text  AS as_of_date,
      refreshed_at::text AS refreshed_at
    FROM atlas.mv_stock_list_v6
    ORDER BY
      CASE confidence_band WHEN 'HIGH' THEN 1 WHEN 'MED' THEN 2 WHEN 'LOW' THEN 3 ELSE 4 END,
      composite_score DESC NULLS LAST,
      symbol
  `

  const out: StockListRow[] = rows.map(r => ({
    instrument_id: r.instrument_id,
    symbol: r.symbol,
    company_name: r.company_name,
    sector: r.sector,
    tier: r.tier,
    in_nifty_50: r.in_nifty_50,
    in_nifty_100: r.in_nifty_100,
    in_nifty_500: r.in_nifty_500,
    composite_score: toNumber(r.composite_score),
    confidence_band: r.confidence_band,
    backing_ic: toNumber(r.backing_ic),
    action: r.action,
    best_cell_name: r.best_cell_name,
    predicted_excess: toNumber(r.predicted_excess),
    cross_cell_depth: toInt(r.cross_cell_depth),
    tape_1m: r.tape_1m, tape_3m: r.tape_3m, tape_6m: r.tape_6m, tape_12m: r.tape_12m,
    ret_1m: toNumber(r.ret_1m),
    ret_3m: toNumber(r.ret_3m),
    ret_6m: toNumber(r.ret_6m),
    ret_12m: toNumber(r.ret_12m),
    rs_1m_nifty500: toNumber(r.rs_1m_nifty500),
    rs_3m_nifty500: toNumber(r.rs_3m_nifty500),
    rs_pctile_3m: toNumber(r.rs_pctile_3m),
    realized_vol_63: toNumber(r.realized_vol_63),
    max_drawdown_252: toNumber(r.max_drawdown_252),
    family_trend: r.family_trend,
    family_volatility: r.family_volatility,
    family_volume: r.family_volume,
    family_path: r.family_path,
    family_sector: r.family_sector,
    as_of_date: r.as_of_date,
    refreshed_at: r.refreshed_at,
  }))

  return { as_of_date: out[0]?.as_of_date ?? null, rows: out }
}
