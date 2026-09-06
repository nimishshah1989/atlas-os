// src/lib/facts.ts — pure derivations over instrument facts, shared by the query layer, the
// components and the tests. Dates are ISO text from postgres (`::text`), money and fractions are
// NUMERIC strings; nothing here does arithmetic on either.
import { formatIsoDate, formatNum } from '@/lib/format'

export type AssetClass = 'etf' | 'stock'

// ── the explorer row ────────────────────────────────────────────────────────

/** What the list query selects per active instrument: facts, plus the price-derived columns
 *  LEFT JOINed at EOD (technical_daily, universe_snapshot, ohlcv_daily.close_adj) — NULL until the
 *  price spine has run. NUMERICs arrive as strings. */
export type InstrumentDbRow = {
  symbol: string
  name: string | null
  exchange: string | null
  asset_class: AssetClass
  listing_date: string | null
  cik: string | null
  series_id: string | null
  class_id: string | null
  sector_gics: string | null
  sp500: boolean
  spy_weight: string | null
  price_adj: string | null
  ret_1m: string | null
  ret_3m: string | null
  ret_6m: string | null
  ret_12m: string | null
  rs_3m_spy: string | null
  pos_52w: string | null
  adv_usd: string | null
  in_universe: boolean | null
  /** The ONE reason the snapshot left the row out — universe_snapshot.exclusion_reason, one of
   *  the seven its CHECK allows; null exactly when the row is in (or the snapshot has not run). */
  universe_exclusion: string | null
}

/** A snake_case token as words, for values that arrive as machine tokens (an exclusion reason). */
export const words = (token: string) => token.replace(/_/g, ' ')

export type SecKind = 'cik' | 'series_class' | 'none'

export const SEC_KIND_LABEL: Record<SecKind, string> = { cik: 'CIK', series_class: 'Series + class', none: 'None' }

/** How the SEC knows this instrument: a fund share class (series + class), an issuer (CIK), or not at all. */
export function secIdentityKind(r: Pick<InstrumentDbRow, 'cik' | 'series_id' | 'class_id'>): SecKind {
  if (r.series_id || r.class_id) return 'series_class'
  return r.cik ? 'cik' : 'none'
}

/** The row the explorer ships to the browser: the facts, the derived SEC kind, the price-derived
 *  columns as they are (null-tolerant). The raw SEC ids stay on the detail page. */
export type InstrumentRow = Omit<InstrumentDbRow, 'cik' | 'series_id' | 'class_id' | 'sector_gics'> & {
  sector: string | null
  sec_kind: SecKind
}

export function toInstrumentRow(r: InstrumentDbRow): InstrumentRow {
  return {
    symbol: r.symbol, name: r.name, exchange: r.exchange, asset_class: r.asset_class, listing_date: r.listing_date,
    sp500: r.sp500, sector: r.sector_gics, spy_weight: r.spy_weight, sec_kind: secIdentityKind(r),
    price_adj: r.price_adj, ret_1m: r.ret_1m, ret_3m: r.ret_3m, ret_6m: r.ret_6m, ret_12m: r.ret_12m,
    rs_3m_spy: r.rs_3m_spy, pos_52w: r.pos_52w, adv_usd: r.adv_usd, in_universe: r.in_universe,
    universe_exclusion: r.universe_exclusion,
  }
}

/** The list as cached and shipped: one key list and one array per row — under half the size of
 *  keyed objects, which matters twice: Next's data cache refuses an entry over 2 MB (the keyed
 *  ETF list is 2.2 MB), and the browser receives every row. expandRows restores the row type. */
export type PackedRows = { keys: (keyof InstrumentRow)[]; cells: (string | boolean | null)[][] }

export function packRows(rows: InstrumentRow[]): PackedRows {
  const keys = rows.length ? (Object.keys(rows[0]) as (keyof InstrumentRow)[]) : []
  return { keys, cells: rows.map((r) => keys.map((k) => r[k])) }
}

export function expandRows(p: PackedRows): InstrumentRow[] {
  return p.cells.map((c) => Object.fromEntries(p.keys.map((k, i) => [k, c[i]])) as InstrumentRow)
}

/** The price-derived columns; the list shows them only once at least one row carries a value. */
export const PRICE_KEYS = ['price_adj', 'ret_1m', 'ret_3m', 'ret_6m', 'ret_12m', 'rs_3m_spy', 'pos_52w', 'adv_usd'] as const

export function hasPrices(rows: readonly InstrumentRow[]): boolean {
  return rows.some((r) => PRICE_KEYS.some((k) => r[k] != null))
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
