// frontend/src/lib/queries/v6/india_pulse.ts
//
// Data layer for /india-pulse (Page 02 — India Pulse).
// Source: atlas.mv_india_pulse — one row per date, latest row served.
//
// Exports:
//   getIndiaPulsePage()  — full page snapshot, typed

import 'server-only'
import sql from '@/lib/db'
import { toNumber } from '@/lib/v6/decimal'

// ---------------------------------------------------------------------------
// Raw DB row shape (JSONB columns come back as parsed objects from postgres-js)
// ---------------------------------------------------------------------------

type RawRow = {
  as_of_date: string | null
  breadth_pct_above_200dma: string | null
  india_vix: string | null
  cross_section_dispersion: string | null
  smallcap_rs_z: string | null
  vix_spot: string | null
  vix_5y_pct: string | null
  vix_term_structure: string | null
  headline_indices: HeadlineIndexItem[] | null
  breadth_table: BreadthRow[] | null
  sector_heatmap: SectorHeatmapItem[] | null
  tier_leadership: TierLeadership | null
  dispersion_60d_series: DispersionPoint[] | null
  macro_cards: MacroCard[] | null
  narrative_ribbon: NarrativeRibbon | null
}

// ---------------------------------------------------------------------------
// JSONB element types
// ---------------------------------------------------------------------------

export type HeadlineIndexItem = {
  index_code: string
  label: string
  close: number | null
  ret_1d: number | null
  ret_1w: number | null
  ret_1m: number | null
  ret_3m: number | null
  ret_6m: number | null
  rs_3m_vs_nifty500: number | null
}

export type BreadthRow = {
  metric: string
  label: string
  today: number | null
  delta_1w: number | null
  delta_1m: number | null
  delta_3m: number | null
  data_gap: boolean
}

export type SectorHeatmapItem = {
  sector_name: string
  rs_1w: number | null
  ret_1m: number | null
  ret_3m: number | null
}

export type TierReturnWindow = {
  window: string
  sc: number | null
  mc: number | null
  lc: number | null
  sc_lc_spread: number | null
  mc_lc_spread: number | null
}

export type TierLeadership = {
  returns_table: TierReturnWindow[]
  smallcap_rs_z: number | null
}

export type DispersionPoint = {
  date: string
  value: number | null
}

export type SparkPoint = {
  date: string
  v: number | null
}

export type MacroCard = {
  id: string
  label: string
  value: number | null
  ret_1d: number | null
  ret_1m: number | null
  sparkline_30d: SparkPoint[] | null
}

export type NarrativeRibbon = {
  india_10y_yield: number | null
  real_yield: number | null
  cpi_yoy: number | null
  fii_flow_1m_cr: number | null
  dii_flow_1m_cr: number | null
  equity_earnings_yield: number | null
}

// ---------------------------------------------------------------------------
// Public page data type
// ---------------------------------------------------------------------------

export type IndiaPulsePageData = {
  as_of_date: string | null
  // Hero scalars
  smallcap_rs_z: number | null
  breadth_pct_above_200dma: number | null
  india_vix: number | null
  cross_section_dispersion: number | null
  // Volatility triple
  vix_spot: number | null
  vix_5y_pct: number | null
  vix_term_structure: number | null
  // JSONB sections
  headline_indices: HeadlineIndexItem[]
  breadth_table: BreadthRow[]
  sector_heatmap: SectorHeatmapItem[]
  tier_leadership: TierLeadership | null
  dispersion_60d_series: DispersionPoint[]
  macro_cards: MacroCard[]
  narrative_ribbon: NarrativeRibbon | null
}

// ---------------------------------------------------------------------------
// Null-safe number parse (JSONB numeric fields come back as numbers or strings)
// ---------------------------------------------------------------------------

function n(v: unknown): number | null {
  if (v == null) return null
  if (typeof v === 'number' && Number.isFinite(v)) return v
  if (typeof v === 'string') {
    return toNumber(v)
  }
  return null
}

// ---------------------------------------------------------------------------
// Main query
// ---------------------------------------------------------------------------

export async function getIndiaPulsePage(): Promise<IndiaPulsePageData> {
  const rows = await sql<RawRow[]>`
    SELECT
      as_of_date::text,
      breadth_pct_above_200dma::text,
      india_vix::text,
      cross_section_dispersion::text,
      smallcap_rs_z::text,
      vix_spot::text,
      vix_5y_pct::text,
      vix_term_structure::text,
      headline_indices,
      breadth_table,
      sector_heatmap,
      tier_leadership,
      dispersion_60d_series,
      macro_cards,
      narrative_ribbon
    FROM atlas.mv_india_pulse
    WHERE as_of_date = (SELECT MAX(as_of_date) FROM atlas.mv_india_pulse)
    LIMIT 1
  `

  if (rows.length === 0) {
    return emptySnapshot()
  }

  const r = rows[0]

  // Parse scalar numeric text fields — uses toNumber() from decimal to avoid
  // silent NaN (throws on invalid strings, returns null for empty/null)
  function parseScalar(v: string | null): number | null {
    if (v == null || v === '') return null
    return toNumber(v)
  }

  // Normalize headline_indices array (JSONB numbers may come as strings in some
  // postgres-js configurations — guard both)
  const headline_indices: HeadlineIndexItem[] = (r.headline_indices ?? []).map(item => ({
    index_code: item.index_code,
    label: item.label,
    close: n(item.close),
    ret_1d: n(item.ret_1d),
    ret_1w: n(item.ret_1w),
    ret_1m: n(item.ret_1m),
    ret_3m: n(item.ret_3m),
    ret_6m: n(item.ret_6m),
    rs_3m_vs_nifty500: n(item.rs_3m_vs_nifty500),
  }))

  const breadth_table: BreadthRow[] = (r.breadth_table ?? []).map(row => ({
    metric: row.metric,
    label: row.label,
    today: n(row.today),
    delta_1w: n(row.delta_1w),
    delta_1m: n(row.delta_1m),
    delta_3m: n(row.delta_3m),
    data_gap: row.data_gap === true,
  }))

  const sector_heatmap: SectorHeatmapItem[] = (r.sector_heatmap ?? []).map(s => ({
    sector_name: s.sector_name,
    rs_1w: n(s.rs_1w),
    ret_1m: n(s.ret_1m),
    ret_3m: n(s.ret_3m),
  }))

  let tier_leadership: TierLeadership | null = null
  if (r.tier_leadership) {
    const tl = r.tier_leadership
    tier_leadership = {
      returns_table: (tl.returns_table ?? []).map(row => ({
        window: row.window,
        sc: n(row.sc),
        mc: n(row.mc),
        lc: n(row.lc),
        sc_lc_spread: n(row.sc_lc_spread),
        mc_lc_spread: n(row.mc_lc_spread),
      })),
      smallcap_rs_z: n(tl.smallcap_rs_z),
    }
  }

  const dispersion_60d_series: DispersionPoint[] = (r.dispersion_60d_series ?? []).map(p => ({
    date: p.date,
    value: n(p.value),
  }))

  const macro_cards: MacroCard[] = (r.macro_cards ?? []).map(card => ({
    id: card.id,
    label: card.label,
    value: n(card.value),
    ret_1d: n(card.ret_1d),
    ret_1m: n(card.ret_1m),
    sparkline_30d: (card.sparkline_30d ?? []).map(pt => ({
      date: pt.date,
      v: n(pt.v),
    })),
  }))

  let narrative_ribbon: NarrativeRibbon | null = null
  if (r.narrative_ribbon) {
    const nb = r.narrative_ribbon
    narrative_ribbon = {
      india_10y_yield: n(nb.india_10y_yield),
      real_yield: n(nb.real_yield),
      cpi_yoy: n(nb.cpi_yoy),
      fii_flow_1m_cr: n(nb.fii_flow_1m_cr),
      dii_flow_1m_cr: n(nb.dii_flow_1m_cr),
      equity_earnings_yield: n(nb.equity_earnings_yield),
    }
  }

  return {
    as_of_date: r.as_of_date ?? null,
    smallcap_rs_z: parseScalar(r.smallcap_rs_z),
    breadth_pct_above_200dma: parseScalar(r.breadth_pct_above_200dma),
    india_vix: parseScalar(r.india_vix),
    cross_section_dispersion: parseScalar(r.cross_section_dispersion),
    vix_spot: parseScalar(r.vix_spot),
    vix_5y_pct: parseScalar(r.vix_5y_pct),
    vix_term_structure: parseScalar(r.vix_term_structure),
    headline_indices,
    breadth_table,
    sector_heatmap,
    tier_leadership,
    dispersion_60d_series,
    macro_cards,
    narrative_ribbon,
  }
}

function emptySnapshot(): IndiaPulsePageData {
  return {
    as_of_date: null,
    smallcap_rs_z: null,
    breadth_pct_above_200dma: null,
    india_vix: null,
    cross_section_dispersion: null,
    vix_spot: null,
    vix_5y_pct: null,
    vix_term_structure: null,
    headline_indices: [],
    breadth_table: [],
    sector_heatmap: [],
    tier_leadership: null,
    dispersion_60d_series: [],
    macro_cards: [],
    narrative_ribbon: null,
  }
}
