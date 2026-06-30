import { describe, it, expect } from 'vitest'
import { aggregateMargins, perConstituentMargins, type RawFin } from '../sectorFin'

// REAL latest-consolidated quarterly financials pulled from
// foundation_staging.financials_quarterly (snapshot 2026-06-29) for six Chemicals
// constituents — NO synthetic inputs (rule #0). EIDPARRY is loss-making (pat < 0),
// so this fixture exercises the outlier-robustness that the old simple-average-of-
// ratios aggregation lacked (a micro-cap with a −423 stored margin dragged the whole
// universe average negative). Revenue-weighting nets the loss against revenue instead.
const CHEM: RawFin[] = [
  { symbol: 'UPL', revenue: 18335, ebitda: 3481, pat: 1294 },
  { symbol: 'EIDPARRY', revenue: 7882, ebitda: 611, pat: -287 },
  { symbol: 'GODREJIND', revenue: 7694, ebitda: 1167, pat: 841 },
  { symbol: 'COROMANDEL', revenue: 6004, ebitda: 488, pat: 115 },
  { symbol: 'PIDILITIND', revenue: 3583, ebitda: 831, pat: 584 },
  { symbol: 'SUPREMEIND', revenue: 3528, ebitda: 623, pat: 434 },
]
// Σrevenue = 47026, Σebitda = 7201, Σpat = 2981.

describe('aggregateMargins (revenue-weighted, %)', () => {
  it('weights margins by revenue — Σebitda/Σrevenue, not the average of per-stock ratios', () => {
    const a = aggregateMargins(CHEM)
    expect(a.n).toBe(6)
    expect(a.ebitda_margin).toBeCloseTo(15.313, 2) // 100*7201/47026
    expect(a.net_margin).toBeCloseTo(6.339, 2) // 100*2981/47026
  })

  it('reports the share of constituents that are profitable (PAT > 0)', () => {
    // 5 of 6 profitable (EIDPARRY loss-making).
    expect(aggregateMargins(CHEM).pct_profitable).toBeCloseTo(83.333, 2)
  })

  it('is robust to a small-denominator loss-maker (the old simple average was not)', () => {
    // A micro-cap with tiny revenue and a large loss barely moves the weighted margin,
    // but would have tanked an unweighted average of ratios.
    const withOutlier: RawFin[] = [...CHEM, { symbol: 'MICRO', revenue: 5, ebitda: -40, pat: -60 }]
    const a = aggregateMargins(withOutlier)
    expect(a.ebitda_margin).toBeCloseTo(15.226, 2) // 100*(7201-40)/(47026+5) — barely moves off 15.31
    expect(a.ebitda_margin!).toBeGreaterThan(14) // nowhere near the −42% the old avg produced
  })

  it('excludes zero/negative-revenue rows from the denominator and from n', () => {
    const a = aggregateMargins([
      { symbol: 'A', revenue: 1000, ebitda: 200, pat: 100 },
      { symbol: 'ZERO', revenue: 0, ebitda: 5, pat: 5 },
      { symbol: 'NULLREV', revenue: null, ebitda: 5, pat: 5 },
    ])
    expect(a.n).toBe(1)
    expect(a.ebitda_margin).toBeCloseTo(20, 6)
  })

  it('returns nulls when no constituent has revenue', () => {
    const a = aggregateMargins([{ symbol: 'X', revenue: null, ebitda: 10, pat: 5 }])
    expect(a).toEqual({ n: 0, ebitda_margin: null, net_margin: null, pct_profitable: null })
  })
})

describe('perConstituentMargins (the within-sector drill)', () => {
  it('computes each stock’s own margin and sorts strongest EBITDA margin first', () => {
    const rows = perConstituentMargins(CHEM)
    expect(rows.map((r) => r.symbol)).toEqual([
      'PIDILITIND', 'UPL', 'SUPREMEIND', 'GODREJIND', 'COROMANDEL', 'EIDPARRY',
    ])
    const upl = rows.find((r) => r.symbol === 'UPL')!
    expect(upl.ebitda_margin).toBeCloseTo(18.985, 2) // 100*3481/18335
    expect(upl.net_margin).toBeCloseTo(7.058, 2)
    expect(upl.profitable).toBe(true)
    expect(rows.find((r) => r.symbol === 'EIDPARRY')!.profitable).toBe(false)
  })

  it('nulls a stock’s margins when revenue is missing and sorts it last', () => {
    const rows = perConstituentMargins([
      { symbol: 'A', revenue: 1000, ebitda: 200, pat: 100 },
      { symbol: 'NOREV', revenue: null, ebitda: 50, pat: 25 },
    ])
    expect(rows[0].symbol).toBe('A')
    expect(rows[1].symbol).toBe('NOREV')
    expect(rows[1].ebitda_margin).toBeNull()
    expect(rows[1].profitable).toBeNull()
  })
})
