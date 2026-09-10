// The pulse's mappers. Every id and name below is real — the GICS sectors and themes are
// seed_taxonomy.py verbatim, EWJ and EWZ are the real single-country funds for Japan and Brazil —
// and the SCORES are this test's own algebra, because what is under test is an ordering rule and
// an ordering rule is proved by orderings. No number here reaches a page (rule #0).
import { describe, expect, it } from 'vitest'
import { countryItems, sectorItems, themeItems } from '@/lib/rank'
import type { SectorNode } from '@/lib/sectors'
import type { ThemeRow } from '@/lib/themes'
import type { CountryRow } from '@/lib/countries'

const sector = (id: string, name: string, composite: string | null, kids: number): SectorNode => ({
  level: 'sector', id, name, symbol: null, n_children: kids, n_funds: kids, n_scored: kids,
  n_offered: kids,
  aum_usd: null, composite, above_ema200_frac: null,
  rs: { '3m': '0.05', '6m': null, '12m': null },
  rank: null, n_ranked: 0, top_symbol: null, top_name: null,
  n_small: 0, n_geared: 0, n_young: 0, children: [],
})

const theme = (id: string, name: string, median: string | null, scored: number): ThemeRow => ({
  id, name, sector_id: null, sector_name: null, n_funds: scored, n_scored: scored,
  n_offered: scored,
  aum_usd: null, median_composite: median, above_ema200_frac: null,
  top_symbol: null, top_name: null, top_composite: null, top_decile: null,
  rs: { '3m': null, '6m': null, '12m': null },
})

const country = (iso2: string, name: string, composite: string | null, symbol: string | null): CountryRow => ({
  iso2, name, region: null, symbol, fund_name: null, adv_usd_60d_median: null, n_etfs: 1,
  composite, breadth_pct: null, decile: null, rank: null, n_ranked: 0, exclusion_reason: null,
  rs: { '1w': null, '1m': null, '3m': null, '6m': null, '12m': null, '24m': null },
})

describe('sectors → the strip', () => {
  it('ranks strongest first whatever order the board handed over', () => {
    const items = sectorItems([
      sector('materials', 'Materials', '55.0', 6),
      sector('energy', 'Energy', '61.0', 4),
    ])
    expect(items.map((i) => i.id)).toEqual(['energy', 'materials'])
  })

  it('DROPS an unscored sector rather than ranking it last — a ranking of scores has no room for no score', () => {
    const items = sectorItems([sector('energy', 'Energy', '61.0', 4), sector('utilities', 'Utilities', null, 2)])
    expect(items.map((i) => i.id)).toEqual(['energy'])
  })

  it('links to the sector’s own page — the drill-down’s entry, not an anchor on a list', () => {
    const [energy] = sectorItems([sector('energy', 'Energy', '61.0', 4)])
    expect(energy.href).toBe('/sectors/energy')
    expect(energy.meta).toBe('4 themes')
    expect(sectorItems([sector('solar', 'Solar', '5.0', 1)])[0].meta).toBe('1 theme')
  })
})

describe('themes → the strip', () => {
  it('carries the median as the score and the scored count as the context', () => {
    const items = themeItems([
      theme('clean_energy', 'Clean & Renewable Energy', '44.0', 9),
      theme('nuclear_uranium', 'Nuclear & Uranium', '68.0', 12),
    ])
    expect(items.map((i) => [i.id, i.score, i.meta])).toEqual([
      ['nuclear_uranium', '68.0', '12 funds'],
      ['clean_energy', '44.0', '9 funds'],
    ])
    expect(items[0].href).toBe('/themes/nuclear_uranium')
  })
})

describe('markets → the strip', () => {
  it('lower-cases the ISO code for the route and names the representative fund', () => {
    const [jp] = countryItems([country('JP', 'Japan', '58.0', 'EWJ')])
    expect(jp.href).toBe('/countries/jp')
    expect(jp.meta).toBe('EWJ')
  })

  it('drops a market with no representative score', () => {
    expect(countryItems([country('BR', 'Brazil', null, 'EWZ')])).toEqual([])
  })
})
