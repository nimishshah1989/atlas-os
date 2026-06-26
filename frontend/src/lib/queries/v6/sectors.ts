// frontend/src/lib/queries/v6/sectors.ts
//
// Direct Supabase query for the v6 Sectors page.
//
// Joins:
//   atlas_sector_states_daily   ← sector_state ("Overweight"/"Avoid" etc.)
//   atlas_sector_metrics_daily  ← ret_1m / 3m / 6m + participation_rs / breadth
//
// Returns ScreenSector[] consumed by /v6/sectors and /v6/sectors/[name].
// Rank is computed in-app by ordering on participation_rs desc.
//
// MV queries for /sectors (Page 04) and /sectors/[sector] (Page 04a):
//   getSectorCards()      — foundation_staging.mv_sector_cards (latest snapshot, 30 rows)
//   getSectorBreadthMV()  — foundation_staging.mv_sector_breadth (latest snapshot, 30 rows)
//   getSectorRRG()        — foundation_staging.mv_sector_rrg (latest snapshot, 30 rows + trail_6w JSONB)
//   getSectorDeepdive()   — foundation_staging.mv_sector_deepdive (single row per sector, ~30 total)

import 'server-only'
import sql from '@/lib/db'
import { toNumber } from '@/lib/v6/decimal'
import type { ScreenSector } from '@/lib/api/v1'

// ── MV types ──────────────────────────────────────────────────────────────────

export type ConfidenceDistribution = { H: number; M: number; L: number }

export type SectorCardRow = {
  as_of_date: string
  sector_name: string
  constituent_count: number
  ret_1w: number | null
  ret_1m: number | null
  ret_3m: number | null
  ret_6m: number | null
  ret_12m: number | null
  rs_1m: number | null
  rs_3m: number | null
  rs_6m: number | null
  vol_60d_ann: number | null
  pct_above_ema21: number | null
  pct_above_ema200: number | null
  pct_at_52wh: number | null
  hhi_concentration: number | null
  buy_signal_count: number
  confidence_distribution: ConfidenceDistribution
  verdict: string
  verdict_abbr: string | null
}

export type BreadthWindowEntry = {
  window: string
  pct_positive: number | null
  pct_top_decile_movers: number | null
}

export type BreadthByStrength = {
  very_strong: number
  strong: number
  neutral: number
  weak: number
  very_weak: number
}

export type MoverEntry = { symbol: string; ret_pct: number }

export type SectorBreadthMVRow = {
  as_of_date: string
  sector_name: string
  constituent_count: number
  pct_above_ema21: number | null
  pct_above_ema50: number | null
  pct_above_ema200: number | null
  pct_at_52wh: number | null
  breadth_by_window: BreadthWindowEntry[]
  breadth_by_strength: BreadthByStrength | null
  top_movers: MoverEntry[]
  bottom_movers: MoverEntry[]
}

export type TrailEntry = {
  week_end_date: string
  rs_ratio: number | null
  rs_momentum: number | null
  quadrant: string | null
}

export type SectorRRGRow = {
  as_of_date: string
  sector_name: string
  rs_ratio_current: number | null
  rs_momentum_current: number | null
  quadrant_current: string | null
  trail_6w: TrailEntry[]
  // card metadata (joined from sector cards for convenience)
  constituent_count?: number
}

export type ConstituentRow = {
  symbol: string
  company_name: string | null
  tier: string | null
  ret_1w: number | null
  ret_1m: number | null
  ret_3m: number | null
  ret_6m: number | null
  rs_3m_nifty500_pp: number | null
  vol_60d: number | null
  rs_state: string | null
  composite_score: number | null
  confidence_band: string | null
  action: string | null
}

export type OpenSignalRow = {
  symbol: string
  company_name: string | null
  action: string
  tenure: string | null
  cap_tier_at_trigger: string | null
  confidence_unconditional: number | null
  signal_date: string
}

export type TopPickRow = {
  symbol: string
  company_name: string | null
  composite_score: number | null
  confidence_band: string | null
  action: string | null
}

export type StrengthDist = {
  very_strong: number
  strong: number
  neutral: number
  weak: number
  very_weak: number
}

export type SectorDeepdiveRow = {
  sector_name: string
  verdict: string
  constituent_count: number
  data_as_of: string
  returns: {
    ret_1w: number | null
    ret_1m: number | null
    ret_3m: number | null
    ret_6m: number | null
    ret_12m: number | null
  }
  rs_windows: {
    rs_1w: number | null
    rs_1m: number | null
    rs_3m: number | null
    rs_6m: number | null
    rs_12m: number | null
  }
  pct_above_ema21: number | null
  pct_above_ema200: number | null
  pct_at_52wh: number | null
  constituents_top30: ConstituentRow[]
  open_signals: OpenSignalRow[]
  strength_dist: StrengthDist
  top_picks_top10: TopPickRow[]
  sub_industries: SubIndustryRow[]
}

export type SubIndustryRow = {
  industry: string
  n_stocks: number
  avg_rs_3m_pp: number | null
  avg_composite_score: number | null
  n_buy: number
  n_avoid: number
}

// ── MV Query functions ────────────────────────────────────────────────────────

/**
 * Latest snapshot of mv_sector_cards — 30 rows ordered by rs_3m DESC.
 * Used for: hero readout, sector cards grid, heatmap table.
 */
export async function getSectorCards(): Promise<SectorCardRow[]> {
  const rows = await sql<Array<{
    as_of_date: string
    sector_name: string
    constituent_count: number
    ret_1w: string | null
    ret_1m: string | null
    ret_3m: string | null
    ret_6m: string | null
    ret_12m: string | null
    rs_1m: string | null
    rs_3m: string | null
    rs_6m: string | null
    vol_60d_ann: string | null
    pct_above_ema21: string | null
    pct_above_ema200: string | null
    pct_at_52wh: string | null
    hhi_concentration: string | null
    buy_signal_count: number
    confidence_distribution: ConfidenceDistribution
    verdict: string
    verdict_abbr: string | null
  }>>`
    SELECT
      as_of_date::text,
      sector_name,
      constituent_count,
      ret_1w::text,
      ret_1m::text,
      ret_3m::text,
      ret_6m::text,
      ret_12m::text,
      rs_1m::text,
      rs_3m::text,
      rs_6m::text,
      vol_60d_ann::text,
      pct_above_ema21::text,
      pct_above_ema200::text,
      pct_at_52wh::text,
      hhi_concentration::text,
      buy_signal_count,
      confidence_distribution,
      verdict,
      verdict_abbr
    FROM foundation_staging.mv_sector_cards
    WHERE as_of_date = (
      -- Anchor to last fully-populated date. On a fresh trading day,
      -- rs_1m / ret_1w / ret_12m / breadth columns can lag rs_3m by one
      -- compute cycle. Picking MAX(as_of_date) blindly gives a partial row
      -- with empty 1W / 12M / breadth columns. Filter on rs_1m IS NOT NULL.
      SELECT MAX(as_of_date) FROM foundation_staging.mv_sector_cards
      WHERE rs_1m IS NOT NULL AND ret_1w IS NOT NULL
    )
      AND LOWER(sector_name) NOT LIKE '%conglomerate%'
    ORDER BY rs_3m DESC NULLS LAST
  `

  // mv_sector_cards.buy_signal_count counts signals TRIGGERED on T-0 only,
  // so it almost always shows 0. Overlay live counts of OPEN BUY signals
  // (exit_date IS NULL) grouped by sector — that's what the UI implies.
  const liveCounts = await sql<Array<{
    sector_name: string
    n_open: number
    conf_h: number
    conf_m: number
    conf_l: number
  }>>`
    SELECT
      u.sector AS sector_name,
      COUNT(sc.signal_call_id)::int AS n_open,
      COUNT(CASE WHEN sc.confidence_unconditional >= 0.70 THEN 1 END)::int AS conf_h,
      COUNT(CASE WHEN sc.confidence_unconditional >= 0.50
                  AND sc.confidence_unconditional <  0.70 THEN 1 END)::int AS conf_m,
      COUNT(CASE WHEN sc.confidence_unconditional <  0.50 THEN 1 END)::int AS conf_l
    FROM atlas.atlas_signal_calls sc
    JOIN atlas.atlas_universe_stocks u
      ON u.instrument_id = sc.instrument_id
     AND u.effective_to IS NULL
    WHERE sc.action = 'POSITIVE'
      AND sc.exit_date IS NULL
    GROUP BY u.sector
  `
  const liveBySector = new Map(liveCounts.map(r => [r.sector_name, r]))

  return rows.map((r) => ({
    as_of_date: r.as_of_date,
    sector_name: r.sector_name,
    constituent_count: r.constituent_count,
    ret_1w: toNumber(r.ret_1w),
    ret_1m: toNumber(r.ret_1m),
    ret_3m: toNumber(r.ret_3m),
    ret_6m: toNumber(r.ret_6m),
    ret_12m: toNumber(r.ret_12m),
    rs_1m: toNumber(r.rs_1m),
    rs_3m: toNumber(r.rs_3m),
    rs_6m: toNumber(r.rs_6m),
    vol_60d_ann: toNumber(r.vol_60d_ann),
    pct_above_ema21: toNumber(r.pct_above_ema21),
    pct_above_ema200: toNumber(r.pct_above_ema200),
    pct_at_52wh: toNumber(r.pct_at_52wh),
    hhi_concentration: toNumber(r.hhi_concentration),
    buy_signal_count: liveBySector.get(r.sector_name)?.n_open ?? r.buy_signal_count,
    confidence_distribution: liveBySector.has(r.sector_name)
      ? {
          H: liveBySector.get(r.sector_name)!.conf_h,
          M: liveBySector.get(r.sector_name)!.conf_m,
          L: liveBySector.get(r.sector_name)!.conf_l,
        }
      : r.confidence_distribution,
    verdict: r.verdict,
    verdict_abbr: r.verdict_abbr,
  }))
}

/**
 * Latest snapshot of mv_sector_breadth — 30 rows.
 * Used for: breadth panel on list page and detail page.
 */
export async function getSectorBreadthMV(sectorName?: string): Promise<SectorBreadthMVRow[]> {
  const rows = await sql<Array<{
    as_of_date: string
    sector_name: string
    constituent_count: number
    pct_above_ema21: string | null
    pct_above_ema50: string | null
    pct_above_ema200: string | null
    pct_at_52wh: string | null
    breadth_by_window: BreadthWindowEntry[]
    breadth_by_strength: BreadthByStrength | null
    top_movers: MoverEntry[]
    bottom_movers: MoverEntry[]
  }>>`
    SELECT
      as_of_date::text,
      sector_name,
      constituent_count,
      pct_above_ema21::text,
      pct_above_ema50::text,
      pct_above_ema200::text,
      pct_at_52wh::text,
      breadth_by_window,
      breadth_by_strength,
      top_movers,
      bottom_movers
    FROM foundation_staging.mv_sector_breadth
    WHERE as_of_date = (
      SELECT MAX(as_of_date) FROM foundation_staging.mv_sector_breadth
    )
    ${sectorName != null ? sql`AND sector_name = ${sectorName}` : sql``}
    ORDER BY sector_name
  `

  return rows.map((r) => ({
    as_of_date: r.as_of_date,
    sector_name: r.sector_name,
    constituent_count: r.constituent_count,
    pct_above_ema21: toNumber(r.pct_above_ema21),
    pct_above_ema50: toNumber(r.pct_above_ema50),
    pct_above_ema200: toNumber(r.pct_above_ema200),
    pct_at_52wh: toNumber(r.pct_at_52wh),
    breadth_by_window: r.breadth_by_window ?? [],
    breadth_by_strength: r.breadth_by_strength ?? null,
    top_movers: r.top_movers ?? [],
    bottom_movers: r.bottom_movers ?? [],
  }))
}

/**
 * Latest snapshot of mv_sector_rrg — 30 rows with trail_6w JSONB.
 * Used for: RRG 4-quadrant scatter chart.
 */
export async function getSectorRRG(): Promise<SectorRRGRow[]> {
  const rows = await sql<Array<{
    as_of_date: string
    sector_name: string
    rs_ratio_current: string | null
    rs_momentum_current: string | null
    quadrant_current: string | null
    trail_6w: TrailEntry[]
    constituent_count: number
  }>>`
    SELECT
      r.as_of_date::text,
      r.sector_name,
      r.rs_ratio_current::text,
      r.rs_momentum_current::text,
      r.quadrant_current,
      r.trail_6w,
      COALESCE(c.constituent_count, 0) AS constituent_count
    FROM foundation_staging.mv_sector_rrg r
    LEFT JOIN foundation_staging.mv_sector_cards c
      ON c.sector_name = r.sector_name
     AND c.as_of_date = r.as_of_date
    WHERE r.as_of_date = (
      SELECT MAX(as_of_date) FROM foundation_staging.mv_sector_rrg
    )
    ORDER BY r.sector_name
  `

  return rows.map((r) => ({
    as_of_date: r.as_of_date,
    sector_name: r.sector_name,
    rs_ratio_current: toNumber(r.rs_ratio_current),
    rs_momentum_current: toNumber(r.rs_momentum_current),
    quadrant_current: r.quadrant_current,
    trail_6w: r.trail_6w ?? [],
    constituent_count: r.constituent_count,
  }))
}

/**
 * Single sector row from mv_sector_deepdive (latest-only MV).
 * Returns null when sector not found.
 */
export async function getSectorDeepdive(sectorName: string): Promise<SectorDeepdiveRow | null> {
  const rows = await sql<Array<{
    sector_name: string
    verdict: string
    constituent_count: number
    data_as_of: string
    returns: SectorDeepdiveRow['returns']
    rs_windows: SectorDeepdiveRow['rs_windows']
    pct_above_ema21: string | null
    pct_above_ema200: string | null
    pct_at_52wh: string | null
    constituents_top30: ConstituentRow[]
    open_signals: OpenSignalRow[]
    strength_dist: StrengthDist
    top_picks_top10: TopPickRow[]
  }>>`
    SELECT
      sector_name,
      verdict,
      constituent_count,
      data_as_of::text,
      returns,
      rs_windows,
      pct_above_ema21::text,
      pct_above_ema200::text,
      pct_at_52wh::text,
      constituents_top30,
      open_signals,
      strength_dist,
      top_picks_top10
    FROM foundation_staging.mv_sector_deepdive
    WHERE sector_name = ${sectorName}
    LIMIT 1
  `

  if (rows.length === 0) return null

  const r = rows[0]
  return {
    sector_name: r.sector_name,
    verdict: r.verdict,
    constituent_count: r.constituent_count,
    data_as_of: r.data_as_of,
    returns: r.returns,
    rs_windows: r.rs_windows,
    pct_above_ema21: toNumber(r.pct_above_ema21),
    pct_above_ema200: toNumber(r.pct_above_ema200),
    pct_at_52wh: toNumber(r.pct_at_52wh),
    constituents_top30: r.constituents_top30 ?? [],
    open_signals: r.open_signals ?? [],
    strength_dist: r.strength_dist ?? { very_strong: 0, strong: 0, neutral: 0, weak: 0, very_weak: 0 },
    top_picks_top10: r.top_picks_top10 ?? [],
    sub_industries: [],
  }
}

type Row = {
  sector_name: string
  sector_state: string
  bottomup_state: string | null
  topdown_state: string | null
  bottomup_rs_state: string | null
  bottomup_momentum_state: string | null
  participation_rs_pct: string | null
  bottomup_ret_1m: string | null
  bottomup_ret_3m: string | null
  bottomup_rs_3m_nifty500: string | null
  participation_50: string | null
  constituent_count: number | null
}

/**
 * Return all sectors for a snapshot_date, ranked by participation_rs_pct desc.
 *
 * The page expects ScreenSector — we fill in v6.x placeholders for
 * rrg_quadrant, cells_favored_today and days_in_state (those are not yet
 * surfaced from the new sector pipeline).
 */
export async function getSectorsForDate(snapshotDate: string): Promise<ScreenSector[]> {
  const rows = await sql<Row[]>`
    SELECT
      s.sector_name,
      s.sector_state,
      s.bottomup_state,
      s.topdown_state,
      s.bottomup_rs_state,
      s.bottomup_momentum_state,
      s.participation_rs_pct::text   AS participation_rs_pct,
      m.bottomup_ret_1m::text        AS bottomup_ret_1m,
      m.bottomup_ret_3m::text        AS bottomup_ret_3m,
      m.bottomup_rs_3m_nifty500::text AS bottomup_rs_3m_nifty500,
      m.participation_50::text       AS participation_50,
      m.constituent_count
    FROM atlas.atlas_sector_states_daily s
    LEFT JOIN atlas.atlas_sector_metrics_daily m
      ON m.sector_name = s.sector_name
     AND m.date        = s.date
    WHERE s.date = ${snapshotDate}
    ORDER BY
      CASE s.sector_state
        WHEN 'Overweight'  THEN 0
        WHEN 'Neutral'     THEN 1
        WHEN 'Underweight' THEN 2
        WHEN 'Avoid'       THEN 3
        ELSE 4
      END,
      s.participation_rs_pct DESC NULLS LAST
  `

  return rows.map((r, idx): ScreenSector => ({
    sector_iid: r.sector_name,
    sector_name: r.sector_name,
    rank: idx + 1,
    rank_change: 0,
    days_in_state: 0,
    sector_state: r.sector_state,
    breadth_pct_stage_2: (() => { const v = toNumber(r.participation_50); return v != null ? v / 100 : null })(),
    vol_regime: r.bottomup_momentum_state ?? 'Normal',
    rs_pct_cross_sector: toNumber(r.bottomup_rs_3m_nifty500),
    ret_1m: toNumber(r.bottomup_ret_1m),
    ret_3m: toNumber(r.bottomup_ret_3m),
    rrg_quadrant: null,
    cells_favored_today: [],
  }))
}
