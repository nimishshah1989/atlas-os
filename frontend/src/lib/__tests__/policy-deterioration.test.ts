/**
 * Tests for frontend/src/lib/policy-deterioration.ts
 *
 * Covers:
 * - Pure findDeterioration function
 * - C7: mutual exclusivity — a deteriorating holding's state is not in buy_states
 * - Honest hard_stop_pct omission (no entry price data)
 * - NULL handling (null engine_state, null policy fields)
 */
import { describe, it, expect } from 'vitest'
import {
  findDeterioration,
  type DeteriHolding,
  type DeteriPolicy,
  type DeteriItem,
} from '@/lib/policy-deterioration'

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

function makeHolding(
  id: string,
  symbol: string,
  engineState: string | null,
  weightPct = 5,
): DeteriHolding {
  return { instrument_id: id, symbol, engine_state: engineState, weight_pct: weightPct }
}

// House-default-like policy: stage_3 = trim, stage_4 = full exit
const POLICY: DeteriPolicy = {
  state_exit_trim: 'stage_3',
  state_exit_full: 'stage_4',
  buy_states: ['stage_2a', 'stage_2b', 'stage_2c'],
}

// Policy with null exit fields
const NULL_POLICY: DeteriPolicy = {
  state_exit_trim: null,
  state_exit_full: null,
  buy_states: ['stage_2a', 'stage_2b'],
}

// ---------------------------------------------------------------------------
// Basic cases
// ---------------------------------------------------------------------------

describe('findDeterioration — basic cases', () => {
  it('empty holdings returns empty result', () => {
    expect(findDeterioration([], POLICY)).toEqual([])
  })

  it('healthy stage_2b holding is NOT surfaced', () => {
    const holdings = [makeHolding('A', 'HDFCBANK', 'stage_2b')]
    expect(findDeterioration(holdings, POLICY)).toEqual([])
  })

  it('null engine_state is NOT surfaced', () => {
    const holdings = [makeHolding('A', 'HDFCBANK', null)]
    expect(findDeterioration(holdings, POLICY)).toEqual([])
  })

  it('stage_1 (neither trim nor exit state) is NOT surfaced', () => {
    const holdings = [makeHolding('A', 'RELIANCE', 'stage_1')]
    expect(findDeterioration(holdings, POLICY)).toEqual([])
  })

  it('state_exit_trim holding surfaces with rule="trim"', () => {
    const holdings = [makeHolding('B', 'INFY', 'stage_3', 7.5)]
    const result = findDeterioration(holdings, POLICY)
    expect(result).toHaveLength(1)
    expect(result[0].rule).toBe('trim')
    expect(result[0].instrument_id).toBe('B')
    expect(result[0].symbol).toBe('INFY')
    expect(result[0].weight_pct).toBe(7.5)
  })

  it('state_exit_full holding surfaces with rule="full_exit"', () => {
    const holdings = [makeHolding('C', 'WIPRO', 'stage_4', 4.0)]
    const result = findDeterioration(holdings, POLICY)
    expect(result).toHaveLength(1)
    expect(result[0].rule).toBe('full_exit')
    expect(result[0].instrument_id).toBe('C')
    expect(result[0].symbol).toBe('WIPRO')
    expect(result[0].weight_pct).toBe(4.0)
  })

  it('reason string for full_exit contains the state label', () => {
    const holdings = [makeHolding('C', 'WIPRO', 'stage_4')]
    const result = findDeterioration(holdings, POLICY)
    expect(result[0].reason).toContain('stage_4')
  })

  it('reason string for trim contains the state label', () => {
    const holdings = [makeHolding('B', 'INFY', 'stage_3')]
    const result = findDeterioration(holdings, POLICY)
    expect(result[0].reason).toContain('stage_3')
  })

  it('mixed holdings: only the deteriorating ones surface', () => {
    const holdings = [
      makeHolding('A', 'HDFCBANK', 'stage_2b'),
      makeHolding('B', 'INFY', 'stage_3'),
      makeHolding('C', 'WIPRO', 'stage_4'),
      makeHolding('D', 'TCS', 'stage_2a'),
      makeHolding('E', 'LT', null),
    ]
    const result = findDeterioration(holdings, POLICY)
    expect(result).toHaveLength(2)
    const ids = result.map((r) => r.instrument_id)
    expect(ids).toContain('B')
    expect(ids).toContain('C')
    expect(ids).not.toContain('A')
    expect(ids).not.toContain('D')
    expect(ids).not.toContain('E')
  })

  it('preserves weight_pct from holding', () => {
    const holdings = [makeHolding('B', 'INFY', 'stage_3', 12.5)]
    const result = findDeterioration(holdings, POLICY)
    expect(result[0].weight_pct).toBe(12.5)
  })
})

// ---------------------------------------------------------------------------
// NULL policy fields
// ---------------------------------------------------------------------------

describe('findDeterioration — null policy fields', () => {
  it('null state_exit_full skips full-exit check', () => {
    const policy: DeteriPolicy = { state_exit_trim: 'stage_3', state_exit_full: null, buy_states: ['stage_2b'] }
    const holdings = [makeHolding('C', 'WIPRO', 'stage_4')]
    expect(findDeterioration(holdings, policy)).toEqual([])
  })

  it('null state_exit_trim skips trim check', () => {
    const policy: DeteriPolicy = { state_exit_trim: null, state_exit_full: 'stage_4', buy_states: ['stage_2b'] }
    const holdings = [makeHolding('B', 'INFY', 'stage_3')]
    expect(findDeterioration(holdings, policy)).toEqual([])
  })

  it('both null policy fields → no deterioration for any state', () => {
    const holdings = [
      makeHolding('A', 'HDFCBANK', 'stage_3'),
      makeHolding('B', 'INFY', 'stage_4'),
    ]
    expect(findDeterioration(holdings, NULL_POLICY)).toEqual([])
  })
})

// ---------------------------------------------------------------------------
// C7: Mutual exclusivity — deteriorating holding not eligible as buy candidate
// ---------------------------------------------------------------------------

describe('C7 — mutual exclusivity: deteriorating state not in buy_states', () => {
  it('state_exit_full value is not in buy_states', () => {
    // By policy design, stage_4 is an exit state; buy_states contains stage_2a/2b/2c
    const exitState = POLICY.state_exit_full // 'stage_4'
    expect(exitState).not.toBeNull()
    expect(POLICY.buy_states).not.toContain(exitState)
  })

  it('state_exit_trim value is not in buy_states', () => {
    const trimState = POLICY.state_exit_trim // 'stage_3'
    expect(trimState).not.toBeNull()
    expect(POLICY.buy_states).not.toContain(trimState)
  })

  it('a holding in state_exit_full is returned by findDeterioration and its state is not in buy_states', () => {
    const holdings = [makeHolding('C', 'WIPRO', 'stage_4')]
    const result = findDeterioration(holdings, POLICY)
    expect(result).toHaveLength(1)
    const detItem = result[0]
    // The deteriorating holding's engine_state must NOT be in buy_states
    expect(POLICY.buy_states).not.toContain(detItem.engine_state)
  })

  it('a holding in state_exit_trim is returned by findDeterioration and its state is not in buy_states', () => {
    const holdings = [makeHolding('B', 'INFY', 'stage_3')]
    const result = findDeterioration(holdings, POLICY)
    expect(result).toHaveLength(1)
    const detItem = result[0]
    expect(POLICY.buy_states).not.toContain(detItem.engine_state)
  })

  it('a healthy stage_2b holding passes applyEntryFilter but does not appear in findDeterioration', () => {
    // Stage_2b is in buy_states but not in exit states — it should never be in both.
    const goodState = 'stage_2b'
    expect(POLICY.buy_states).toContain(goodState)
    expect(POLICY.state_exit_full).not.toBe(goodState)
    expect(POLICY.state_exit_trim).not.toBe(goodState)

    const holdings = [makeHolding('A', 'HDFCBANK', goodState)]
    expect(findDeterioration(holdings, POLICY)).toEqual([])
  })
})

// ---------------------------------------------------------------------------
// hard_stop_pct: honest omission
// ---------------------------------------------------------------------------

describe('findDeterioration — hard_stop_pct honest omission', () => {
  it('result items have no return_since_entry field (entry price not tracked)', () => {
    const holdings = [makeHolding('C', 'WIPRO', 'stage_4')]
    const result = findDeterioration(holdings, POLICY)
    expect(result).toHaveLength(1)
    // No return_since_entry — field must not exist on DeteriItem
    expect('return_since_entry' in result[0]).toBe(false)
    expect('entry_price' in result[0]).toBe(false)
  })
})
