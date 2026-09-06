// Pure derivations over instrument facts. Every row below is copied VERBATIM from the scratch
// database atlas_p1_base (a clone of prod's atlas_global shape, identity built by build_identity.py
// on 2026-09-04, membership by ingest_index_membership.py, bars by import_stooq.py), read with
// psql on 2026-09-06 — no row is invented (rule #0). The SQL that produced each block is quoted.
import { describe, expect, it } from 'vitest'
import {
  describeBars,
  describeInterval,
  expandRows,
  hasUniverse,
  packRows,
  secIdentityKind,
  SEC_KIND_LABEL,
  toInstrumentRow,
  universeValue,
  type BarsRow,
  type InstrumentDbRow,
} from '@/lib/facts'

// select symbol, name, exchange, asset_class, listing_date, cik, series_id, class_id, sector_gics
// from atlas_global.instrument_master where is_active and symbol in (…)   (+ the EOD membership
// EXISTS and the open ssga weight_frac, as queries/instruments.ts computes them for 2026-09-03)
const SPY: InstrumentDbRow = {
  symbol: 'SPY', name: 'State Street SPDR S&P 500 ETF Trust', exchange: 'NYSEARCA', asset_class: 'etf',
  listing_date: '1993-01-29', cik: '0000884394', series_id: null, class_id: null, sector_gics: null,
  sp500: false, spy_weight: null,
  price_adj: null, ret_1m: null, ret_3m: null, ret_6m: null, ret_12m: null, rs_3m_spy: null, pos_52w: null,
  adv_usd: null, in_universe: null, universe_exclusion: null,
}
const QQQ: InstrumentDbRow = {
  ...SPY, symbol: 'QQQ', name: 'Invesco QQQ Trust, Series 1', exchange: 'NASDAQ', listing_date: '1999-03-10',
  cik: '0001067839', series_id: 'S000101292', class_id: 'C000271435',
}
const AAOG: InstrumentDbRow = {
  ...SPY, symbol: 'AAOG', name: 'Leverage Shares 2X Long AAOI Daily ETF', exchange: 'BATS', listing_date: '2026-05-12',
  cik: null, series_id: null, class_id: null,
}
const AAPL: InstrumentDbRow = {
  ...SPY, symbol: 'AAPL', name: 'Apple Inc. - Common Stock', exchange: 'NASDAQ', asset_class: 'stock',
  listing_date: '1980-12-12', cik: '0000320193', sector_gics: 'Information Technology',
  sp500: true, spy_weight: '0.07219673',
}

describe('secIdentityKind', () => {
  it('is CIK when the SEC knows the issuer but not a fund series/class (SPY is a unit investment trust)', () => {
    expect(secIdentityKind(SPY)).toBe('cik')
    expect(secIdentityKind(AAPL)).toBe('cik')
  })
  it('is series + class for a registered fund share class (QQQ)', () => {
    expect(secIdentityKind(QQQ)).toBe('series_class')
  })
  it('is none when instrument_master carries no SEC identity (AAOG, listed 2026-05-12)', () => {
    expect(secIdentityKind(AAOG)).toBe('none')
  })
  it('has a label for every kind', () => {
    expect(SEC_KIND_LABEL).toEqual({ cik: 'CIK', series_class: 'Series + class', none: 'None' })
  })
})

describe('toInstrumentRow', () => {
  it('keeps the facts, derives the SEC kind, drops the raw SEC ids, and leaves price columns null', () => {
    expect(toInstrumentRow(AAPL)).toEqual({
      symbol: 'AAPL', name: 'Apple Inc. - Common Stock', exchange: 'NASDAQ', asset_class: 'stock',
      listing_date: '1980-12-12', sp500: true, sector: 'Information Technology', spy_weight: '0.07219673',
      sec_kind: 'cik',
      price_adj: null, ret_1m: null, ret_3m: null, ret_6m: null, ret_12m: null, rs_3m_spy: null, pos_52w: null,
      adv_usd: null, in_universe: null, universe_exclusion: null,
    })
    expect(toInstrumentRow(QQQ).sec_kind).toBe('series_class')
  })
})

describe('packRows / expandRows', () => {
  it('round-trips the rows through the packed transport and keeps the key order', () => {
    const rows = [SPY, QQQ, AAPL, AAOG].map(toInstrumentRow)
    const packed = packRows(rows)
    expect(packed.keys[0]).toBe('symbol')
    expect(packed.cells).toHaveLength(4)
    expect(packed.cells[2]).toContain('0.07219673')
    expect(expandRows(packed)).toEqual(rows)
    expect(packRows([])).toEqual({ keys: [], cells: [] })
  })
})

describe('universe', () => {
  // universe_snapshot has no rows in the scratch database: the flag is null on every row today.
  it('is unknown until the snapshot has run, so neither the column nor the facet appears', () => {
    const rows = [AAPL, SPY].map(toInstrumentRow)
    expect(hasUniverse(rows)).toBe(false)
    expect(universeValue(rows[0])).toBe('unknown')
  })
  it('reads in, or the reason the snapshot gave for the exclusion, once it has', () => {
    expect(universeValue({ in_universe: true, universe_exclusion: null })).toBe('in')
    expect(universeValue({ in_universe: false, universe_exclusion: 'below_floor' })).toBe('below_floor')
    expect(universeValue({ in_universe: false, universe_exclusion: null })).toBe('excluded')
    expect(hasUniverse([{ ...toInstrumentRow(SPY), in_universe: false }])).toBe(true)
  })
})

describe('describeInterval', () => {
  // select index_code, effective_from, effective_to, weight_frac, source from atlas_global.index_membership
  // where instrument_id = (FSLR) order by effective_from  — three intervals, the last one open
  const FSLR = [
    { index_code: 'SP500', effective_from: '2016-01-04', effective_to: '2017-03-20', weight_frac: null, source: 'fja05680' },
    { index_code: 'SP500', effective_from: '2022-12-19', effective_to: '2026-09-03', weight_frac: null, source: 'fja05680' },
    { index_code: 'SP500', effective_from: '2026-09-03', effective_to: null, weight_frac: '0.00033385', source: 'ssga' },
  ]

  it('reads a closed interval with its EXCLUSIVE end: the member is out on effective_to', () => {
    expect(describeInterval(FSLR[0])).toEqual({
      open: false, span: 'In from 4 Jan 2016, out on 20 Mar 2017', source: 'fja05680 archive',
    })
  })
  it('marks the open interval', () => {
    expect(describeInterval(FSLR[2])).toEqual({
      open: true, span: 'In from 3 Sep 2026, current member', source: 'SSGA weekly holdings',
    })
  })
  it('shows an unknown source verbatim rather than guessing a label', () => {
    expect(describeInterval({ ...FSLR[1], source: 'manual' }).source).toBe('manual')
  })
})

describe('describeBars', () => {
  // select source, adjustment_source, min(date), max(date), count(*), count(close_adj), count(close_tr)
  // from atlas_global.ohlcv_daily where instrument_id = (SPY) group by 1, 2
  const SPY_BARS: BarsRow = {
    source: 'stooq_csv', adjustment_source: 'stooq:unknown', first_date: '2005-02-25', last_date: '2026-09-03',
    sessions: 5414, adjusted: 0, total_return: 0,
  }

  it('states the source, the count, and that adjusted closes are not yet labelled', () => {
    expect(describeBars(SPY_BARS)).toEqual({
      source: 'Stooq CSV',
      sessions: '5,414',
      adjustment: 'stooq:unknown',
      adjusted: 'adjusted closes not yet labelled (0 of 5,414 bars)',
      totalReturn: 'total-return closes not yet labelled (0 of 5,414 bars)',
    })
  })
  it('says when every bar is adjusted, and when only some are', () => {
    expect(describeBars({ ...SPY_BARS, adjusted: 5414 }).adjusted).toBe('adjusted closes on every bar')
    expect(describeBars({ ...SPY_BARS, adjusted: 12 }).adjusted).toBe('adjusted closes on 12 of 5,414 bars')
  })
  it('names an absent adjustment source in words', () => {
    expect(describeBars({ ...SPY_BARS, adjustment_source: null }).adjustment).toBe('not recorded')
  })
})
