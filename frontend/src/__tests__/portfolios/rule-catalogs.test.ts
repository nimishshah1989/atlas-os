// Tests for src/lib/rule-catalogs.ts
// Hardcoded strings protect against drift vs atlas/api/_rule_allowlist.py.
// If any test fails here, update both the Python and the TS file together.

import { describe, it, expect } from 'vitest'
import {
  RS_STATES,
  MOMENTUM_STATES,
  RISK_STATES,
  VOLUME_STATES,
  SECTOR_STATES,
  REGIME_STATES,
  POSITION_SIZING,
  REBALANCE,
  BREADTH_GATES,
  formatBreadthValue,
} from '@/lib/rule-catalogs'

describe('RS_STATES mirrors Python ALLOWED_RS_STATES', () => {
  it('contains exact 7 values', () => {
    expect(RS_STATES).toHaveLength(7)
  })
  it('contains all expected values', () => {
    const expected = ['Leader', 'Strong', 'Consolidating', 'Emerging', 'Average', 'Weak', 'Laggard']
    for (const v of expected) {
      expect(RS_STATES).toContain(v)
    }
  })
})

describe('MOMENTUM_STATES mirrors Python ALLOWED_MOMENTUM_STATES', () => {
  it('contains exact 5 values', () => {
    expect(MOMENTUM_STATES).toHaveLength(5)
  })
  it('contains all expected values', () => {
    const expected = ['Accelerating', 'Improving', 'Flat', 'Deteriorating', 'Collapsing']
    for (const v of expected) {
      expect(MOMENTUM_STATES).toContain(v)
    }
  })
})

describe('RISK_STATES mirrors Python ALLOWED_RISK_STATES', () => {
  it('contains exact 5 values', () => {
    expect(RISK_STATES).toHaveLength(5)
  })
  it('contains all expected values', () => {
    const expected = ['Low', 'Normal', 'Elevated', 'High', 'Below Trend']
    for (const v of expected) {
      expect(RISK_STATES).toContain(v)
    }
  })
})

describe('VOLUME_STATES mirrors Python ALLOWED_VOLUME_STATES', () => {
  it('contains exact 5 values', () => {
    expect(VOLUME_STATES).toHaveLength(5)
  })
  it('contains all expected values', () => {
    const expected = ['Accumulation', 'Steady-Buying', 'Neutral', 'Distribution', 'Heavy Distribution']
    for (const v of expected) {
      expect(VOLUME_STATES).toContain(v)
    }
  })
})

describe('SECTOR_STATES mirrors Python ALLOWED_SECTOR_STATES', () => {
  it('contains exact 4 values', () => {
    expect(SECTOR_STATES).toHaveLength(4)
  })
  it('contains all expected values', () => {
    const expected = ['Overweight', 'Neutral', 'Underweight', 'Avoid']
    for (const v of expected) {
      expect(SECTOR_STATES).toContain(v)
    }
  })
})

describe('REGIME_STATES mirrors Python ALLOWED_REGIME_STATES', () => {
  it('contains exact 4 values', () => {
    expect(REGIME_STATES).toHaveLength(4)
  })
  it('contains all expected values', () => {
    const expected = ['Risk-On', 'Constructive', 'Cautious', 'Risk-Off']
    for (const v of expected) {
      expect(REGIME_STATES).toContain(v)
    }
  })
})

describe('POSITION_SIZING mirrors Python ALLOWED_POSITION_SIZING', () => {
  it('contains exact 3 values', () => {
    expect(POSITION_SIZING).toHaveLength(3)
  })
  it('contains all expected values', () => {
    expect(POSITION_SIZING).toContain('equal_weight')
    expect(POSITION_SIZING).toContain('vol_target')
    expect(POSITION_SIZING).toContain('market_cap')
  })
})

describe('REBALANCE mirrors Python ALLOWED_REBALANCE', () => {
  it('contains exact 3 values', () => {
    expect(REBALANCE).toHaveLength(3)
  })
  it('contains all expected values', () => {
    expect(REBALANCE).toContain('signal_change')
    expect(REBALANCE).toContain('weekly')
    expect(REBALANCE).toContain('monthly')
  })
})

describe('BREADTH_GATES mirrors Python ALLOWED_BREADTH_FIELDS', () => {
  it('contains exact 5 gates', () => {
    expect(BREADTH_GATES).toHaveLength(5)
  })
  it('contains all expected keys', () => {
    const keys = BREADTH_GATES.map((g) => g.key)
    expect(keys).toContain('pct_above_ema_50')
    expect(keys).toContain('ad_ratio')
    expect(keys).toContain('new_high_low_ratio')
    expect(keys).toContain('pct_in_strong_states')
    expect(keys).toContain('pct_weinstein_pass')
  })
  it('each gate has required fields', () => {
    for (const gate of BREADTH_GATES) {
      expect(gate).toHaveProperty('key')
      expect(gate).toHaveProperty('label')
      expect(gate).toHaveProperty('min')
      expect(gate).toHaveProperty('max')
      expect(gate).toHaveProperty('step')
      expect(gate).toHaveProperty('fmt')
      expect(gate).toHaveProperty('help')
    }
  })
})

describe('formatBreadthValue', () => {
  it('formats pct as integer percent', () => {
    expect(formatBreadthValue(60, 'pct')).toBe('60%')
    expect(formatBreadthValue(60.7, 'pct')).toBe('61%')
  })
  it('formats ratio to 2 decimals', () => {
    expect(formatBreadthValue(1.2, 'ratio')).toBe('1.20')
  })
  it('formats frac to 2 decimals', () => {
    expect(formatBreadthValue(0.6, 'frac')).toBe('0.60')
  })
})
