/**
 * Tests for frontend/src/lib/policy-entry-filter.ts
 *
 * Covers:
 * - Pure applyEntryFilter function
 * - DoD #4: strict vs loose policies over the same candidates produce different result sets
 * - PolicyEntryParams construction from EffectivePolicy
 */
import { describe, it, expect } from 'vitest'
import {
  applyEntryFilter,
  type CandidateInstrument,
  type PolicyEntryParams,
} from '@/lib/policy-entry-filter'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeCandidate(
  id: string,
  engineState: string | null,
  withinStateRank: number | null,
  rsRank12m: number | null,
): CandidateInstrument {
  return { instrument_id: id, symbol: id, engine_state: engineState, within_state_rank: withinStateRank, rs_rank_12m: rsRank12m }
}

// Strict policy: only stage_2b + rank >= 0.80 + rs >= 0.70
const STRICT: PolicyEntryParams = {
  buy_states: ['stage_2b'],
  min_within_state_rank: 0.80,
  min_rs_rank: 0.70,
}

// Loose policy: stage_2a or stage_2b + rank >= 0.50 + rs >= 0.40
const LOOSE: PolicyEntryParams = {
  buy_states: ['stage_2a', 'stage_2b'],
  min_within_state_rank: 0.50,
  min_rs_rank: 0.40,
}

// Hand-specified candidates (matches Python test_entry_filter.py CANDIDATES)
// A: stage_2b, rank=0.90, rs=0.80 → both pass
// B: stage_2a, rank=0.60, rs=0.50 → loose passes, strict FAILS (wrong state)
// C: stage_2b, rank=0.75, rs=0.65 → loose passes, strict FAILS (rank<0.80, rs<0.70)
// D: stage_1,  rank=0.90, rs=0.85 → both FAIL (wrong state)
// E: stage_2b, rank=0.85, rs=0.72 → both pass
const CANDIDATES: CandidateInstrument[] = [
  makeCandidate('A', 'stage_2b', 0.90, 0.80),
  makeCandidate('B', 'stage_2a', 0.60, 0.50),
  makeCandidate('C', 'stage_2b', 0.75, 0.65),
  makeCandidate('D', 'stage_1',  0.90, 0.85),
  makeCandidate('E', 'stage_2b', 0.85, 0.72),
]

// ---------------------------------------------------------------------------
// Basic filter behaviour
// ---------------------------------------------------------------------------

describe('applyEntryFilter — basic cases', () => {
  it('empty candidates returns empty result', () => {
    expect(applyEntryFilter([], STRICT)).toEqual([])
  })

  it('all candidates pass a permissive policy', () => {
    const zero: PolicyEntryParams = { buy_states: ['stage_1', 'stage_2a', 'stage_2b', 'stage_3', 'stage_4'], min_within_state_rank: 0, min_rs_rank: 0 }
    const all = [makeCandidate('X', 'stage_1', 0, 0), makeCandidate('Y', 'stage_2b', 0.5, 0.5)]
    expect(applyEntryFilter(all, zero)).toHaveLength(2)
  })

  it('wrong state is excluded', () => {
    const c = [makeCandidate('X', 'stage_1', 0.90, 0.90)]
    expect(applyEntryFilter(c, STRICT)).toHaveLength(0)
  })

  it('null engine_state is excluded', () => {
    const c = [makeCandidate('X', null, 0.90, 0.90)]
    expect(applyEntryFilter(c, STRICT)).toHaveLength(0)
  })

  it('null within_state_rank treated as 0 — excluded when threshold positive', () => {
    const c = [makeCandidate('X', 'stage_2b', null, 0.90)]
    expect(applyEntryFilter(c, STRICT)).toHaveLength(0)
  })

  it('null rs_rank_12m treated as 0 — excluded when threshold positive', () => {
    const c = [makeCandidate('X', 'stage_2b', 0.90, null)]
    expect(applyEntryFilter(c, STRICT)).toHaveLength(0)
  })

  it('null ranks pass when both thresholds are 0', () => {
    const zeroThreshold: PolicyEntryParams = { buy_states: ['stage_2b'], min_within_state_rank: 0, min_rs_rank: 0 }
    const c = [makeCandidate('X', 'stage_2b', null, null)]
    expect(applyEntryFilter(c, zeroThreshold)).toHaveLength(1)
  })

  it('empty buy_states excludes all', () => {
    const noStates: PolicyEntryParams = { buy_states: [], min_within_state_rank: 0, min_rs_rank: 0 }
    const c = [makeCandidate('X', 'stage_2b', 0.90, 0.90)]
    expect(applyEntryFilter(c, noStates)).toHaveLength(0)
  })

  it('exactly at threshold passes (inclusive >=)', () => {
    const c = [makeCandidate('X', 'stage_2b', 0.80, 0.70)]
    expect(applyEntryFilter(c, STRICT)).toHaveLength(1)
  })

  it('below within_state_rank threshold is excluded', () => {
    const c = [makeCandidate('X', 'stage_2b', 0.79, 0.90)]
    expect(applyEntryFilter(c, STRICT)).toHaveLength(0)
  })

  it('below rs_rank_12m threshold is excluded', () => {
    const c = [makeCandidate('X', 'stage_2b', 0.90, 0.69)]
    expect(applyEntryFilter(c, STRICT)).toHaveLength(0)
  })

  it('preserves input order', () => {
    const c = [makeCandidate('Z', 'stage_2b', 0.90, 0.80), makeCandidate('A', 'stage_2b', 0.85, 0.75)]
    const result = applyEntryFilter(c, LOOSE)
    expect(result.map(r => r.instrument_id)).toEqual(['Z', 'A'])
  })
})

// ---------------------------------------------------------------------------
// DoD #4: two policies over the same candidates → different results
// ---------------------------------------------------------------------------

describe('DoD #4 — strict vs loose policies produce different candidate sets', () => {
  it('strict passes exactly A and E', () => {
    const result = applyEntryFilter(CANDIDATES, STRICT)
    const ids = new Set(result.map(c => c.instrument_id))
    expect(ids).toEqual(new Set(['A', 'E']))
  })

  it('loose passes A, B, C, E (D fails — wrong state)', () => {
    const result = applyEntryFilter(CANDIDATES, LOOSE)
    const ids = new Set(result.map(c => c.instrument_id))
    expect(ids).toEqual(new Set(['A', 'B', 'C', 'E']))
  })

  it('strict and loose result sets are not equal', () => {
    const strictIds = new Set(applyEntryFilter(CANDIDATES, STRICT).map(c => c.instrument_id))
    const looseIds  = new Set(applyEntryFilter(CANDIDATES, LOOSE).map(c => c.instrument_id))
    // Sets are not equal
    expect(strictIds.size).not.toBe(looseIds.size)
  })

  it('strict count is 2', () => {
    expect(applyEntryFilter(CANDIDATES, STRICT)).toHaveLength(2)
  })

  it('loose count is 4', () => {
    expect(applyEntryFilter(CANDIDATES, LOOSE)).toHaveLength(4)
  })

  it('every strict pass also passes loose (strict ⊆ loose)', () => {
    const strictIds = new Set(applyEntryFilter(CANDIDATES, STRICT).map(c => c.instrument_id))
    const looseIds  = new Set(applyEntryFilter(CANDIDATES, LOOSE).map(c => c.instrument_id))
    for (const id of strictIds) {
      expect(looseIds.has(id)).toBe(true)
    }
  })
})
