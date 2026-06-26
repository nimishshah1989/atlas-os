// frontend/src/lib/queries/v6/etfs.ts
//
// Direct Supabase query for the v6 ETFs page.
//
// Joins:
//   atlas_etf_scorecard  ← composite + sub-scores + ELI5 + raw_metrics (JSONB)
//   atlas_universe_etfs  ← ticker / etf_name / category enrichment
//   atlas_etf_metrics_daily ← ret_1m / ret_3m / ret_6m / ret_12m + rs_pctile_3m
//
// Returns EtfV6Row (extended shape) sorted by composite_score DESC.
// conviction_tape is a NEUTRAL placeholder — ETFs don't have tape rows today.

import 'server-only'
import sql from '@/lib/db'
import { toNumber } from '@/lib/v6/decimal'
import type { ConvictionTape } from '@/lib/api/v1'

const NEUTRAL_TAPE: ConvictionTape = {
  '1m':  { direction: 'NEUTRAL', ic: null, rule_count: 0, top_rule_id: null },
  '3m':  { direction: 'NEUTRAL', ic: null, rule_count: 0, top_rule_id: null },
  '6m':  { direction: 'NEUTRAL', ic: null, rule_count: 0, top_rule_id: null },
  '12m': { direction: 'NEUTRAL', ic: null, rule_count: 0, top_rule_id: null },
}

// ---------------------------------------------------------------------------
// Public extended row type consumed by ETFsList client component
// ---------------------------------------------------------------------------

export type EtfV6Row = {
  iid: string
  ticker: string
  name: string | null
  category: string | null
  aum_cr: string | null           // from raw_metrics->>'aum_cr' (Cr)
  expense_ratio: string | null    // from raw_metrics->>'ter_pct' (%)
  tracking_error: string | null   // from raw_metrics->>'tracking_error_252d' (%)
  is_atlas_leader: boolean | null
  composite_score: string | null
  conviction_tape: ConvictionTape
  ret_1m: number | null
  ret_3m: number | null
  ret_6m: number | null
  ret_12m: number | null
  rs_state: string | null
}

// ---------------------------------------------------------------------------
// Internal DB row type
// ---------------------------------------------------------------------------

type Row = {
  iid: string
  ticker: string
  name: string | null
  category: string | null
  composite_score: string | null
  is_atlas_leader: boolean | null
  aum_cr: string | null
  expense_ratio: string | null
  tracking_error: string | null
  ret_1m: string | null
  ret_3m: string | null
  ret_6m: string | null
  ret_12m: string | null
  rs_pctile_3m: string | null
}

// ---------------------------------------------------------------------------
// Public query
// ---------------------------------------------------------------------------

/**
 * Return all ETF scorecard rows for a snapshot_date, sorted by composite_score
 * desc. Returns EtfV6Row (extended shape with expense_ratio, tracking_error,
 * aum_cr). conviction_tape is NEUTRAL placeholder (ETF tape is v6.1 work).
 */
export async function getEtfsForDate(snapshotDate: string): Promise<EtfV6Row[]> {
  const rows = await sql<Row[]>`
    SELECT
      s.instrument_id::text                            AS iid,
      s.ticker,
      COALESCE(s.etf_name, u.etf_name)                AS name,
      s.etf_category                                   AS category,
      s.composite_score::text                          AS composite_score,
      s.is_atlas_leader,
      (s.raw_metrics->>'aum_cr')::text                 AS aum_cr,
      (s.raw_metrics->>'ter_pct')::text                AS expense_ratio,
      (s.raw_metrics->>'tracking_error_252d')::text    AS tracking_error,
      m.ret_1m::text                                   AS ret_1m,
      m.ret_3m::text                                   AS ret_3m,
      m.ret_6m::text                                   AS ret_6m,
      m.ret_12m::text                                  AS ret_12m,
      m.rs_pctile_3m::text                             AS rs_pctile_3m
    FROM foundation_staging.atlas_etf_scorecard s
    LEFT JOIN foundation_staging.atlas_universe_etfs u
      ON u.ticker = s.ticker
     AND u.effective_to IS NULL
    LEFT JOIN atlas.atlas_etf_metrics_daily m
      ON m.ticker = s.ticker
     AND m.date   = s.snapshot_date
    WHERE s.snapshot_date = ${snapshotDate}
    ORDER BY s.composite_score DESC NULLS LAST
  `

  return rows.map((r): EtfV6Row => ({
    iid: r.iid,
    ticker: r.ticker,
    name: r.name,
    category: r.category,
    aum_cr: r.aum_cr ?? null,
    expense_ratio: r.expense_ratio ?? null,
    tracking_error: r.tracking_error ?? null,
    is_atlas_leader: r.is_atlas_leader ?? null,
    composite_score: r.composite_score ?? null,
    conviction_tape: NEUTRAL_TAPE,
    ret_1m: toNumber(r.ret_1m),
    ret_3m: toNumber(r.ret_3m),
    ret_6m: toNumber(r.ret_6m),
    ret_12m: toNumber(r.ret_12m),
    rs_state: rsStateFromPctile(r.rs_pctile_3m),
  }))
}

// ---------------------------------------------------------------------------
// Single-ETF detail query (D.8)
// ---------------------------------------------------------------------------

export type EtfDetailRow = EtfV6Row & {
  rank_in_category: number | null
  category_size: number | null
  matrix_conviction_score: string | null
  sector_strength_score: string | null
  tracking_quality_score: string | null
  aum_bracket_score: string | null
  liquidity_score: string | null
  expense_ratio_score: string | null
  eli5: string | null
  top_holdings: ETFTopHolding[] | null
}

export type ETFTopHolding = {
  ticker: string
  weight_pct: string | null
  sector: string | null
}

type DetailRow = Row & {
  rank_in_category: number | null
  category_size: number | null
  matrix_conviction_score: string | null
  sector_strength_score: string | null
  tracking_quality_score: string | null
  aum_bracket_score: string | null
  liquidity_score: string | null
  expense_ratio_score: string | null
  eli5: string | null
  top_holdings: ETFTopHolding[] | null
}

/**
 * Return full scorecard detail for a single ETF by instrument_id (UUID).
 * Returns null when not found (triggers notFound() in page).
 */
export async function getEtfDetail(
  iid: string,
  snapshotDate: string,
): Promise<EtfDetailRow | null> {
  const rows = await sql<DetailRow[]>`
    SELECT
      s.instrument_id::text                              AS iid,
      s.ticker,
      COALESCE(s.etf_name, u.etf_name)                  AS name,
      s.etf_category                                     AS category,
      s.composite_score::text                            AS composite_score,
      s.is_atlas_leader,
      s.rank_in_category,
      s.category_size,
      s.matrix_conviction_score::text                    AS matrix_conviction_score,
      s.sector_strength_score::text                      AS sector_strength_score,
      s.tracking_quality_score::text                     AS tracking_quality_score,
      s.aum_bracket_score::text                          AS aum_bracket_score,
      s.liquidity_score::text                            AS liquidity_score,
      s.expense_ratio_score::text                        AS expense_ratio_score,
      s.eli5,
      (s.raw_metrics->>'aum_cr')::text                   AS aum_cr,
      (s.raw_metrics->>'ter_pct')::text                  AS expense_ratio,
      (s.raw_metrics->>'tracking_error_252d')::text      AS tracking_error,
      m.ret_1m::text                                     AS ret_1m,
      m.ret_3m::text                                     AS ret_3m,
      m.ret_6m::text                                     AS ret_6m,
      m.ret_12m::text                                    AS ret_12m,
      m.rs_pctile_3m::text                               AS rs_pctile_3m,
      s.top_holdings                                     AS top_holdings
    FROM foundation_staging.atlas_etf_scorecard s
    LEFT JOIN foundation_staging.atlas_universe_etfs u
      ON u.ticker = s.ticker
     AND u.effective_to IS NULL
    LEFT JOIN atlas.atlas_etf_metrics_daily m
      ON m.ticker   = s.ticker
     AND m.date     = s.snapshot_date
    WHERE s.instrument_id = ${iid}::uuid
      AND s.snapshot_date = ${snapshotDate}
    LIMIT 1
  `

  const r = rows[0]
  if (!r) return null

  return {
    iid: r.iid,
    ticker: r.ticker,
    name: r.name,
    category: r.category,
    aum_cr: r.aum_cr ?? null,
    expense_ratio: r.expense_ratio ?? null,
    tracking_error: r.tracking_error ?? null,
    is_atlas_leader: r.is_atlas_leader ?? null,
    composite_score: r.composite_score ?? null,
    conviction_tape: NEUTRAL_TAPE,
    ret_1m: toNumber(r.ret_1m),
    ret_3m: toNumber(r.ret_3m),
    ret_6m: toNumber(r.ret_6m),
    ret_12m: toNumber(r.ret_12m),
    rs_state: rsStateFromPctile(r.rs_pctile_3m),
    rank_in_category: r.rank_in_category ?? null,
    category_size: r.category_size ?? null,
    matrix_conviction_score: r.matrix_conviction_score ?? null,
    sector_strength_score: r.sector_strength_score ?? null,
    tracking_quality_score: r.tracking_quality_score ?? null,
    aum_bracket_score: r.aum_bracket_score ?? null,
    liquidity_score: r.liquidity_score ?? null,
    expense_ratio_score: r.expense_ratio_score ?? null,
    eli5: r.eli5 ?? null,
    top_holdings: (r.top_holdings as ETFTopHolding[] | null) ?? null,
  }
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function rsStateFromPctile(p: string | null): string | null {
  const v = toNumber(p)
  if (v == null) return null
  if (v >= 0.90) return 'Leader'
  if (v >= 0.70) return 'Strong'
  if (v >= 0.30) return 'Average'
  if (v >= 0.10) return 'Weak'
  return 'Laggard'
}

// ---------------------------------------------------------------------------
// mv_etf_list_v6 — Page 07 full list (new MV-backed query)
// ---------------------------------------------------------------------------

export type EtfListV6Row = {
  ticker: string
  etf_name: string | null
  fund_house: string | null
  asset_class: string | null
  etf_category: string | null
  composite_score: number | null
  is_atlas_leader: boolean | null
  premium_bps: number | null
  /**
   * Tracking error — 60-day window.
   * MV stores values in two possible scales depending on data source:
   *   v < 1  → fractional (e.g. 0.0010 = 10 bps) — multiply × 10000 to display as bps
   *   v >= 1 → already in bps (e.g. 10.0 = 10 bps) — use as-is
   * Components apply: `const bps = te_60d < 1 ? te_60d * 10000 : te_60d`
   */
  te_60d: number | null
  adv_20d_inr: number | null
  adv_monthly_cr: number | null
  ret_1d: number | null
  ret_1w: number | null
  ret_1m: number | null
  ret_3m: number | null
  ret_6m: number | null
  ret_12m: number | null
  rs_state: string | null
  momentum_state: string | null
  action: string | null           // BUY / AVOID / WATCH
  scatter_zone: string | null     // clean_buy / discount_outlier / premium_outlier / low_adv / premium_unknown
  signal_fire_date: string | null
  /** atlas_tenure enum, e.g. '1m'/'3m'/'6m'/'12m' — string, NOT number */
  signal_tenure: string | null
  as_of_date: string | null
  eli5: string | null
}

type MvEtfListRow = {
  ticker: string
  etf_name: string | null
  fund_house: string | null
  asset_class: string | null
  etf_category: string | null
  composite_score: string | null
  is_atlas_leader: boolean | null
  premium_bps: string | null
  te_60d: string | null
  adv_20d_inr: string | null
  adv_monthly_cr: string | null
  ret_1d: string | null
  ret_1w: string | null
  ret_1m: string | null
  ret_3m: string | null
  ret_6m: string | null
  ret_12m: string | null
  rs_state: string | null
  momentum_state: string | null
  action: string | null
  scatter_zone: string | null
  signal_fire_date: string | null
  signal_tenure: string | null
  as_of_date: string | null
  eli5: string | null
}

/**
 * Return all ETFs from mv_etf_list_v6, sorted by composite_score desc.
 * Use this for the Page 07 list — it includes premium_bps, te_60d, adv_20d_inr
 * and the derived action + scatter_zone columns.
 */
export async function getEtfsList(): Promise<EtfListV6Row[]> {
  const rows = await sql<MvEtfListRow[]>`
    SELECT
      ticker, etf_name, fund_house, asset_class, etf_category,
      composite_score::text, is_atlas_leader,
      premium_bps::text, te_60d::text, adv_20d_inr::text, adv_monthly_cr::text,
      ret_1d::text, ret_1w::text, ret_1m::text, ret_3m::text,
      ret_6m::text, ret_12m::text,
      rs_state, momentum_state,
      action, scatter_zone,
      signal_fire_date::text, signal_tenure::text,
      as_of_date::text, eli5
    FROM atlas.mv_etf_list_v6
    ORDER BY composite_score DESC NULLS LAST
  `

  return rows.map((r): EtfListV6Row => ({
    ticker: r.ticker,
    etf_name: r.etf_name,
    fund_house: r.fund_house,
    asset_class: r.asset_class,
    etf_category: r.etf_category,
    composite_score: toNumber(r.composite_score),
    is_atlas_leader: r.is_atlas_leader ?? null,
    premium_bps: toNumber(r.premium_bps),
    te_60d: toNumber(r.te_60d),
    adv_20d_inr: toNumber(r.adv_20d_inr),
    adv_monthly_cr: toNumber(r.adv_monthly_cr),
    ret_1d: toNumber(r.ret_1d),
    ret_1w: toNumber(r.ret_1w),
    ret_1m: toNumber(r.ret_1m),
    ret_3m: toNumber(r.ret_3m),
    ret_6m: toNumber(r.ret_6m),
    ret_12m: toNumber(r.ret_12m),
    rs_state: r.rs_state,
    momentum_state: r.momentum_state,
    action: r.action,
    scatter_zone: r.scatter_zone,
    signal_fire_date: r.signal_fire_date,
    signal_tenure: r.signal_tenure,
    as_of_date: r.as_of_date,
    eli5: r.eli5,
  }))
}

// ---------------------------------------------------------------------------
// AMC aggregate — computed from getEtfsList() result in JS (34 rows, trivial)
// ---------------------------------------------------------------------------

export type AmcAggregate = {
  fund_house: string
  etf_count: number
  buy_count: number
  avoid_count: number
  watch_count: number
  /** sum of adv_monthly_cr as proxy for AUM */
  total_adv_cr: number
  /** dominant action: BUY | AVOID | WATCH | neutral */
  dominant_action: string
}

export function getAmcAggregates(rows: EtfListV6Row[]): AmcAggregate[] {
  const map = new Map<string, AmcAggregate>()

  for (const r of rows) {
    const fh = r.fund_house?.toUpperCase().trim() ?? 'UNKNOWN'
    if (!map.has(fh)) {
      map.set(fh, {
        fund_house: fh,
        etf_count: 0,
        buy_count: 0,
        avoid_count: 0,
        watch_count: 0,
        total_adv_cr: 0,
        dominant_action: 'neutral',
      })
    }
    const agg = map.get(fh)!
    agg.etf_count += 1
    if (r.action === 'BUY') agg.buy_count += 1
    else if (r.action === 'AVOID') agg.avoid_count += 1
    else if (r.action === 'WATCH') agg.watch_count += 1
    agg.total_adv_cr += r.adv_monthly_cr ?? 0
  }

  // Derive dominant_action and sort by total_adv_cr desc
  const result = Array.from(map.values()).map((a) => ({
    ...a,
    dominant_action:
      a.buy_count > a.avoid_count && a.buy_count > a.watch_count
        ? 'BUY'
        : a.avoid_count > a.watch_count
          ? 'AVOID'
          : a.watch_count > 0
            ? 'WATCH'
            : 'neutral',
  }))

  return result.sort((a, b) => b.total_adv_cr - a.total_adv_cr)
}

// ---------------------------------------------------------------------------
// mv_etf_deepdive — Page 07a single-ETF deep dive
// ---------------------------------------------------------------------------

export type PriceBar = {
  date: string
  open: number
  high: number
  low: number
  close: number
  volume: number
}

export type PeerSetEntry = {
  ticker: string
  composite_score: number | null
  matrix_conviction_score: number | null
  adv_20d_inr: number | null
  is_atlas_leader: boolean | null
  rank_in_category: number | null
  delta_composite: number | null
}

export type EtfDeepdiveRow = {
  ticker: string
  etf_name: string | null
  fund_house: string | null
  asset_class: string | null
  etf_category: string | null
  as_of_date: string | null
  composite_score: number | null
  is_atlas_leader: boolean | null
  premium_bps: number | null
  te_60d: number | null
  adv_20d_inr: number | null
  ret_1m: number | null
  ret_3m: number | null
  ret_6m: number | null
  ret_12m: number | null
  rs_state: string | null
  action: string | null
  eli5: string | null
  /** 180-day OHLCV — may be null if ETF not in de_etf_ohlcv */
  price_180d: PriceBar[] | null
  /** peer set within same etf_category */
  peer_set: PeerSetEntry[] | null
}

type MvDeepdiveRow = {
  ticker: string
  etf_name: string | null
  fund_house: string | null
  asset_class: string | null
  etf_category: string | null
  as_of_date: string | null
  composite_score: string | null
  is_atlas_leader: boolean | null
  premium_bps: string | null
  te_60d: string | null
  adv_20d_inr: string | null
  ret_1m: string | null
  ret_3m: string | null
  ret_6m: string | null
  ret_12m: string | null
  rs_state: string | null
  action: string | null
  eli5: string | null
  price_180d: unknown | null
  peer_set: unknown | null
}

/**
 * Return deep-dive row for a single ETF from mv_etf_deepdive.
 * Returns null when not found (triggers notFound() in page).
 */
export async function getEtfDeepdive(ticker: string): Promise<EtfDeepdiveRow | null> {
  const rows = await sql<MvDeepdiveRow[]>`
    SELECT
      ticker, etf_name, fund_house, asset_class, etf_category,
      as_of_date::text,
      composite_score::text, is_atlas_leader,
      premium_bps::text, te_60d::text, adv_20d_inr::text,
      ret_1m::text, ret_3m::text, ret_6m::text, ret_12m::text,
      rs_state, action, eli5,
      price_180d, peer_set
    FROM atlas.mv_etf_deepdive
    WHERE ticker = ${ticker.toUpperCase()}
    LIMIT 1
  `

  const r = rows[0]
  if (!r) return null

  // Parse JSONB arrays safely
  const price_180d = parsePriceArray(r.price_180d)
  const peer_set = parsePeerSet(r.peer_set)

  return {
    ticker: r.ticker,
    etf_name: r.etf_name,
    fund_house: r.fund_house,
    asset_class: r.asset_class,
    etf_category: r.etf_category,
    as_of_date: r.as_of_date,
    composite_score: toNumber(r.composite_score),
    is_atlas_leader: r.is_atlas_leader ?? null,
    premium_bps: toNumber(r.premium_bps),
    te_60d: toNumber(r.te_60d),
    adv_20d_inr: toNumber(r.adv_20d_inr),
    ret_1m: toNumber(r.ret_1m),
    ret_3m: toNumber(r.ret_3m),
    ret_6m: toNumber(r.ret_6m),
    ret_12m: toNumber(r.ret_12m),
    rs_state: r.rs_state,
    action: r.action,
    eli5: r.eli5,
    price_180d,
    peer_set,
  }
}

// ---------------------------------------------------------------------------
// Private JSONB parsers
// ---------------------------------------------------------------------------

/**
 * Convert an unknown JSONB field to number | null.
 * JSONB numeric fields arrive as JS number already; string path handles
 * edge cases where the driver serialises numerics as strings.
 * Uses toNumber() for string values to satisfy the no-Number lint rule.
 */
function jsonbNum(v: unknown): number | null {
  if (v == null) return null
  if (typeof v === 'number') return Number.isFinite(v) ? v : null
  if (typeof v === 'string') return toNumber(v)
  return null
}

function parsePriceArray(raw: unknown): PriceBar[] | null {
  if (!raw || !Array.isArray(raw)) return null
  return raw
    .map((item): PriceBar | null => {
      if (typeof item !== 'object' || item === null) return null
      const o = item as Record<string, unknown>
      return {
        date: String(o['date'] ?? ''),
        open: jsonbNum(o['open']) ?? 0,
        high: jsonbNum(o['high']) ?? 0,
        low: jsonbNum(o['low']) ?? 0,
        close: jsonbNum(o['close']) ?? 0,
        volume: jsonbNum(o['volume']) ?? 0,
      }
    })
    .filter((x): x is PriceBar => x !== null && x.date !== '')
}

function parsePeerSet(raw: unknown): PeerSetEntry[] | null {
  if (!raw || !Array.isArray(raw)) return null
  return raw
    .map((item): PeerSetEntry | null => {
      if (typeof item !== 'object' || item === null) return null
      const o = item as Record<string, unknown>
      return {
        ticker: String(o['ticker'] ?? ''),
        composite_score: jsonbNum(o['composite_score']),
        matrix_conviction_score: jsonbNum(o['matrix_conviction_score']),
        adv_20d_inr: jsonbNum(o['adv_20d_inr']),
        is_atlas_leader: typeof o['is_atlas_leader'] === 'boolean' ? o['is_atlas_leader'] : null,
        rank_in_category: jsonbNum(o['rank_in_category']),
        delta_composite: jsonbNum(o['delta_composite']),
      }
    })
    .filter((x): x is PeerSetEntry => x !== null && x.ticker !== '')
}
