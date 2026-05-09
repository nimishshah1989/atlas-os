// Tests for src/components/strategy/RuleBuilderForm.tsx
// Focuses on buildConfigPayload logic — strips disabled rules, builds correct shape.

import { describe, it, expect, vi } from 'vitest'

// RuleBuilderForm imports server actions which pull in server-only — mock them.
vi.mock('server-only', () => ({}))
vi.mock('next/cache', () => ({ revalidatePath: vi.fn() }))
vi.mock('@/lib/internal-api', () => ({ callInternalApi: vi.fn() }))
vi.mock('next/navigation', () => ({ useRouter: () => ({ push: vi.fn() }) }))

import { buildConfigPayload } from '@/components/strategy/RuleBuilderForm'

// Minimal FormState-compatible object factory
function makeForm(overrides: Partial<Parameters<typeof buildConfigPayload>[0]> = {}): Parameters<typeof buildConfigPayload>[0] {
  return {
    name: 'Test Strategy',
    description: '',
    universeStocks: true,
    universeEtfs: false,
    universeFunds: false,
    rsStateFilter: { enabled: false, selected: new Set() },
    momentumStateFilter: { enabled: false, selected: new Set() },
    riskStateFilter: { enabled: false, selected: new Set() },
    volumeStateFilter: { enabled: false, selected: new Set() },
    sectorStateFilter: { enabled: false, selected: new Set() },
    regimeStateFilter: { enabled: false, selected: new Set() },
    breadthGates: {
      enabled: false,
      values: {
        pct_above_ema_50: null,
        ad_ratio: null,
        new_high_low_ratio: null,
        pct_in_strong_states: null,
        pct_weinstein_pass: null,
      },
    },
    drawdownPerPosition: null,
    drawdownEnabled: false,
    holdingPeriodMax: null,
    holdingPeriodEnabled: false,
    positionSizing: 'equal_weight',
    maxPositions: 20,
    maxSectorPct: 25,
    rebalanceTrigger: 'signal_change',
    ...overrides,
  }
}

describe('buildConfigPayload — disabled rules are dropped', () => {
  it('omits disabled state filters', () => {
    const config = buildConfigPayload(makeForm())
    expect(config).not.toHaveProperty('rs_state_filter')
    expect(config).not.toHaveProperty('momentum_state_filter')
    expect(config).not.toHaveProperty('regime_state_filter')
  })

  it('omits breadth_gates when gates disabled', () => {
    const config = buildConfigPayload(makeForm())
    expect(config).not.toHaveProperty('breadth_gates')
  })

  it('omits exit_rules when neither exit option is enabled', () => {
    const config = buildConfigPayload(makeForm())
    expect(config).not.toHaveProperty('exit_rules')
  })
})

describe('buildConfigPayload — enabled rules are included', () => {
  it('includes rs_state_filter when enabled with selections', () => {
    const config = buildConfigPayload(
      makeForm({
        rsStateFilter: { enabled: true, selected: new Set(['Leader', 'Strong']) },
      }),
    )
    expect(config.rs_state_filter).toEqual(expect.arrayContaining(['Leader', 'Strong']))
    const arr = config.rs_state_filter as string[]
    expect(arr).toHaveLength(2)
  })

  it('omits filter even if enabled but no selections', () => {
    const config = buildConfigPayload(
      makeForm({
        rsStateFilter: { enabled: true, selected: new Set() },
      }),
    )
    expect(config).not.toHaveProperty('rs_state_filter')
  })

  it('includes active breadth gates when enabled', () => {
    const config = buildConfigPayload(
      makeForm({
        breadthGates: {
          enabled: true,
          values: {
            pct_above_ema_50: 60,
            ad_ratio: null,
            new_high_low_ratio: null,
            pct_in_strong_states: null,
            pct_weinstein_pass: null,
          },
        },
      }),
    )
    expect(config.breadth_gates).toEqual({ pct_above_ema_50: 60 })
  })

  it('omits breadth_gates key entirely when enabled but all values null', () => {
    const config = buildConfigPayload(
      makeForm({
        breadthGates: {
          enabled: true,
          values: {
            pct_above_ema_50: null,
            ad_ratio: null,
            new_high_low_ratio: null,
            pct_in_strong_states: null,
            pct_weinstein_pass: null,
          },
        },
      }),
    )
    expect(config).not.toHaveProperty('breadth_gates')
  })

  it('includes exit_rules with drawdown when enabled', () => {
    const config = buildConfigPayload(
      makeForm({ drawdownEnabled: true, drawdownPerPosition: 15 }),
    )
    expect(config.exit_rules).toEqual(
      expect.objectContaining({ drawdown_per_position_pct: 15 }),
    )
  })

  it('includes exit_rules with holding period when enabled', () => {
    const config = buildConfigPayload(
      makeForm({ holdingPeriodEnabled: true, holdingPeriodMax: 90 }),
    )
    expect(config.exit_rules).toEqual(
      expect.objectContaining({ holding_period_max_days: 90 }),
    )
  })

  it('merges both exit rules when both enabled', () => {
    const config = buildConfigPayload(
      makeForm({
        drawdownEnabled: true,
        drawdownPerPosition: 10,
        holdingPeriodEnabled: true,
        holdingPeriodMax: 60,
      }),
    )
    expect(config.exit_rules).toEqual({
      drawdown_per_position_pct: 10,
      holding_period_max_days: 60,
    })
  })
})

describe('buildConfigPayload — sizing and rebalance always present', () => {
  it('always includes position_sizing, max_positions, max_sector_pct, rebalance_trigger', () => {
    const config = buildConfigPayload(
      makeForm({
        positionSizing: 'vol_target',
        maxPositions: 30,
        maxSectorPct: 40,
        rebalanceTrigger: 'monthly',
      }),
    )
    expect(config.position_sizing).toBe('vol_target')
    expect(config.max_positions).toBe(30)
    expect(config.max_sector_pct).toBe(40)
    expect(config.rebalance_trigger).toBe('monthly')
  })
})
