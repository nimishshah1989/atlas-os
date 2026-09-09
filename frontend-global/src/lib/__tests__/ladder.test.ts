/**
 * The ladder adapter: a score journal row → the rows Atlas's signature block draws.
 *
 * PROVENANCE — NO FUND AND NO SCORE IS INVENTED HERE (rule #0).
 *
 * • The two SPY rows are the REAL ones already cited elsewhere in this suite. The first is the
 *   degenerate row `blend()` writes when no lens had data, from the scratch database of EOD
 *   2026-09-03 that src/components/explorer/__tests__/InstrumentExplorer.test.tsx is built on:
 *   BlendResult(None, 'BELOW_THRESHOLD', 0) — no composite, no lens, no decile. The second is
 *   SPY as the live board served it on 2026-09-09 for EOD 2026-09-08, the row
 *   src/lib/__tests__/thresholds.test.ts and StrengthRiskBubble.test.tsx read: composite 74.55,
 *   HIGH, 3 of 5 lenses, decile 7 in equity:broad_market.
 * • The weights are the seeds of scripts/global_market/seed_thresholds.py (§B and §C of the plan),
 *   the same list InstrumentExplorer.test.tsx reads out of atlas_thresholds.
 * • The evidence object is the shape its two writers emit, spelled as they spell it:
 *   score_etfs.py nests each lens's own trail under the lens name beside `grouped_by`/`peer_n`,
 *   and atlas/global_market/scoring/etf_lenses._lens writes exactly
 *   {"reason": "no sub-score had inputs"} when nothing could be computed.
 *
 * NO LENS OR SUB-SCORE VALUE IS ASSERTED ON, because none exists to assert on: the lens columns
 * are null in every real row this repo holds. What is under test is the mapping and, above all,
 * that an absent measurement comes out as null and never as a zero.
 */
import { describe, expect, it } from 'vitest'
import { scoreToLadder, SUB_MAX, topLens } from '@/lib/ladder'
import {
  ETF_LENSES as ETF_LENS_COLUMNS,
  lensDeciles,
  STOCK_LENSES as STOCK_LENS_COLUMNS,
  type ScoreDetail,
} from '@/lib/queries/scores'
import { lensSubs, type LensWeight } from '@/lib/scores'

// select threshold_key, threshold_value from atlas_global.atlas_thresholds
// where is_active and threshold_key like 'etf_lens_weight_%'
const ETF_LENSES: LensWeight[] = [
  { key: 'technical', weight: 0.35 },
  { key: 'quality', weight: 0.3 },
  { key: 'cost_liquidity', weight: 0.2 },
  { key: 'flow', weight: 0.15 },
  { key: 'risk', weight: 0 },
]
// …and 'lens_weight_%': technical and fundamental are seeded at the SAME weight, which is what
// makes the tie-break testable at all.
const STOCK_LENSES: LensWeight[] = [
  { key: 'technical', weight: 0.3 },
  { key: 'fundamental', weight: 0.3 },
  { key: 'catalyst', weight: 0.25 },
  { key: 'flow', weight: 0.15 },
]

/** SPY, EOD 2026-09-03: a journal row exists, and no lens had data. */
const DEGENERATE: ScoreDetail = {
  scored_on: '2026-09-03',
  // Every lens in this fixture is null, so no lens carries a decile — the real shape, not a gap.
  deciles: {},
  values: { composite: null, technical: null, risk: null, cost_liquidity: null, flow: null, quality: null },
  conviction_tier: 'BELOW_THRESHOLD',
  peer_group: 'equity:broad_market',
  lenses_active: 0,
  coverage_factor: null,
  decile: null,
  peer_rank: null,
  peer_n: null,
  evidence: { grouped_by: 'strategy', peer_n: 40, technical: { reason: 'no sub-score had inputs' } },
  lenses: ETF_LENSES,
}

/** SPY, EOD 2026-09-08, as the board served it: scored and ranked. The per-lens columns are not
 *  in that payload, so they stay null here rather than being filled in with a guess. */
const SCORED: ScoreDetail = {
  ...DEGENERATE,
  scored_on: '2026-09-08',
  values: { ...DEGENERATE.values, composite: '74.55' },
  conviction_tier: 'HIGH',
  lenses_active: 3,
  decile: 7,
  peer_rank: 4,
  peer_n: 34,
}

describe('one row per lens, widest weight first', () => {
  it('gives every lens the weight table carries a row — including the ones with no producer', () => {
    const rows = scoreToLadder('etf', DEGENERATE)
    expect(rows.map((r) => r.key)).toEqual(['technical', 'quality', 'cost_liquidity', 'flow', 'risk'])
    expect(rows.map((r) => r.weight)).toEqual([0.35, 0.3, 0.2, 0.15, 0])
  })

  it('orders by weight whatever order the caller hands them over in', () => {
    const shuffled = { ...DEGENERATE, lenses: [...ETF_LENSES].reverse() }
    expect(scoreToLadder('etf', shuffled).map((r) => r.key)).toEqual(
      scoreToLadder('etf', DEGENERATE).map((r) => r.key),
    )
  })

  it('breaks a tie on the threshold key, the same way the weights query does', () => {
    const rows = scoreToLadder('stock', { ...SCORED, lenses: STOCK_LENSES })
    expect(rows.map((r) => r.key)).toEqual(['fundamental', 'technical', 'catalyst', 'flow'])
  })

  it('names each lens in words, never the column name', () => {
    const rows = scoreToLadder('etf', DEGENERATE)
    expect(rows.map((r) => r.label)).toContain('Cost & liquidity')
  })

  it('keeps a zero WEIGHT, which is a real answer — the risk lens is an overlay today', () => {
    const risk = scoreToLadder('etf', DEGENERATE).find((r) => r.key === 'risk')
    expect(risk?.weight).toBe(0)
    expect(risk?.score).toBeNull()
  })
})

describe('an absent measurement is null, never a zero (rule #0)', () => {
  it('leaves every lens of the degenerate row unscored rather than scoring it 0', () => {
    for (const row of scoreToLadder('etf', DEGENERATE)) expect(row.score).toBeNull()
  })

  it('leaves every sub-score of a lens nobody reached null, so the ladder can say the words', () => {
    const technical = scoreToLadder('etf', DEGENERATE).find((r) => r.key === 'technical')
    expect(technical?.numbers?.map((n) => n.value)).toEqual([null, null, null, null])
  })

  it('opens no row at all when no lens is scored — never an empty one', () => {
    expect(topLens(scoreToLadder('etf', DEGENERATE))).toBeUndefined()
  })

  it('carries the composite unchanged as text; the ladder never recomputes it', () => {
    expect(SCORED.values.composite).toBe('74.55')
    expect(scoreToLadder('etf', SCORED).every((r) => r.score == null)).toBe(true)
  })
})

describe('the actual numbers', () => {
  it('is one entry per sub-score column of that lens, in the journal’s own order', () => {
    const rows = scoreToLadder('etf', SCORED)
    for (const row of rows) {
      expect(row.numbers).toHaveLength(lensSubs('etf', row.key).length)
    }
    const cost = rows.find((r) => r.key === 'cost_liquidity')
    expect(cost?.numbers?.map((n) => n.label)).toEqual([
      'Expense ratio',
      'Traded value',
      'Assets under management',
      'Concentration',
    ])
  })

  it('reads the STOCK sub-scores for a stock, not the ETF ones', () => {
    const rows = scoreToLadder('stock', { ...SCORED, lenses: STOCK_LENSES })
    const technical = rows.find((r) => r.key === 'technical')
    expect(technical?.numbers?.map((n) => n.label)).toEqual([
      'Trend',
      'Relative strength',
      'Volatility contraction',
      'Volume',
    ])
  })

  it('carries the unit a sub-score is measured in — a lens is out of 100, a sub out of 25', () => {
    expect(SUB_MAX).toBe(25)
    const values = { ...SCORED.values, cost_expense: '18.75' }
    const cost = scoreToLadder('etf', { ...SCORED, values }).find((r) => r.key === 'cost_liquidity')
    expect(cost?.numbers?.[0]).toEqual({ label: 'Expense ratio', value: '18.8 / 25' })
  })
})

describe('the evidence trail', () => {
  it('reads the lens’s own entry out of the row’s evidence JSONB', () => {
    const technical = scoreToLadder('etf', DEGENERATE).find((r) => r.key === 'technical')
    expect(technical?.evidence).toEqual(['reason: no sub-score had inputs'])
  })

  it('takes only the scorer’s words — a count is not evidence, it is one of the numbers', () => {
    const evidence = { technical: { subs_present: 3, rs_3m: 'strong', rs_6m: 'ahead' } }
    const technical = scoreToLadder('etf', { ...SCORED, evidence }).find((r) => r.key === 'technical')
    expect(technical?.evidence).toEqual(['rs 3m: strong', 'rs 6m: ahead'])
  })

  it('is empty, not a throw, for a row whose evidence is null or holds nothing for the lens', () => {
    for (const evidence of [null, undefined, 'not an object', { technical: 'flat' }, {}]) {
      const rows = scoreToLadder('etf', { ...SCORED, evidence })
      expect(rows.find((r) => r.key === 'technical')?.evidence).toEqual([])
    }
  })
})

// ── the per-lens decile ─────────────────────────────────────────────────────
//
// India's ladder shows a decile beside every lens, cut within cap cohort, and this board now cuts
// the same thing on read (src/lib/queries/scores.ts::lensDeciles). Two things are worth pinning:
// the SQL asks for exactly one decile per lens, in the right cohort; and a lens with no score
// carries no decile at all rather than a low one.
describe('every lens carries its own decile, cut in its own cohort', () => {
  it('asks postgres for one ntile per lens, partitioned by the cohort that lens is judged in', () => {
    const sql = lensDeciles(ETF_LENS_COLUMNS, 'peer_group')
    for (const lens of ETF_LENS_COLUMNS) {
      expect(sql).toContain(`ORDER BY s.${lens}`)
      expect(sql).toContain(`AS ${lens}_decile`)
    }
    // One ntile each, and no more.
    expect(sql.match(/ntile\(10\)/g)).toHaveLength(ETF_LENS_COLUMNS.length)
    expect(sql.match(/PARTITION BY s\.date, s\.peer_group/g)).toHaveLength(ETF_LENS_COLUMNS.length)
  })

  it('puts the rows a lens could not score into their own partition, so they never dilute it', () => {
    // India's trick, and the reason it is here: `(lens IS NULL)` in the PARTITION BY keeps the
    // unmeasured funds out of the ranking of the measured ones.
    const sql = lensDeciles(STOCK_LENS_COLUMNS, 'cap_cohort')
    for (const lens of STOCK_LENS_COLUMNS) expect(sql).toContain(`(s.${lens} IS NULL) ORDER BY s.${lens}`)
    expect(sql).not.toContain('peer_group')
  })

  it('refuses a decile for an ETF whose asset class is too small to rank at all', () => {
    // score_etfs leaves peer_group NULL there; with no population, no lens has a standing in one.
    expect(lensDeciles(ETF_LENS_COLUMNS, 'peer_group')).toContain('OR s.peer_group IS NULL')
    // Stocks always have a cap cohort — score_stocks assigns one to every scored name — so only
    // the ETF side carries that escape. Both sides keep the OTHER null guard, which is a different
    // rule: a lens with no score has no decile, whatever the cohort.
    expect(lensDeciles(STOCK_LENS_COLUMNS, 'cap_cohort')).not.toContain('OR s.peer_group IS NULL')
    for (const lens of STOCK_LENS_COLUMNS) {
      expect(lensDeciles(STOCK_LENS_COLUMNS, 'cap_cohort')).toContain(`CASE WHEN s.${lens} IS NULL THEN NULL`)
    }
  })

  it('gives a lens with no score no decile — an empty track, never a low one', () => {
    // SPY on 2026-09-03: the journal's degenerate row, every lens null. Real, and the honest case.
    for (const l of scoreToLadder('etf', DEGENERATE)) {
      expect(l.score).toBeNull()
      expect(l.decile ?? null).toBeNull()
    }
  })
})
