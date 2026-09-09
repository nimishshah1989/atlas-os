// The threshold rails — "traded at least $10M a day", "volatility at most 25 percent" — on REAL
// board rows.
//
// PROVENANCE. Every row below was read out of the live board's own payload at
// https://global.jslwealth.in/etfs on 2026-09-09, scored for EOD 2026-09-08: six of the 1,652
// funds that carry both a score and a full set of price measures, chosen as the extremes and the
// middle of the traded-value distribution (SPY at $33.7bn a day down to IBTQ at $1.0M). Nothing is
// rounded and nothing is invented — these are the numbers on the screen (rule #0).
//
// THE ONE RULE THAT MATTERS. A row whose number is MISSING must never pass a threshold. "Volatility
// at most 15 percent" is a question about measured volatility, and a fund nobody has measured is
// not a calm fund. Letting nulls through would put exactly the unmeasured funds at the top of the
// safest screen anyone runs.
import { describe, expect, it } from 'vitest'
import { ALL, applyFilters, facetCounts, parseState, serialiseState, type FacetGroup, type SortState } from '@/lib/explorer'
import { toInstrumentRow, type InstrumentDbRow, type InstrumentRow } from '@/lib/facts'

const BASE = {
  asset_class: 'etf',
  sector_gics: null,
  universe_exclusion: null,
  in_universe: true,
  leveraged: false,
  inverse: false,
  hedged: false,
  class_status: 'auto',
  country: null,
  region: null,
  technical: null,
  peer_rank: null,
  peer_n: null,
  pos_52w: null,
  rs_3m_spy: null,
  rs_6m_spy: null,
} as const

const RAW: InstrumentDbRow[] = [
  { ...BASE, symbol: 'SPY', name: 'State Street SPDR S&P 500 ETF Trust', strategy: 'broad_market', class_asset_class: 'equity', composite: '74.55', conviction_tier: 'HIGH', peer_group: 'equity:broad_market', lenses_active: 3, composite_decile: 7, rs_12m_spy: '0.00000000', adv_usd: '33721055202.1800', vol_ann: '0.12796628', mdd_12m: '-0.08879991' },
  { ...BASE, symbol: 'IWM', name: 'iShares Russell 2000 ETF', strategy: 'broad_market', class_asset_class: 'equity', composite: '90.45', conviction_tier: 'HIGH', peer_group: 'equity:broad_market', lenses_active: 3, composite_decile: 10, rs_12m_spy: '0.04691471', adv_usd: '5881301779.6000', vol_ann: '0.18755545', mdd_12m: '-0.11028399' },
  { ...BASE, symbol: 'XPH', name: 'SPDR S&P Pharmaceuticals ETF', strategy: null, class_asset_class: null, composite: '82.27', conviction_tier: 'HIGH', peer_group: 'unclassified:unclassified', lenses_active: 3, composite_decile: 10, rs_12m_spy: '0.24654311', adv_usd: '6619419.3600', vol_ann: '0.22853817', mdd_12m: '-0.11974610' },
  { ...BASE, symbol: 'FDD', name: 'First Trust STOXX European Select Dividend Index Fund', strategy: 'dividend_income', class_asset_class: 'equity', composite: '83.86', conviction_tier: 'HIGH', peer_group: 'equity:dividend_income', lenses_active: 3, composite_decile: 9, rs_12m_spy: '0.13444258', adv_usd: '2296258.0750', vol_ann: '0.15312524', mdd_12m: '-0.09393774' },
  { ...BASE, symbol: 'XMLV', name: 'Invesco S&P MidCap Low Volatility ETF', strategy: 'factor', class_asset_class: 'equity', composite: '48.91', conviction_tier: 'MEDIUM', peer_group: 'equity:factor', lenses_active: 3, composite_decile: 1, rs_12m_spy: '-0.08786587', adv_usd: '1008121.0768', vol_ann: '0.10503199', mdd_12m: '-0.07033732' },
  { ...BASE, symbol: 'IBTQ', name: 'iShares iBonds Dec 2033 Term Treasury ETF', strategy: 'fixed_income', class_asset_class: 'fixed_income', composite: '19.32', conviction_tier: 'BELOW_THRESHOLD', peer_group: 'fixed_income:fixed_income', lenses_active: 3, composite_decile: 1, rs_12m_spy: '-0.17257728', adv_usd: '1001463.9469', vol_ann: '0.04733420', mdd_12m: '-0.04291339' },
  // The state every producer starts in, and the state this file exists to police: listed, in the
  // universe, and measured by nobody.
  { ...BASE, symbol: 'NEWF', name: 'A fund the price spine has not reached', strategy: null, class_asset_class: null, class_status: null, composite: null, conviction_tier: null, peer_group: null, lenses_active: null, composite_decile: null, rs_12m_spy: null, adv_usd: null, vol_ann: null, mdd_12m: null },
]

const ROWS: InstrumentRow[] = RAW.map(toInstrumentRow)
const num = (s: string | null): number | null => (s == null || s === '' ? null : Number(s))

const ADV: FacetGroup<InstrumentRow> = {
  key: 'adv', label: 'Traded a day, at least', kind: 'min',
  value: (r) => r.adv_usd ?? 'none', numeric: (r) => num(r.adv_usd),
  options: ['1000000', '10000000', '50000000', '250000000'], default: ALL,
}
const VOL: FacetGroup<InstrumentRow> = {
  key: 'vol', label: 'Volatility a year, at most', kind: 'max',
  value: (r) => r.vol_ann ?? 'none', numeric: (r) => num(r.vol_ann),
  options: ['0.15', '0.25', '0.40'], default: ALL,
}
const MDD: FacetGroup<InstrumentRow> = {
  key: 'mdd', label: 'Worst 12m fall, at most', kind: 'max',
  value: (r) => r.mdd_12m ?? 'none',
  numeric: (r) => { const v = num(r.mdd_12m); return v == null ? null : Math.abs(v) },
  options: ['0.10', '0.20', '0.35', '0.50'], default: ALL,
}
const RS: FacetGroup<InstrumentRow> = {
  key: 'rs', label: 'Beating the S&P over 12m by', kind: 'min',
  value: (r) => r.rs_12m_spy ?? 'none', numeric: (r) => num(r.rs_12m_spy),
  options: ['0', '0.10', '0.25'], default: ALL,
}
const GROUPS = [ADV, VOL, MDD, RS]
const BY_SYMBOL: SortState = { key: 'symbol', dir: 'asc' }

const state = (qs: string) => parseState(new URLSearchParams(qs), GROUPS, BY_SYMBOL)
const shown = (qs: string) => applyFilters(ROWS, state(qs), GROUPS).map((r) => r.symbol).sort()

describe('an unmeasured fund never passes a threshold', () => {
  it('shows everything, NEWF included, until a threshold is set', () => {
    expect(shown('')).toEqual(['FDD', 'IBTQ', 'IWM', 'NEWF', 'SPY', 'XMLV', 'XPH'])
  })

  it('drops the unmeasured fund from a liquidity FLOOR', () => {
    expect(shown('adv=10000000')).toEqual(['IWM', 'SPY'])
    expect(shown('adv=10000000')).not.toContain('NEWF')
  })

  it('drops it from a volatility CEILING too — the direction that would flatter it', () => {
    // The trap: a "max" rail could let nulls through as "not above the limit". IBTQ at 4.7 percent,
    // XMLV at 10.5 and SPY at 12.8 are genuinely calm; NEWF is merely unmeasured, and must not sit
    // beside them.
    expect(shown('vol=0.15')).toEqual(['IBTQ', 'SPY', 'XMLV'])
    expect(shown('vol=0.25')).toEqual(['FDD', 'IBTQ', 'IWM', 'SPY', 'XMLV', 'XPH'])
  })

  it('reads a drawdown by its DEPTH, so the sign of a fall cannot invert the rail', () => {
    // mdd_12m is negative. Compared raw, "at most 0.20" would keep every fund ever (all are < 0.2)
    // and the rail would filter nothing while looking as if it worked.
    expect(shown('mdd=0.20')).toEqual(['FDD', 'IBTQ', 'IWM', 'SPY', 'XMLV', 'XPH'])
    expect(shown('mdd=0.10')).toEqual(['FDD', 'IBTQ', 'SPY', 'XMLV'])
  })

  it('floors relative strength at the benchmark itself', () => {
    // SPY's rs_12m_spy is exactly 0.00000000 — it IS the benchmark — so a "beating it by any
    // margin" floor keeps it, and a 10-point floor does not.
    expect(shown('rs=0')).toEqual(['FDD', 'IWM', 'SPY', 'XPH'])
    expect(shown('rs=0.10')).toEqual(['FDD', 'XPH'])
    expect(shown('rs=0.25')).toEqual([])
  })
})

describe('the rails compose, count and survive the URL', () => {
  it('a liquidity floor and a volatility ceiling together are an AND', () => {
    expect(shown('adv=1000000&vol=0.15')).toEqual(['IBTQ', 'SPY', 'XMLV'])
    expect(shown('adv=10000000&vol=0.15')).toEqual(['SPY'])
  })

  it('each option counts the rows it would KEEP, not the rows that share a value', () => {
    // A threshold's count answers "how many survive if I pick this", which is the question the
    // reader is actually asking. Counting rows per exact value would print 1 beside every option.
    const counts = facetCounts(ROWS, state(''), GROUPS)
    expect(counts.adv).toEqual({ '1000000': 6, '10000000': 2, '50000000': 2, '250000000': 2, [ALL]: 7 })
    expect(counts.vol).toEqual({ '0.15': 3, '0.25': 6, '0.40': 6, [ALL]: 7 })
  })

  it('counts each rail under the OTHER rails, so a choice never hides its alternatives', () => {
    const counts = facetCounts(ROWS, state('vol=0.15'), GROUPS)
    expect(counts.adv['1000000']).toBe(3) // IBTQ, SPY and XMLV are what the volatility ceiling left
    expect(counts.vol['0.25']).toBe(6) // its OWN rail still counts against everything else
  })

  it('round-trips through the query string and falls back on a value it does not offer', () => {
    const s = state('adv=10000000&vol=0.15')
    expect(serialiseState(s, GROUPS, BY_SYMBOL)).toBe('adv=10000000&vol=0.15')
    expect(state('adv=7').facets.adv).toEqual([ALL]) // not one of the offered floors
    expect(state('').facets.adv).toEqual([ALL])
  })
})
