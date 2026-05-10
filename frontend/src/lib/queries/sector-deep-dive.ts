// frontend/src/lib/queries/sector-deep-dive.ts
import 'server-only'
import sql from '@/lib/db'

export type StockRow = {
  instrument_id: string
  symbol: string
  company_name: string
  in_nifty_50: boolean
  in_nifty_100: boolean
  in_nifty_500: boolean
  ret_1m: string | null
  ret_3m: string | null
  ret_6m: string | null
  rs_3m_nifty500: string | null
  rs_pctile_3m: string | null
  rs_3m_tier_gold: string | null
  rs_state: string | null
  momentum_state: string | null
  risk_state: string | null
  volume_state: string | null
  is_investable: boolean | null
  market_gate: boolean | null
  sector_gate: boolean | null
  strength_gate: boolean | null
  direction_gate: boolean | null
  risk_gate: boolean | null
  volume_gate: boolean | null
  position_size_pct: string | null
  ema_10_at_20d_high: boolean | null
  weinstein_gate_pass: boolean | null
}

export async function getStocksInSector(sectorName: string): Promise<StockRow[]> {
  return sql<StockRow[]>`
    WITH latest AS (
      SELECT MAX(date) AS d FROM atlas.atlas_stock_metrics_daily
    )
    SELECT
      u.instrument_id::text AS instrument_id,
      u.symbol,
      u.company_name,
      u.in_nifty_50,
      u.in_nifty_100,
      u.in_nifty_500,
      m.ret_1m::text          AS ret_1m,
      m.ret_3m::text          AS ret_3m,
      m.ret_6m::text          AS ret_6m,
      m.rs_3m_tier::text      AS rs_3m_nifty500,
      m.rs_pctile_3m::text    AS rs_pctile_3m,
      m.rs_3m_tier_gold::text AS rs_3m_tier_gold,
      s.rs_state,
      s.momentum_state,
      s.risk_state,
      s.volume_state,
      d.is_investable,
      d.market_gate,
      d.sector_gate,
      d.strength_gate,
      d.direction_gate,
      d.risk_gate,
      d.volume_gate,
      d.position_size_pct::text AS position_size_pct,
      m.ema_10_at_20d_high,
      m.weinstein_gate_pass
    FROM atlas.atlas_universe_stocks u
    JOIN latest l ON TRUE
    LEFT JOIN atlas.atlas_stock_metrics_daily m
      ON m.instrument_id = u.instrument_id AND m.date = l.d
    LEFT JOIN atlas.atlas_stock_states_daily s
      ON s.instrument_id = u.instrument_id AND s.date = l.d
    LEFT JOIN atlas.atlas_stock_decisions_daily d
      ON d.instrument_id = u.instrument_id AND d.date = l.d
    WHERE u.sector = ${sectorName}
      AND u.effective_to IS NULL
    ORDER BY
      d.is_investable DESC NULLS LAST,
      m.rs_pctile_3m DESC NULLS LAST
  `
}

export type SectorBriefSnapshot = {
  sector_name: string
  constituent_count: number
  bottomup_ret_1m: string | null
  bottomup_ret_3m: string | null
  bottomup_ret_6m: string | null
  bottomup_rs_3m_nifty500: string | null
  bottomup_ema_10_ratio: string | null
  bottomup_ema_20_ratio: string | null
  topdown_ret_1m: string | null
  topdown_ret_3m: string | null
  topdown_rs_3m_nifty500: string | null
  topdown_index_code: string | null
  participation_50: string | null
  participation_rs: string | null
  participation_rs_pct: string | null
  leadership_concentration: string | null
  sector_state: string
  bottomup_state: string | null
  topdown_state: string | null
  divergence_flag: boolean
  bottomup_rs_state: string | null
  bottomup_momentum_state: string | null
  bottomup_risk_state: string | null
  bottomup_volume_state: string | null
  data_date: Date
}

export async function getSectorSnapshotByName(name: string): Promise<SectorBriefSnapshot | null> {
  const rows = await sql<SectorBriefSnapshot[]>`
    SELECT
      m.sector_name,
      m.constituent_count,
      m.bottomup_ret_1m::text          AS bottomup_ret_1m,
      m.bottomup_ret_3m::text          AS bottomup_ret_3m,
      m.bottomup_ret_6m::text          AS bottomup_ret_6m,
      m.bottomup_rs_3m_nifty500::text  AS bottomup_rs_3m_nifty500,
      m.bottomup_ema_10_ratio::text    AS bottomup_ema_10_ratio,
      m.bottomup_ema_20_ratio::text    AS bottomup_ema_20_ratio,
      m.topdown_ret_1m::text           AS topdown_ret_1m,
      m.topdown_ret_3m::text           AS topdown_ret_3m,
      m.topdown_rs_3m_nifty500::text   AS topdown_rs_3m_nifty500,
      m.topdown_index_code,
      m.participation_50::text         AS participation_50,
      m.participation_rs::text         AS participation_rs,
      s.participation_rs_pct::text     AS participation_rs_pct,
      m.leadership_concentration::text AS leadership_concentration,
      s.sector_state,
      s.bottomup_state,
      s.topdown_state,
      s.divergence_flag,
      s.bottomup_rs_state,
      s.bottomup_momentum_state,
      s.bottomup_risk_state,
      s.bottomup_volume_state,
      m.date AS data_date
    FROM atlas.atlas_sector_metrics_daily m
    JOIN atlas.atlas_sector_states_daily s
      ON m.sector_name = s.sector_name AND m.date = s.date
    WHERE m.sector_name = ${name}
      AND m.date = (SELECT MAX(date) FROM atlas.atlas_sector_metrics_daily WHERE sector_name = ${name})
  `
  return rows[0] ?? null
}

export type TopPickRow = {
  symbol: string
  company_name: string
  rs_pctile_3m: string | null
  rs_state: string | null
}

export async function getTopPicksBySector(sectorName: string): Promise<TopPickRow[]> {
  return sql<TopPickRow[]>`
    WITH latest AS (
      SELECT MAX(date) AS d FROM atlas.atlas_stock_metrics_daily
    )
    SELECT
      u.symbol,
      u.company_name,
      m.rs_pctile_3m::text AS rs_pctile_3m,
      st.rs_state
    FROM atlas.atlas_universe_stocks u
    JOIN latest l ON TRUE
    LEFT JOIN atlas.atlas_stock_metrics_daily m
      ON m.instrument_id = u.instrument_id AND m.date = l.d
    LEFT JOIN atlas.atlas_stock_states_daily st
      ON st.instrument_id = u.instrument_id AND st.date = l.d
    LEFT JOIN atlas.atlas_stock_decisions_daily d
      ON d.instrument_id = u.instrument_id AND d.date = l.d
    WHERE u.sector = ${sectorName}
      AND u.effective_to IS NULL
      AND d.is_investable = TRUE
    ORDER BY m.rs_pctile_3m DESC NULLS LAST
    LIMIT 3
  `
}
