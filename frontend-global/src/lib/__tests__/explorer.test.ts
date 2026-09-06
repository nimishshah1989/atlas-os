// The explorer's pure pieces: URL state, facets with counts, sort, search. The rows are REAL
// instrument_master rows copied verbatim from the scratch database atlas_p1_base (psql, 2026-09-06;
// membership and weight as of EOD 2026-09-03, price columns NULL because technical_daily and
// universe_snapshot hold no rows there yet). Nothing is invented (rule #0).
import { describe, expect, it } from 'vitest'
import {
  applyFilters,
  facetCounts,
  facetValues,
  matchesQuery,
  parseState,
  serialiseState,
  sortRows,
  type FacetGroup,
  type SortState,
} from '@/lib/explorer'
import { toInstrumentRow, type InstrumentDbRow, type InstrumentRow } from '@/lib/facts'

const NULL_PRICES = {
  price_adj: null, ret_1m: null, ret_3m: null, ret_6m: null, ret_12m: null, rs_3m_spy: null, pos_52w: null,
  adv_usd: null, in_universe: null, universe_exclusion: null,
} as const

// select symbol, name, exchange, asset_class, listing_date, cik, series_id, class_id, sector_gics, <sp500 at
// EOD>, <open ssga weight_frac> from atlas_global.instrument_master where is_active and symbol in (…)
const RAW: InstrumentDbRow[] = [
  { symbol: 'QQQ', name: 'Invesco QQQ Trust, Series 1', exchange: 'NASDAQ', asset_class: 'etf', listing_date: '1999-03-10', cik: '0001067839', series_id: 'S000101292', class_id: 'C000271435', sector_gics: null, sp500: false, spy_weight: null, ...NULL_PRICES },
  { symbol: 'SPY', name: 'State Street SPDR S&P 500 ETF Trust', exchange: 'NYSEARCA', asset_class: 'etf', listing_date: '1993-01-29', cik: '0000884394', series_id: null, class_id: null, sector_gics: null, sp500: false, spy_weight: null, ...NULL_PRICES },
  { symbol: 'VOO', name: 'Vanguard S&P 500 ETF', exchange: 'NYSEARCA', asset_class: 'etf', listing_date: '2010-09-09', cik: '0000036405', series_id: 'S000002839', class_id: 'C000092055', sector_gics: null, sp500: false, spy_weight: null, ...NULL_PRICES },
  { symbol: 'XLK', name: 'State Street Technology Select Sector SPDR ETF', exchange: 'NYSEARCA', asset_class: 'etf', listing_date: '1998-12-22', cik: '0001064641', series_id: 'S000006415', class_id: 'C000017601', sector_gics: null, sp500: false, spy_weight: null, ...NULL_PRICES },
  { symbol: 'AAOG', name: 'Leverage Shares 2X Long AAOI Daily ETF', exchange: 'BATS', asset_class: 'etf', listing_date: '2026-05-12', cik: null, series_id: null, class_id: null, sector_gics: null, sp500: false, spy_weight: null, ...NULL_PRICES },
  { symbol: 'AAPL', name: 'Apple Inc. - Common Stock', exchange: 'NASDAQ', asset_class: 'stock', listing_date: '1980-12-12', cik: '0000320193', series_id: null, class_id: null, sector_gics: 'Information Technology', sp500: true, spy_weight: '0.07219673', ...NULL_PRICES },
  { symbol: 'BRK.B', name: 'Berkshire Hathaway Inc. New Common Stock', exchange: 'NYSE', asset_class: 'stock', listing_date: '1996-05-09', cik: '0001067983', series_id: null, class_id: null, sector_gics: 'Financials', sp500: true, spy_weight: '0.01395152', ...NULL_PRICES },
  { symbol: 'ABR$D', name: 'Arbor Realty Trust 6.375% Series D Cumulative Redeemable Preferred Stock, Liquidation Preference $25.00 per Share', exchange: 'NYSE', asset_class: 'stock', listing_date: '2021-05-26', cik: '0001253986', series_id: null, class_id: null, sector_gics: null, sp500: false, spy_weight: null, ...NULL_PRICES },
  { symbol: 'AIIA.R', name: 'AI Infrastructure Acquisition Corp. Rights, each entitling the holder to receive one-fifth (1/5) of one Class A Ordinary Share', exchange: 'NYSE', asset_class: 'stock', listing_date: '2025-11-24', cik: null, series_id: null, class_id: null, sector_gics: null, sp500: false, spy_weight: null, ...NULL_PRICES },
]
const ROWS: InstrumentRow[] = RAW.map(toInstrumentRow)
const STOCKS = ROWS.filter((r) => r.asset_class === 'stock')

const GROUPS: FacetGroup<InstrumentRow>[] = [
  { key: 'exchange', label: 'Exchange', kind: 'any', value: (r) => r.exchange ?? 'none' },
  { key: 'sp500', label: 'S&P 500', kind: 'one', value: (r) => (r.sp500 ? 'member' : 'other'), options: ['member', 'other'], default: 'member' },
  { key: 'sec', label: 'SEC identity', kind: 'any', value: (r) => r.sec_kind },
]
const BY_SYMBOL: SortState = { key: 'symbol', dir: 'asc' }
const sortValue = (r: InstrumentRow, key: string) =>
  key === 'listed' ? r.listing_date : key === 'weight' ? (r.spy_weight == null ? null : Number(r.spy_weight)) : r.symbol

describe('parseState / serialiseState', () => {
  it('defaults: empty query, default sort, "one" groups on their default, "any" groups unselected', () => {
    const s = parseState(new URLSearchParams(''), GROUPS, BY_SYMBOL)
    expect(s).toEqual({ q: '', sort: BY_SYMBOL, facets: { exchange: [], sp500: ['member'], sec: [] } })
    expect(serialiseState(s, GROUPS, BY_SYMBOL)).toBe('')
  })
  it('reads repeated keys, a "-" sort prefix, and round-trips', () => {
    const p = new URLSearchParams('exchange=NYSE&exchange=NASDAQ&sp500=all&sort=-listed&q=apple')
    const s = parseState(p, GROUPS, BY_SYMBOL)
    expect(s).toEqual({
      q: 'apple', sort: { key: 'listed', dir: 'desc' }, facets: { exchange: ['NYSE', 'NASDAQ'], sp500: ['all'], sec: [] },
    })
    expect(serialiseState(s, GROUPS, BY_SYMBOL)).toBe('exchange=NYSE&exchange=NASDAQ&sp500=all&sort=-listed&q=apple')
  })
  it('falls back to the default for a "one" group given an unknown value', () => {
    expect(parseState(new URLSearchParams('sp500=maybe'), GROUPS, BY_SYMBOL).facets.sp500).toEqual(['member'])
  })
})

describe('matchesQuery', () => {
  it('matches a symbol prefix or a name substring, case-insensitively', () => {
    expect(matchesQuery(ROWS[5], 'aa')).toBe(true) // AAPL
    expect(matchesQuery(ROWS[5], 'apple')).toBe(true)
    expect(matchesQuery(ROWS[5], 'xyz')).toBe(false) // not a prefix, not in the name
    expect(matchesQuery(ROWS[1], '')).toBe(true)
  })
  it("accepts the dash spelling of a dotted share class (Stooq's BRK-B is instrument_master's BRK.B)", () => {
    expect(matchesQuery(ROWS[6], 'brk-b')).toBe(true)
  })
})

describe('applyFilters', () => {
  it('applies the S&P default on stocks: the two members at EOD 2026-09-03', () => {
    const s = parseState(new URLSearchParams(''), GROUPS, BY_SYMBOL)
    expect(applyFilters(STOCKS, s, GROUPS).map((r) => r.symbol)).toEqual(['AAPL', 'BRK.B'])
  })
  it('"all" lifts a "one" group; "any" groups OR their values and AND across groups', () => {
    const s = parseState(new URLSearchParams('sp500=all&exchange=NYSE&sec=none'), GROUPS, BY_SYMBOL)
    expect(applyFilters(STOCKS, s, GROUPS).map((r) => r.symbol)).toEqual(['AIIA.R'])
  })
  it('combines the query with the facets', () => {
    const s = parseState(new URLSearchParams('sp500=all&q=arbor'), GROUPS, BY_SYMBOL)
    expect(applyFilters(STOCKS, s, GROUPS).map((r) => r.symbol)).toEqual(['ABR$D'])
  })
})

describe('facetCounts', () => {
  it('counts each value under the query and the OTHER groups, so a group never hides its own alternatives', () => {
    const s = parseState(new URLSearchParams('exchange=NASDAQ'), GROUPS, BY_SYMBOL)
    const c = facetCounts(STOCKS, s, GROUPS)
    // exchange counts ignore the exchange selection but honour sp500=member
    expect(c.exchange).toEqual({ NASDAQ: 1, NYSE: 1 })
    // sp500 counts honour exchange=NASDAQ: AAPL is the only NASDAQ stock here; "all" is the total
    expect(c.sp500).toEqual({ member: 1, all: 1 })
    expect(c.sec).toEqual({ cik: 1 })
  })
})

describe('facetValues', () => {
  it('lists a group’s values most frequent first, the none token last whatever its count', () => {
    expect(facetValues(STOCKS, GROUPS[0])).toEqual(['NYSE', 'NASDAQ'])
    const sector: FacetGroup<InstrumentRow> = { key: 'sector', label: 'Sector', kind: 'any', value: (r) => r.sector ?? 'none' }
    expect(facetValues(STOCKS, sector)).toEqual(['Financials', 'Information Technology', 'none'])
  })
})

describe('sortRows', () => {
  it('sorts strings and numbers, nulls last in both directions, without mutating the input', () => {
    const asc = sortRows(STOCKS, { key: 'weight', dir: 'asc' }, sortValue).map((r) => r.symbol)
    expect(asc).toEqual(['BRK.B', 'AAPL', 'ABR$D', 'AIIA.R'])
    const desc = sortRows(STOCKS, { key: 'weight', dir: 'desc' }, sortValue).map((r) => r.symbol)
    expect(desc).toEqual(['AAPL', 'BRK.B', 'ABR$D', 'AIIA.R'])
    expect(STOCKS.map((r) => r.symbol)).toEqual(['AAPL', 'BRK.B', 'ABR$D', 'AIIA.R'])
  })
  it('sorts ISO dates as text', () => {
    const oldest = sortRows(ROWS, { key: 'listed', dir: 'asc' }, sortValue)[0]
    expect(oldest.symbol).toBe('AAPL')
  })
})
