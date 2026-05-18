// src/lib/queries/sectors.ts
import 'server-only'
import sql from '@/lib/db'
import { MARKET_EVENTS } from '@/lib/event-library'

// postgres returns NUMERIC as string — keep as string, parse at display time

export type SectorSnapshot = {
  sector_name: string
  constituent_count: number
  bottomup_ret_1w: string | null
  bottomup_ret_1m: string | null
  bottomup_ret_3m: string | null
  bottomup_ret_6m: string | null
  bottomup_rs_3m_nifty500: string | null
  rs_momentum: string | null
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
  // Phase 8: stage breadth from atlas_sector_signal_unified
  pct_stage_2: number | null
  pct_stage_3: number | null
  pct_stage_4: number | null
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
  topdown_ret_1m: string | null
  topdown_ret_3m: string | null
  participation_50: string | null
  participation_rs: string | null
  participation_rs_pct: string | null
  leadership_concentration: string | null
  bottomup_ret_3m: string | null
  bottomup_ema_10_ratio: string | null
  bottomup_ema_20_ratio: string | null
  sector_state: string
}

export async function getSectorsWithMomentum(): Promise<SectorSnapshot[]> {
  return sql<SectorSnapshot[]>`
    WITH ranked AS (
      SELECT
        sector_name,
        date,
        bottomup_rs_3m_nifty500,
        LAG(bottomup_rs_3m_nifty500, 20) OVER (
          PARTITION BY sector_name ORDER BY date
        ) AS rs_20d_ago
      FROM atlas.atlas_sector_metrics_daily
    ),
    latest_date AS (
      SELECT MAX(date) AS d FROM atlas.atlas_sector_metrics_daily
    ),
    momentum AS (
      SELECT
        sector_name,
        (bottomup_rs_3m_nifty500 - rs_20d_ago) AS rs_momentum
      FROM ranked
      WHERE date = (SELECT d FROM latest_date)
    )
    SELECT
      m.sector_name,
      m.constituent_count,
      m.bottomup_ret_1w::text          AS bottomup_ret_1w,
      m.bottomup_ret_1m::text          AS bottomup_ret_1m,
      m.bottomup_ret_3m::text          AS bottomup_ret_3m,
      m.bottomup_ret_6m::text          AS bottomup_ret_6m,
      m.bottomup_rs_3m_nifty500::text  AS bottomup_rs_3m_nifty500,
      mom.rs_momentum::text            AS rs_momentum,
      m.bottomup_ema_10_ratio::text    AS bottomup_ema_10_ratio,
      m.bottomup_ema_20_ratio::text    AS bottomup_ema_20_ratio,
      m.topdown_ret_1m::text           AS topdown_ret_1m,
      m.topdown_ret_3m::text           AS topdown_ret_3m,
      m.topdown_rs_3m_nifty500::text   AS topdown_rs_3m_nifty500,
      m.topdown_index_code,
      m.participation_50::text         AS participation_50,
      m.participation_rs::text         AS participation_rs,
      -- Phase 7: participation_rs_pct not in unified view; removed in Phase 8.
      NULL::text                       AS participation_rs_pct,
      m.leadership_concentration::text AS leadership_concentration,
      s.sector_state,
      -- Phase 7: bottomup_state/topdown_state/divergence_flag not in unified view; removed in Phase 8.
      NULL::text                       AS bottomup_state,
      NULL::text                       AS topdown_state,
      FALSE                            AS divergence_flag,
      NULL::text                       AS bottomup_rs_state,
      NULL::text                       AS bottomup_momentum_state,
      NULL::text                       AS bottomup_risk_state,
      NULL::text                       AS bottomup_volume_state,
      m.date                           AS data_date,
      s.pct_stage_2,
      s.pct_stage_3,
      s.pct_stage_4
    FROM atlas.atlas_sector_metrics_daily m
    JOIN atlas.atlas_sector_signal_unified s
      ON m.sector_name = s.sector
     AND m.date        = s.date
    LEFT JOIN momentum mom ON m.sector_name = mom.sector_name
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
  // Phase 7: rewired to atlas_sector_signal_unified.
  return sql<SectorStateRow[]>`
    SELECT date, sector AS sector_name, sector_state
    FROM atlas.atlas_sector_signal_unified
    WHERE date >= CURRENT_DATE - (${days} || ' days')::interval
    ORDER BY date ASC, sector ASC
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
      m.topdown_ret_1m::text           AS topdown_ret_1m,
      m.topdown_ret_3m::text           AS topdown_ret_3m,
      m.participation_50::text         AS participation_50,
      m.participation_rs::text         AS participation_rs,
      -- Phase 7: participation_rs_pct not in unified view; removed in Phase 8.
      NULL::text                       AS participation_rs_pct,
      m.leadership_concentration::text AS leadership_concentration,
      m.bottomup_ret_3m::text          AS bottomup_ret_3m,
      m.bottomup_ema_10_ratio::text    AS bottomup_ema_10_ratio,
      m.bottomup_ema_20_ratio::text    AS bottomup_ema_20_ratio,
      s.sector_state
    FROM atlas.atlas_sector_metrics_daily m
    JOIN atlas.atlas_sector_signal_unified s
      ON m.sector_name = s.sector
     AND m.date        = s.date
    WHERE m.sector_name = ${sectorName}
      AND m.date >= CURRENT_DATE - (${days} || ' days')::interval
    ORDER BY m.date ASC
  `
}

export type SectorPivotRow = {
  sector: string
  ppc_count: number
  npc_count: number
  total_tradeable: number
  pivot_balance: string | null
}

// Phase 7: CTS sector pivot table (atlas_cts_sector_pivot_daily) is being cut.
// Returns empty array; Phase 8 removes the UI panel that consumed this.
export async function getSectorCTSPivot(): Promise<SectorPivotRow[]> {
  return []
}

export type RRGHistoryRow = {
  sector_name: string
  date: Date
  rs: number | null
  momentum: number | null
}

export async function getRRGHistory(days: number = 30): Promise<RRGHistoryRow[]> {
  if (!Number.isInteger(days) || days < 1 || days > 365) {
    throw new Error(`days must be an integer between 1 and 365, got: ${days}`)
  }
  return sql<RRGHistoryRow[]>`
    WITH history AS (
      SELECT
        sector_name,
        date,
        bottomup_rs_3m_nifty500::float AS rs,
        LAG(bottomup_rs_3m_nifty500, 20) OVER (
          PARTITION BY sector_name ORDER BY date
        ) AS rs_20d_ago
      FROM atlas.atlas_sector_metrics_daily
      WHERE date >= CURRENT_DATE - ((${days + 25} || ' days')::interval)
    ),
    with_momentum AS (
      SELECT
        sector_name,
        date,
        rs,
        (rs - rs_20d_ago::float) AS momentum
      FROM history
    )
    SELECT sector_name, date, rs, momentum
    FROM with_momentum
    WHERE date >= CURRENT_DATE - (${days} || ' days')::interval
    ORDER BY sector_name ASC, date ASC
  `
}

export type BreadthWaterfallRow = {
  date: string
  sector: string
  leader_pct: number
  strong_pct: number
  neutral_pct: number
  weak_pct: number
  laggard_pct: number
  sector_state: string
}

export async function getBreadthWaterfallData(
  sectorName: string | null = null,
  days: number = 1095,
): Promise<BreadthWaterfallRow[]> {
  if (!Number.isInteger(days) || days < 1 || days > 3650) {
    throw new Error(`days must be an integer between 1 and 3650, got: ${days}`)
  }
  if (sectorName === null) {
    // Market-wide: one row per date aggregating ALL stocks across all sectors.
    // Phase 7: rewired to atlas_stock_signal_unified.
    return sql<BreadthWaterfallRow[]>`
      SELECT
        date::text                                                                          AS date,
        ''::text                                                                            AS sector,
        COUNT(*) FILTER (WHERE rs_state = 'Leader')::float / NULLIF(COUNT(*), 0)           AS leader_pct,
        COUNT(*) FILTER (WHERE rs_state = 'Strong')::float / NULLIF(COUNT(*), 0)           AS strong_pct,
        COUNT(*) FILTER (WHERE rs_state IN ('Emerging','Consolidating','Average','ILLIQUID','INSUFFICIENT_HISTORY'))::float
          / NULLIF(COUNT(*), 0)                                                             AS neutral_pct,
        COUNT(*) FILTER (WHERE rs_state = 'Weak')::float / NULLIF(COUNT(*), 0)             AS weak_pct,
        COUNT(*) FILTER (WHERE rs_state = 'Laggard')::float / NULLIF(COUNT(*), 0)          AS laggard_pct,
        ''::text                                                                            AS sector_state
      FROM atlas.atlas_stock_signal_unified
      WHERE date >= CURRENT_DATE - (${days} || ' days')::interval
      GROUP BY date
      ORDER BY date ASC
    `
  }
  // Per-sector: join to sector signal unified to include sector_state coloring.
  // Phase 7: rewired to atlas_stock_signal_unified + atlas_sector_signal_unified.
  return sql<BreadthWaterfallRow[]>`
    SELECT
      ssu.date::text AS date,
      u.sector,
      COUNT(*) FILTER (WHERE ssu.rs_state = 'Leader')::float
        / NULLIF(COUNT(*), 0)                                                               AS leader_pct,
      COUNT(*) FILTER (WHERE ssu.rs_state = 'Strong')::float
        / NULLIF(COUNT(*), 0)                                                               AS strong_pct,
      COUNT(*) FILTER (WHERE ssu.rs_state IN ('Emerging', 'Consolidating', 'Average', 'ILLIQUID', 'INSUFFICIENT_HISTORY'))::float
        / NULLIF(COUNT(*), 0)                                                               AS neutral_pct,
      COUNT(*) FILTER (WHERE ssu.rs_state = 'Weak')::float
        / NULLIF(COUNT(*), 0)                                                               AS weak_pct,
      COUNT(*) FILTER (WHERE ssu.rs_state = 'Laggard')::float
        / NULLIF(COUNT(*), 0)                                                               AS laggard_pct,
      COALESCE(sec.sector_state, '')::text AS sector_state
    FROM atlas.atlas_stock_signal_unified ssu
    JOIN atlas.atlas_universe_stocks u
      ON u.instrument_id = ssu.instrument_id
      AND u.effective_to IS NULL
    LEFT JOIN atlas.atlas_sector_signal_unified sec
      ON u.sector = sec.sector AND ssu.date = sec.date
    WHERE ssu.date >= CURRENT_DATE - (${days} || ' days')::interval
      AND u.sector = ${sectorName}
    GROUP BY ssu.date, u.sector, sec.sector_state
    ORDER BY ssu.date ASC
  `
}

export type DaysInStateRow = {
  sector_name: string
  days_in_state: number
}

export async function getDaysInStateForAllSectors(): Promise<DaysInStateRow[]> {
  // Phase 7: rewired to atlas_sector_signal_unified.
  return sql<DaysInStateRow[]>`
    WITH latest_states AS (
      SELECT sector, sector_state
      FROM atlas.atlas_sector_signal_unified
      WHERE date = (SELECT MAX(date) FROM atlas.atlas_sector_signal_unified)
    ),
    streak_starts AS (
      SELECT
        ls.sector,
        COALESCE(MAX(h.date), '2000-01-01'::date) AS change_date
      FROM latest_states ls
      LEFT JOIN atlas.atlas_sector_signal_unified h
        ON h.sector = ls.sector
       AND h.sector_state != ls.sector_state
      GROUP BY ls.sector
    )
    SELECT
      ss.sector AS sector_name,
      COUNT(*)::int AS days_in_state
    FROM streak_starts ss
    JOIN atlas.atlas_sector_signal_unified d
      ON d.sector = ss.sector
     AND d.date > ss.change_date
    GROUP BY ss.sector
  `
}

export type PlaybookEntry = {
  event_id: string
  event_label: string
  event_description: string
  start_date: string
  end_date: string
  leaders: Array<{ sector_name: string; avg_rs: number }>
  laggards: Array<{ sector_name: string; avg_rs: number }>
}

const RISK_OFF_EVENT_IDS = ['covid-crash-2020', 'rate-hike-cycle-2022', 'adani-crisis-2023']
const RISK_ON_EVENT_IDS  = ['post-covid-bull-2020', 'capex-rally-2023', 'post-election-rally-2024']
const NEUTRAL_EVENT_IDS  = ['rate-hike-cycle-2022', 'election-2024', 'capex-rally-2023']

function pickEvents(regimeState: string) {
  const lower = regimeState.toLowerCase()
  const isRiskOff = lower.includes('risk-off') || lower.includes('cautious')
  const isRiskOn  = lower.includes('risk-on')  || lower.includes('constructive')
  if (isRiskOff) return MARKET_EVENTS.filter(e => RISK_OFF_EVENT_IDS.includes(e.id))
  if (isRiskOn)  return MARKET_EVENTS.filter(e => RISK_ON_EVENT_IDS.includes(e.id))
  return MARKET_EVENTS.filter(e => NEUTRAL_EVENT_IDS.includes(e.id))
}

export async function getSectorPlaybook(regimeState: string): Promise<PlaybookEntry[]> {
  const events = pickEvents(regimeState).slice(0, 3)
  if (events.length === 0) return []

  const results = await Promise.all(
    events.map(async (event) => {
      const [leadRows, lagRows] = await Promise.all([
        sql<Array<{ sector_name: string; avg_rs: number }>>`
          SELECT sector_name, AVG(bottomup_rs_3m_nifty500::float)::float AS avg_rs
          FROM atlas.atlas_sector_metrics_daily
          WHERE date BETWEEN ${event.startDate}::date AND ${event.endDate}::date
            AND bottomup_rs_3m_nifty500 IS NOT NULL
          GROUP BY sector_name
          ORDER BY avg_rs DESC
          LIMIT 3
        `,
        sql<Array<{ sector_name: string; avg_rs: number }>>`
          SELECT sector_name, AVG(bottomup_rs_3m_nifty500::float)::float AS avg_rs
          FROM atlas.atlas_sector_metrics_daily
          WHERE date BETWEEN ${event.startDate}::date AND ${event.endDate}::date
            AND bottomup_rs_3m_nifty500 IS NOT NULL
          GROUP BY sector_name
          ORDER BY avg_rs ASC
          LIMIT 3
        `,
      ])
      return {
        event_id:          event.id,
        event_label:       event.label,
        event_description: event.description,
        start_date:        event.startDate,
        end_date:          event.endDate,
        leaders:           leadRows,
        laggards:          lagRows,
      } satisfies PlaybookEntry
    }),
  )
  return results
}
