// The explorer's pure pieces: URL state, facets with counts, sort, search. The rows are REAL
// instrument_master rows copied verbatim from the scratch database atlas_p1_base (psql, 2026-09-06),
// carrying the REAL universe_snapshot verdicts of EOD 2026-09-03 (13,155 active instruments, floor
// $1,000,000). Every score column is null because etf_scores_daily held no rows on that date —
// which is the state the board must render, not a stand-in for one it does not have (rule #0).
import { describe, expect, it } from 'vitest'
import {
  ALL,
  applyFilters,
  facetCounts,
  facetValues,
  matchesQuery,
  ON,
  parseState,
  serialiseState,
  sortRows,
  type FacetGroup,
  type SortState,
} from '@/lib/explorer'
import { toInstrumentRow, type InstrumentDbRow, type InstrumentRow } from '@/lib/facts'
import { orderBy, universeSide } from '@/lib/scores'

const UNSCORED = {
  strategy: null, theme: null, class_asset_class: null, leveraged: null, inverse: null, hedged: null,
  class_status: null, country: null, region: null,
  composite: null, technical: null, conviction_tier: null, peer_group: null, lenses_active: null,
  composite_decile: null, peer_rank: null, peer_n: null,
  rs_3m_spy: null, rs_6m_spy: null, rs_12m_spy: null, pos_52w: null, adv_usd: null,
  vol_ann: null, mdd_12m: null,
} as const

// select m.symbol, m.name, m.asset_class, m.sector_gics, u.in_universe, u.exclusion_reason
// from atlas_global.instrument_master m
// left join atlas_global.universe_snapshot u on … and u.date = '2026-09-03'
// where m.is_active and m.symbol in (…)
const RAW: InstrumentDbRow[] = [
  { symbol: 'QQQ', name: 'Invesco QQQ Trust, Series 1', asset_class: 'etf', sector_gics: null, in_universe: true, universe_exclusion: null, ...UNSCORED },
  { symbol: 'SPY', name: 'State Street SPDR S&P 500 ETF Trust', asset_class: 'etf', sector_gics: null, in_universe: true, universe_exclusion: null, ...UNSCORED },
  { symbol: 'TQQQ', name: 'ProShares UltraPro QQQ', asset_class: 'etf', sector_gics: null, in_universe: false, universe_exclusion: 'leveraged', ...UNSCORED, leveraged: true, inverse: false },
  { symbol: 'SH', name: 'ProShares Short S&P500', asset_class: 'etf', sector_gics: null, in_universe: false, universe_exclusion: 'inverse', ...UNSCORED, leveraged: false, inverse: true },
  { symbol: 'ILCB', name: 'iShares Morningstar Large-Cap ETF', asset_class: 'etf', sector_gics: null, in_universe: false, universe_exclusion: 'below_floor', ...UNSCORED, leveraged: false, inverse: false },
  { symbol: 'AAPL', name: 'Apple Inc. - Common Stock', asset_class: 'stock', sector_gics: 'Information Technology', in_universe: true, universe_exclusion: null, ...UNSCORED },
  { symbol: 'BRK.B', name: 'Berkshire Hathaway Inc. New Common Stock', asset_class: 'stock', sector_gics: 'Financials', in_universe: true, universe_exclusion: null, ...UNSCORED },
  { symbol: 'AA', name: 'Alcoa Corporation Common Stock', asset_class: 'stock', sector_gics: null, in_universe: false, universe_exclusion: 'not_sp500', ...UNSCORED },
]
const ROWS: InstrumentRow[] = RAW.map(toInstrumentRow)
const ETFS = ROWS.filter((r) => r.asset_class === 'etf')
const STOCKS = ROWS.filter((r) => r.asset_class === 'stock')

// The board's own three group kinds, as InstrumentExplorer declares them.
const UNIVERSE: FacetGroup<InstrumentRow> = {
  key: 'universe', label: 'Universe', kind: 'one', value: universeSide,
  options: ['in'], labels: { in: 'The board’s universe', [ALL]: 'Everything listed' }, default: 'in',
}
const SECTOR: FacetGroup<InstrumentRow> = {
  key: 'sector', label: 'GICS sector', kind: 'any', value: (r) => r.sector ?? 'none',
}
const GEARED: FacetGroup<InstrumentRow> = {
  key: 'geared', label: 'Leveraged funds', kind: 'flag', value: (r) => (r.leveraged ? ON : 'off'),
}
const GROUPS = [UNIVERSE, SECTOR, GEARED]
const BY_SYMBOL: SortState = { key: 'symbol', dir: 'asc' }

describe('parseState / serialiseState', () => {
  it('defaults: the universe, no sector chosen, geared funds off', () => {
    const s = parseState(new URLSearchParams(''), GROUPS, BY_SYMBOL)
    expect(s).toEqual({ q: '', sort: BY_SYMBOL, facets: { universe: ['in'], sector: [], geared: [] } })
    expect(serialiseState(s, GROUPS, BY_SYMBOL)).toBe('')
  })
  it('reads repeated keys, a "-" sort prefix, and round-trips', () => {
    const p = new URLSearchParams('universe=all&sector=Financials&geared=on&sort=-composite&q=apple')
    const s = parseState(p, GROUPS, BY_SYMBOL)
    expect(s).toEqual({
      q: 'apple', sort: { key: 'composite', dir: 'desc' },
      facets: { universe: [ALL], sector: ['Financials'], geared: [ON] },
    })
    expect(serialiseState(s, GROUPS, BY_SYMBOL)).toBe('universe=all&sector=Financials&geared=on&sort=-composite&q=apple')
  })
  it('falls back to the default for a "one" group given an unknown value', () => {
    expect(parseState(new URLSearchParams('universe=maybe'), GROUPS, BY_SYMBOL).facets.universe).toEqual(['in'])
  })
})

describe('matchesQuery', () => {
  it('matches a symbol prefix or a name substring, case-insensitively', () => {
    expect(matchesQuery(ROWS[5], 'aa')).toBe(true) // AAPL
    expect(matchesQuery(ROWS[5], 'apple')).toBe(true)
    expect(matchesQuery(ROWS[5], 'xyz')).toBe(false)
    expect(matchesQuery(ROWS[1], '')).toBe(true)
  })
  it("accepts the dash spelling of a dotted share class (Stooq's BRK-B is instrument_master's BRK.B)", () => {
    expect(matchesQuery(ROWS[6], 'brk-b')).toBe(true)
  })
})

// The defect this chunk exists to fix: the board listed all 5,655 funds because it ignored a flag
// the nightly already writes. These are the real verdicts of EOD 2026-09-03.
describe('the universe toggle', () => {
  it('shows only the in-universe set by default', () => {
    const s = parseState(new URLSearchParams(''), GROUPS, BY_SYMBOL)
    expect(applyFilters(ETFS, s, GROUPS).map((r) => r.symbol)).toEqual(['QQQ', 'SPY'])
    expect(applyFilters(STOCKS, s, GROUPS).map((r) => r.symbol)).toEqual(['AAPL', 'BRK.B'])
  })
  it('"Everything listed" reveals the rest — nothing is hidden, it is not the default', () => {
    const s = parseState(new URLSearchParams('universe=all&geared=on'), GROUPS, BY_SYMBOL)
    expect(applyFilters(ETFS, s, GROUPS).map((r) => r.symbol)).toEqual(['QQQ', 'SPY', 'TQQQ', 'SH', 'ILCB'])
  })
  it('keeps geared funds out even under "Everything listed" until the toggle is ticked', () => {
    const s = parseState(new URLSearchParams('universe=all'), GROUPS, BY_SYMBOL)
    expect(applyFilters(ETFS, s, GROUPS).map((r) => r.symbol)).toEqual(['QQQ', 'SPY', 'SH', 'ILCB'])
  })
  it('treats a row the snapshot has not marked as out — the explorer only offers the toggle once one is', () => {
    const unmarked = { ...ETFS[0], in_universe: null }
    expect(universeSide(unmarked)).toBe('out')
  })
})

describe('facetCounts', () => {
  it('counts each value under the query and the OTHER groups, so a group never hides its alternatives', () => {
    const s = parseState(new URLSearchParams('universe=all'), GROUPS, BY_SYMBOL)
    const c = facetCounts(ETFS, s, GROUPS)
    // the geared count is what ticking the box would ADD, under the other groups' selections
    expect(c.geared).toEqual({ off: 4, on: 1 })
    // the universe counts honour the geared toggle, which is still off: TQQQ is not in either
    expect(c.universe).toEqual({ in: 2, out: 2, [ALL]: 4 })
  })
})

describe('facetValues', () => {
  it('lists a group’s values most frequent first, the none token last whatever its count', () => {
    expect(facetValues(STOCKS, SECTOR)).toEqual(['Financials', 'Information Technology', 'none'])
  })
})

// Ordering only. No row below is an instrument and no number below is a score for one: the values
// are the SEEDED conviction cut-points of atlas_global.atlas_thresholds (lens_conviction_highest 70,
// _high 58, _medium 45, _watch 30 — scripts/global_market/seed_thresholds.py), used here because a
// comparator needs distinct ordered values and inventing four would be inventing scores.
describe('sortRows over a composite', () => {
  const CUTS = [
    { key: 'watch', composite: '30' },
    { key: 'highest', composite: '70' },
    { key: 'unscored', composite: null },
    { key: 'medium', composite: '45' },
    { key: 'also-unscored', composite: null },
    { key: 'high', composite: '58' },
  ]
  const byComposite = (r: (typeof CUTS)[number]) => orderBy(r.composite)

  it('puts the strongest first and every unscored row last, in ITS OWN incoming order', () => {
    const desc = sortRows(CUTS, { key: 'composite', dir: 'desc' }, byComposite).map((r) => r.key)
    expect(desc).toEqual(['highest', 'high', 'medium', 'watch', 'unscored', 'also-unscored'])
  })
  it('keeps unscored rows last when the sort is reversed — a null is not a zero', () => {
    const asc = sortRows(CUTS, { key: 'composite', dir: 'asc' }, byComposite).map((r) => r.key)
    expect(asc).toEqual(['watch', 'medium', 'high', 'highest', 'unscored', 'also-unscored'])
  })
  it('does not mutate the input', () => {
    sortRows(CUTS, { key: 'composite', dir: 'desc' }, byComposite)
    expect(CUTS.map((r) => r.key)).toEqual(['watch', 'highest', 'unscored', 'medium', 'also-unscored', 'high'])
  })
  it('sorts the real rows by symbol without a score column', () => {
    expect(sortRows(ETFS, BY_SYMBOL, (r) => r.symbol).map((r) => r.symbol)).toEqual(['ILCB', 'QQQ', 'SH', 'SPY', 'TQQQ'])
  })
})
