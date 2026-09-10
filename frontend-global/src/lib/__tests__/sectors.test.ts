// The sector drill-down's pure half: how three levels are ordered under one sort, and what a heat
// tint is cut against.
//
// WHAT IS REAL HERE AND WHAT IS THE TEST'S OWN. Every id, name and parentage below is real: the
// GICS sectors and the 32 themes with their level-1 parents are `scripts/global_market/
// seed_taxonomy.py` verbatim, and URA, NLR, ICLN, TAN are real US-listed funds those themes
// classify. The SCORES are the test's own algebra — this file tests a comparator, and a comparator
// is proved by the orderings it must produce, not by a market. No number here reaches a page: the
// board's own figures come from `queries/sectors.ts` over `etf_scores_daily` (rule #0).
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'
import { scoreSpan, sortTree, valueOf, type SectorNode } from '@/lib/sectors'
import { unscoredReasons } from '@/components/sectors/Unscored'

const node = (
  id: string,
  name: string,
  level: SectorNode['level'],
  composite: string | null,
  extra: Partial<SectorNode> = {},
): SectorNode => ({
  level,
  id,
  name,
  symbol: level === 'fund' ? id : null,
  n_children: 0,
  n_funds: 1,
  n_scored: composite == null ? 0 : 1,
  n_offered: composite == null ? 0 : 1,
  aum_usd: null,
  composite,
  above_ema200_frac: null,
  rs: { '3m': null, '6m': null, '12m': null },
  rank: null,
  n_ranked: 0,
  top_symbol: null,
  top_name: null,
  n_small: 0,
  n_geared: 0,
  n_young: 0,
  children: [],
  ...extra,
})

// energy → nuclear_uranium → {URA, NLR}; energy → clean_energy → {ICLN, TAN}. The parentage is
// seed_taxonomy.py's: both themes hang off the level-1 `energy` sector, not off a sub-sector.
const tree = (): SectorNode[] => [
  node('energy', 'Energy', 'sector', '61.0', {
    n_children: 2,
    children: [
      node('nuclear_uranium', 'Nuclear & Uranium', 'theme', '68.0', {
        n_children: 2,
        children: [node('URA', 'Global X Uranium', 'fund', '71.0'), node('NLR', 'VanEck Uranium and Nuclear', 'fund', '64.0')],
      }),
      node('clean_energy', 'Clean & Renewable Energy', 'theme', '44.0', {
        n_children: 2,
        children: [node('ICLN', 'iShares Global Clean Energy', 'fund', '46.0'), node('TAN', 'Invesco Solar', 'fund', null)],
      }),
    ],
  }),
  node('materials', 'Materials', 'sector', '55.0', { n_children: 0 }),
]

const names = (rows: SectorNode[]): string[] => rows.flatMap((r) => [r.id, ...names(r.children)])

describe('one sort, all the way down', () => {
  it('orders every level by the key the reader chose, not just the top one', () => {
    expect(names(sortTree(tree(), 'composite', -1))).toEqual([
      'energy', 'nuclear_uranium', 'URA', 'NLR', 'clean_energy', 'ICLN', 'TAN', 'materials',
    ])
  })

  it('reverses every level together — a drill-down whose children keep their own order is two tables', () => {
    expect(names(sortTree(tree(), 'composite', 1))).toEqual([
      'materials', 'energy', 'clean_energy', 'ICLN', 'TAN', 'nuclear_uranium', 'NLR', 'URA',
    ])
  })

  it('KEEPS an unscored row last ascending too — unmeasured is not lowest (rule #0)', () => {
    const rows = sortTree(tree(), 'composite', 1)
    const clean = rows[1].children[0]
    expect(clean.id).toBe('clean_energy')
    // TAN carries no composite, so it sits behind ICLN whichever way the column is pointed.
    expect(clean.children.map((c) => c.id)).toEqual(['ICLN', 'TAN'])
  })

  it('does not mutate the tree it was handed — the eod cache hands the same object to every request', () => {
    const original = tree()
    const before = names(original)
    sortTree(original, 'composite', 1)
    expect(names(original)).toEqual(before)
  })

  it('sorts by name as text, in the direction asked', () => {
    expect(sortTree(tree(), 'name', 1).map((r) => r.id)).toEqual(['energy', 'materials'])
    expect(sortTree(tree(), 'name', -1).map((r) => r.id)).toEqual(['materials', 'energy'])
  })
})

describe('what a value is worth to the comparator', () => {
  it('reads a NUMERIC string as a number, and an absent one as nothing at all', () => {
    expect(valueOf(node('URA', 'Global X Uranium', 'fund', '71.0'), 'composite')).toBe(71)
    expect(valueOf(node('TAN', 'Invesco Solar', 'fund', null), 'composite')).toBeNull()
  })

  it('reads relative strength per window', () => {
    const n = node('URA', 'Global X Uranium', 'fund', '71.0', {
      rs: { '3m': '0.184', '6m': null, '12m': '-0.05' },
    })
    expect(valueOf(n, '3m')).toBeCloseTo(0.184)
    expect(valueOf(n, '6m')).toBeNull()
    expect(valueOf(n, '12m')).toBeCloseTo(-0.05)
  })
})

describe('the population a tint is cut against', () => {
  it('spans the scored siblings only', () => {
    expect(scoreSpan(tree())).toEqual({ best: 61, worst: 55 })
  })

  it('is NOTHING when no sibling is scored, so the caller paints no colour rather than a flat one', () => {
    expect(scoreSpan([node('solar', 'Solar', 'theme', null)])).toBeNull()
    expect(scoreSpan([])).toBeNull()
  })
})

// ── why a fund carries no score ─────────────────────────────────────────────
//
// The counts below are the test's own; what is under test is which clauses appear, in what order,
// and which are omitted. The board's real figures come from `universe_snapshot.exclusion_reason`.
describe('the unscored, explained', () => {
  it('names the reasons largest first, so the dominant one is read first', () => {
    expect(unscoredReasons({ n_small: 50, n_geared: 3, n_young: 9 })).toEqual([
      '50 below the liquidity floor',
      '9 too new to measure',
      '3 geared or inverse',
    ])
  })

  it('omits a reason that accounts for nobody — a zero clause is noise, not information', () => {
    expect(unscoredReasons({ n_small: 4, n_geared: 0, n_young: 0 })).toEqual([
      '4 below the liquidity floor',
    ])
  })

  it('says nothing at all when every fund is scored', () => {
    expect(unscoredReasons({ n_small: 0, n_geared: 0, n_young: 0 })).toEqual([])
  })
})

// ── the label has to mean the number ──────────────────────────────────────────────────────────
describe('the fraction column says what the fraction counts', () => {
  // THE FM READ THIS COLUMN AND THOUGHT THE PIPELINE HAD REGRESSED. The board used to print
  // `n_scored / n_funds` under a heading that said "Scored". Moving every figure on the row to the
  // BUYABLE population changed the numerator to `n_offered` — Health Care went from 12/12 back to
  // 4/12 — and left the heading alone, so the page now said "Scored 4 of 12" about a scorer that
  // had graded all twelve. The numbers were right and the word was a year out of date, which is
  // indistinguishable from a broken pipeline to anyone reading the page instead of the diff.
  const heatmap = readFileSync(
    join(process.cwd(), 'src', 'components', 'sectors', 'SectorHeatmap.tsx'),
    'utf8',
  )

  it('renders n_offered under a heading that says buyable, never scored', () => {
    expect(heatmap).toContain('${node.n_offered}/${node.n_funds}')
    expect(heatmap).toContain('Buyable')
    // The word may still appear in the tooltip, which explains BOTH numbers. It may not be the
    // heading, which is the only part most readers ever see.
    expect(heatmap).not.toMatch(/^\s*Scored\{' '\}/m)
  })
})
