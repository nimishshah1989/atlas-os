// src/lib/queries/sectors.ts
import 'server-only'
import sql from '@/lib/db'

// postgres returns NUMERIC as string — keep as string, parse at display time

export type SectorSnapshot = {
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

export type SectorStateRow = {
  date: Date
  sector_name: string
  sector_state: string
}

export type SectorMetricHistoryRow = {
  date: Date
  bottomup_rs_3m_nifty500: string | null
  topdown_rs_3m_nifty500: string | null
  topdown_ret_3m: string | null
  participation_50: string | null
  participation_rs: string | null
  bottomup_ret_3m: string | null
  bottomup_ema_10_ratio: string | null
  bottomup_ema_20_ratio: string | null
  sector_state: string
}

export async function getCurrentSectors(): Promise<SectorSnapshot[]> {
  return sql<SectorSnapshot[]>`
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
      m.date                           AS data_date
    FROM atlas.atlas_sector_metrics_daily m
    JOIN atlas.atlas_sector_states_daily s
      ON m.sector_name = s.sector_name
     AND m.date        = s.date
    WHERE m.date = (SELECT MAX(date) FROM atlas.atlas_sector_metrics_daily)
    ORDER BY
      CASE s.sector_state
        WHEN 'Overweight'  THEN 1
        WHEN 'Neutral'     THEN 2
        WHEN 'Underweight' THEN 3
        WHEN 'Avoid'       THEN 4
        ELSE 5
      END,
      m.bottomup_rs_3m_nifty500 DESC NULLS LAST
  `
}

export async function getSectorStateHistory(days: number): Promise<SectorStateRow[]> {
  if (!Number.isInteger(days) || days < 1 || days > 3650) {
    throw new Error(`days must be an integer between 1 and 3650, got: ${days}`)
  }
  return sql<SectorStateRow[]>`
    SELECT date, sector_name, sector_state
    FROM atlas.atlas_sector_states_daily
    WHERE date >= CURRENT_DATE - (${days} || ' days')::interval
    ORDER BY date ASC, sector_name ASC
  `
}

export async function getSectorMetricHistory(
  sectorName: string,
  days: number,
): Promise<SectorMetricHistoryRow[]> {
  if (!Number.isInteger(days) || days < 1 || days > 3650) {
    throw new Error(`days must be an integer between 1 and 3650, got: ${days}`)
  }
  return sql<SectorMetricHistoryRow[]>`
    SELECT
      m.date,
      m.bottomup_rs_3m_nifty500::text  AS bottomup_rs_3m_nifty500,
      m.topdown_rs_3m_nifty500::text   AS topdown_rs_3m_nifty500,
      m.topdown_ret_3m::text           AS topdown_ret_3m,
      m.participation_50::text         AS participation_50,
      m.participation_rs::text         AS participation_rs,
      m.bottomup_ret_3m::text          AS bottomup_ret_3m,
      m.bottomup_ema_10_ratio::text    AS bottomup_ema_10_ratio,
      m.bottomup_ema_20_ratio::text    AS bottomup_ema_20_ratio,
      s.sector_state
    FROM atlas.atlas_sector_metrics_daily m
    JOIN atlas.atlas_sector_states_daily s
      ON m.sector_name = s.sector_name
     AND m.date        = s.date
    WHERE m.sector_name = ${sectorName}
      AND m.date >= CURRENT_DATE - (${days} || ' days')::interval
    ORDER BY m.date ASC
  `
}
