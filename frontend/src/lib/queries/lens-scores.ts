import 'server-only'
import sql from '@/lib/db'

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

export type LensScore = {
  instrument_id: string
  date: Date
  symbol: string
  name: string
  sector: string | null
  asset_class: string | null
  // 6 lens scores (0–100)
  technical: number | null
  fundamental: number | null
  valuation: number | null
  catalyst: number | null
  flow: number | null
  policy: number | null
  // subcomponents — technical
  tech_trend: number | null
  tech_rs: number | null
  tech_vol_contraction: number | null
  tech_volume: number | null
  // subcomponents — fundamental
  fund_profitability: number | null
  fund_margin: number | null
  fund_growth: number | null
  fund_balance_sheet: number | null
  fund_op_leverage: number | null
  // subcomponents — valuation
  val_pe_vs_sector: number | null
  val_absolute_pe: number | null
  val_pb: number | null
  val_ev_ebitda: number | null
  val_52w_position: number | null
  // subcomponents — catalyst
  cat_earnings_strategy: number | null
  cat_capital_action: number | null
  cat_governance: number | null
  // subcomponents — flow
  flow_promoter: number | null
  flow_institutional: number | null
  flow_smart_money: number | null
  // subcomponents — policy
  policy_tailwind: number | null
  // composite & conviction
  composite: number | null
  conviction_tier: string | null
  valuation_zone: string | null
  valuation_multiplier: number | null
  smart_money_score: number | null
  degradation_score: number | null
  risk_flags: string[] | null
  evidence: Record<string, unknown> | null
  lenses_active: number | null
  coverage_factor: number | null
}

/** Slim row for table listings — only the 6 lenses + composite + tier. */
export type LensScoreSummary = {
  instrument_id: string
  symbol: string
  name: string
  sector: string | null
  technical: number | null
  fundamental: number | null
  valuation: number | null
  catalyst: number | null
  flow: number | null
  policy: number | null
  composite: number | null
  conviction_tier: string | null
  risk_flags: string[] | null
}

/* ------------------------------------------------------------------ */
/*  Queries                                                            */
/* ------------------------------------------------------------------ */

const LENS_COLS = `
  l.instrument_id, l.date,
  i.symbol, i.name, i.sector, l.asset_class,
  l.technical, l.fundamental, l.valuation, l.catalyst, l.flow, l.policy,
  l.tech_trend, l.tech_rs, l.tech_vol_contraction, l.tech_volume,
  l.fund_profitability, l.fund_margin, l.fund_growth, l.fund_balance_sheet, l.fund_op_leverage,
  l.val_pe_vs_sector, l.val_absolute_pe, l.val_pb, l.val_ev_ebitda, l.val_52w_position,
  l.cat_earnings_strategy, l.cat_capital_action, l.cat_governance,
  l.flow_promoter, l.flow_institutional, l.flow_smart_money,
  l.policy_tailwind,
  l.composite, l.conviction_tier, l.valuation_zone, l.valuation_multiplier,
  l.smart_money_score, l.degradation_score,
  l.risk_flags, l.evidence,
  l.lenses_active, l.coverage_factor
`

/** Latest lens scores for a single stock (by instrument_id). */
export async function getLensScoreByInstrument(instrumentId: string): Promise<LensScore | null> {
  const rows = await sql.unsafe(`
    SELECT ${LENS_COLS}
    FROM foundation_staging.atlas_lens_scores_daily l
    JOIN foundation_staging.instrument_master i ON i.instrument_id = l.instrument_id
    WHERE l.instrument_id = $1
    ORDER BY l.date DESC
    LIMIT 1
  `, [instrumentId])
  return (rows[0] as unknown as LensScore) ?? null
}

/** Latest lens scores for a single stock (by symbol). */
export async function getLensScoreBySymbol(symbol: string): Promise<LensScore | null> {
  const rows = await sql.unsafe(`
    SELECT ${LENS_COLS}
    FROM foundation_staging.atlas_lens_scores_daily l
    JOIN foundation_staging.instrument_master i ON i.instrument_id = l.instrument_id
    WHERE i.symbol = $1
    ORDER BY l.date DESC
    LIMIT 1
  `, [symbol])
  return (rows[0] as unknown as LensScore) ?? null
}

/** Latest lens summary for all stocks — for the ranking table. */
export async function getAllLensScores(): Promise<LensScoreSummary[]> {
  const rows = await sql.unsafe(`
    SELECT DISTINCT ON (l.instrument_id)
      l.instrument_id,
      i.symbol, i.name, i.sector,
      l.technical, l.fundamental, l.valuation, l.catalyst, l.flow, l.policy,
      l.composite, l.conviction_tier, l.risk_flags
    FROM foundation_staging.atlas_lens_scores_daily l
    JOIN foundation_staging.instrument_master i ON i.instrument_id = l.instrument_id
    ORDER BY l.instrument_id, l.date DESC
  `)
  return rows as unknown as LensScoreSummary[]
}

/** Latest lens summary for stocks in a given sector. */
export async function getLensScoresBySector(sector: string): Promise<LensScoreSummary[]> {
  const rows = await sql.unsafe(`
    SELECT DISTINCT ON (l.instrument_id)
      l.instrument_id,
      i.symbol, i.name, i.sector,
      l.technical, l.fundamental, l.valuation, l.catalyst, l.flow, l.policy,
      l.composite, l.conviction_tier, l.risk_flags
    FROM foundation_staging.atlas_lens_scores_daily l
    JOIN foundation_staging.instrument_master i ON i.instrument_id = l.instrument_id
    WHERE i.sector = $1
    ORDER BY l.instrument_id, l.date DESC
  `, [sector])
  return rows as unknown as LensScoreSummary[]
}

/** Sector-level 6-lens vector (cap-weighted averages). */
export async function getSectorLensVectors(): Promise<Array<{
  sector: string
  technical: number | null
  fundamental: number | null
  valuation: number | null
  catalyst: number | null
  flow: number | null
  policy: number | null
  composite: number | null
  stock_count: number
}>> {
  const rows = await sql.unsafe(`
    WITH ld AS (
      SELECT max(date) d FROM foundation_staging.atlas_lens_scores_daily WHERE asset_class='stock'
    ),
    latest AS (
      -- the latest-DATE snapshot (uses the class_date index ~2k rows); replaces a DISTINCT ON
      -- that scanned the whole 3.9M-row journal to pick the last row per instrument.
      SELECT i.sector,
        l.technical, l.fundamental, l.valuation, l.catalyst, l.flow, l.policy,
        l.composite
      FROM foundation_staging.atlas_lens_scores_daily l
      JOIN foundation_staging.instrument_master i ON i.instrument_id = l.instrument_id
      WHERE i.sector IS NOT NULL AND l.asset_class='stock' AND l.date = (SELECT d FROM ld)
    )
    SELECT
      sector,
      ROUND(AVG(technical)::numeric, 1) AS technical,
      ROUND(AVG(fundamental)::numeric, 1) AS fundamental,
      ROUND(AVG(valuation)::numeric, 1) AS valuation,
      ROUND(AVG(catalyst)::numeric, 1) AS catalyst,
      ROUND(AVG(flow)::numeric, 1) AS flow,
      ROUND(AVG(policy)::numeric, 1) AS policy,
      ROUND(AVG(composite)::numeric, 1) AS composite,
      COUNT(*)::int AS stock_count
    FROM latest
    GROUP BY sector
    ORDER BY AVG(composite) DESC NULLS LAST
  `)
  return rows as unknown as Array<{
    sector: string
    technical: number | null
    fundamental: number | null
    valuation: number | null
    catalyst: number | null
    flow: number | null
    policy: number | null
    composite: number | null
    stock_count: number
  }>
}
