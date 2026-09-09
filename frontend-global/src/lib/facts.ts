// src/lib/facts.ts — pure derivations over instrument facts, shared by the query layer, the
// components and the tests. Dates are ISO text from postgres (`::text`), money and fractions are
// NUMERIC strings; nothing here does arithmetic on either.
import { formatIsoDate, formatNum } from '@/lib/format'

export type AssetClass = 'etf' | 'stock'

// ── the explorer row ────────────────────────────────────────────────────────

/** What the list query selects per active instrument. Identity, the universe verdict, the fund's
 *  classification, the score row at the latest scored session, and the technicals at EOD — every
 *  one LEFT JOINed, so every column below is null until its producer has run. NUMERICs arrive as
 *  strings; the counts (`lenses_active`, the decile, the rank) are integers.
 *
 *  Exchange, listing date and the SEC identity are NOT here: they are identity facts, not board
 *  columns, and they live on the detail page (docs/global/phase2.md P2-F). Keeping them out is
 *  also what makes room for the score columns under Next's 2 MB data-cache entry limit. */
export type InstrumentDbRow = {
  symbol: string
  name: string | null
  asset_class: AssetClass
  sector_gics: string | null
  in_universe: boolean | null
  /** The ONE reason the snapshot left the row out — universe_snapshot.exclusion_reason, one of
   *  the seven its CHECK allows; null exactly when the row is in (or the snapshot has not run). */
  universe_exclusion: string | null
  // ── etf_classification, current row (null on stocks, and on a fund classify_etfs has not read)
  strategy: string | null
  class_asset_class: string | null
  leveraged: boolean | null
  inverse: boolean | null
  hedged: boolean | null
  /** `auto` where a naming rule fired, `review` where none did — the honest Unclassified queue. */
  class_status: string | null
  country: string | null
  region: string | null
  // ── the score row (etf_scores_daily / lens_scores_daily) at the latest scored session ≤ EOD
  composite: string | null
  technical: string | null
  conviction_tier: string | null
  /** ETFs: `etf_scores_daily.peer_group`. Stocks: `lens_scores_daily.cap_cohort`. Both name the
   *  population the decile below was cut in. */
  peer_group: string | null
  lenses_active: number | null
  /** ntile(10) within (date, peer group) over NON-NULL composites, cut on read — never stored. */
  composite_decile: number | null
  peer_rank: number | null
  peer_n: number | null
  // ── technical_daily at EOD
  rs_3m_spy: string | null
  rs_6m_spy: string | null
  rs_12m_spy: string | null
  pos_52w: string | null
  adv_usd: string | null
  vol_ann: string | null
  mdd_12m: string | null
}

/** A snake_case token as words, for values that arrive as machine tokens (an exclusion reason). */
export const words = (token: string) => token.replace(/_/g, ' ')

export type SecKind = 'cik' | 'series_class' | 'none'

export const SEC_KIND_LABEL: Record<SecKind, string> = { cik: 'CIK', series_class: 'Series + class', none: 'None' }

/** How the SEC knows this instrument: a fund share class (series + class), an issuer (CIK), or not
 *  at all. The ids are detail-page facts (`InstrumentFacts`); the board list does not carry them. */
export function secIdentityKind(r: { cik: string | null; series_id: string | null; class_id: string | null }): SecKind {
  if (r.series_id || r.class_id) return 'series_class'
  return r.cik ? 'cik' : 'none'
}

/** The row the explorer ships to the browser: the query's row with `sector_gics` under the name
 *  the board uses for it. Everything else passes through unchanged. */
export type InstrumentRow = Omit<InstrumentDbRow, 'sector_gics'> & { sector: string | null }

export function toInstrumentRow(r: InstrumentDbRow): InstrumentRow {
  const { sector_gics, ...rest } = r
  return { ...rest, sector: sector_gics }
}

/** The list as cached and shipped: one key list and one array per row — under half the size of
 *  keyed objects, which matters twice: Next's data cache refuses an entry over 2 MB (the keyed
 *  ETF list is 2.2 MB), and the browser receives every row. expandRows restores the row type. */
export type PackedRows = { keys: (keyof InstrumentRow)[]; cells: (string | number | boolean | null)[][] }

export function packRows(rows: InstrumentRow[]): PackedRows {
  const keys = rows.length ? (Object.keys(rows[0]) as (keyof InstrumentRow)[]) : []
  return { keys, cells: rows.map((r) => keys.map((k) => r[k])) }
}

export function expandRows(p: PackedRows): InstrumentRow[] {
  return p.cells.map((c) => Object.fromEntries(p.keys.map((k, i) => [k, c[i]])) as InstrumentRow)
}

/** The price-derived columns; the list shows them only once at least one row carries a value. */
export const PRICE_KEYS = ['rs_3m_spy', 'rs_6m_spy', 'rs_12m_spy', 'pos_52w', 'adv_usd', 'vol_ann', 'mdd_12m'] as const

export function hasPrices(rows: readonly InstrumentRow[]): boolean {
  return rows.some((r) => PRICE_KEYS.some((k) => r[k] != null))
}

/** Whether the scorer has reached this list. Null everywhere is the honest "not scored yet" state
 *  the board renders instead of a wall of em dashes — never a zero (rule #0). */
export function hasScores(rows: readonly InstrumentRow[]): boolean {
  return rows.some((r) => r.composite != null || r.technical != null || r.conviction_tier != null)
}

/** Whether classify_etfs.py has reached this list (the peer-group strip and its facets need it). */
export function hasClassification(rows: readonly InstrumentRow[]): boolean {
  return rows.some((r) => r.class_status != null)
}

/** Whether the universe snapshot has marked any row (the flag and its facet appear only then). */
export function hasUniverse(rows: readonly InstrumentRow[]): boolean {
  return rows.some((r) => r.in_universe != null)
}

/** The universe facet's value: in, or the reason the snapshot gave for leaving the row out. */
export function universeValue(r: Pick<InstrumentRow, 'in_universe' | 'universe_exclusion'>): string {
  if (r.in_universe == null) return 'unknown'
  return r.in_universe ? 'in' : (r.universe_exclusion ?? 'excluded')
}

/** Those values as English. The seven reasons are `universe_snapshot.exclusion_reason`'s CHECK
 *  (scripts/global_market/ddl/05_scores.sql); `excluded` covers a journal row written before the
 *  column existed, `unknown` a session the snapshot has not run for. */
export const UNIVERSE_LABEL: Record<string, string> = {
  in: 'In universe',
  no_bars: 'No price bars',
  too_few_observations: 'Too few sessions',
  stale: 'Not traded lately',
  not_sp500: 'Not in the S&P 500',
  leveraged: 'Leveraged ETF',
  inverse: 'Inverse ETF',
  below_floor: 'Below the floor',
  excluded: 'Excluded',
  unknown: 'Not marked yet',
}

/** What the universe column and facet show: the reason in English, or the token as words if a
 *  reason ever reaches the board before this map does. */
export const universeLabel = (value: string) => UNIVERSE_LABEL[value] ?? words(value)

// ── index membership ────────────────────────────────────────────────────────

export type MembershipInterval = {
  index_code: string
  effective_from: string
  /** EXCLUSIVE: the member is out on this date. NULL = current member. */
  effective_to: string | null
  weight_frac: string | null
  source: string
}

const MEMBERSHIP_SOURCE: Record<string, string> = {
  ssga: 'SSGA weekly holdings',
  fja05680: 'fja05680 archive',
}

export function describeInterval(m: MembershipInterval): { open: boolean; span: string; source: string } {
  const open = m.effective_to == null
  const from = `In from ${formatIsoDate(m.effective_from)}`
  return {
    open,
    span: open ? `${from}, current member` : `${from}, out on ${formatIsoDate(m.effective_to as string)}`,
    source: MEMBERSHIP_SOURCE[m.source] ?? m.source,
  }
}

// ── bars provenance ─────────────────────────────────────────────────────────

/** One row per (source, adjustment_source) an instrument's bars carry. */
export type BarsRow = {
  source: string
  adjustment_source: string | null
  first_date: string
  last_date: string
  sessions: number
  adjusted: number
  total_return: number
}

const BAR_SOURCE: Record<string, string> = { stooq_csv: 'Stooq CSV', alpaca: 'Alpaca' }

function coverage(what: string, n: number, of: number): string {
  if (n === 0) return `${what} not yet labelled (0 of ${formatNum(of)} bars)`
  if (n === of) return `${what} on every bar`
  return `${what} on ${formatNum(n)} of ${formatNum(of)} bars`
}

export function describeBars(b: BarsRow) {
  return {
    source: BAR_SOURCE[b.source] ?? b.source,
    sessions: formatNum(b.sessions),
    adjustment: b.adjustment_source ?? 'not recorded',
    adjusted: coverage('adjusted closes', b.adjusted, b.sessions),
    totalReturn: coverage('total-return closes', b.total_return, b.sessions),
  }
}
