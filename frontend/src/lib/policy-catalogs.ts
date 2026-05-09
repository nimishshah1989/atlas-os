// policy-catalogs.ts — universe of FM-selectable state values per gate and per multiplier.
// NOT server-only: safe to import in client components.

export const RS_STATES_ALL = [
  'Leader', 'Strong', 'Consolidating', 'Emerging',
  'Average', 'Weak', 'Laggard',
] as const

export const MOMENTUM_STATES_ALL = [
  'Accelerating', 'Improving', 'Flat', 'Deteriorating', 'Collapsing',
] as const

export const RISK_STATES_ALL = [
  'Low', 'Normal', 'Elevated', 'High', 'Below Trend',
] as const

export const VOLUME_STATES_ALL = [
  'Accumulation', 'Steady-Buying', 'Neutral', 'Distribution', 'Heavy Distribution',
] as const

export const SECTOR_STATES_ALL = [
  'Overweight', 'Neutral', 'Underweight', 'Avoid',
] as const

export const REGIME_STATES_ALL = [
  'Risk-On', 'Constructive', 'Cautious', 'Risk-Off',
] as const

// Suspended states are LOCKED — never selectable as "investable":
export const LOCKED_STATES = [
  'INSUFFICIENT_HISTORY', 'ILLIQUID', 'DISLOCATION_SUSPENDED',
] as const

// Per-gate config: which catalog drives the checkboxes + human label
export const GATE_CONFIG: Record<string, {
  label: string
  catalog: readonly string[]
  methodologySection: string
  description: string
}> = {
  strength_gate_stock: {
    label: 'Strength Gate (Stock)',
    catalog: RS_STATES_ALL,
    methodologySection: '13.1',
    description: 'A stock passes if its rs_state is in this set.',
  },
  direction_gate_stock: {
    label: 'Direction Gate (Stock)',
    catalog: MOMENTUM_STATES_ALL,
    methodologySection: '13.2',
    description: 'A stock passes if its momentum_state is in this set.',
  },
  risk_gate_stock: {
    label: 'Risk Gate (Stock)',
    catalog: RISK_STATES_ALL,
    methodologySection: '13.3',
    description: 'A stock passes if its risk_state is in this set.',
  },
  volume_gate_stock: {
    label: 'Volume Gate (Stock)',
    catalog: VOLUME_STATES_ALL,
    methodologySection: '13.4',
    description: 'A stock passes if its volume_state is in this set.',
  },
  sector_gate_stock: {
    label: 'Sector Gate (Stock)',
    catalog: SECTOR_STATES_ALL,
    methodologySection: '11.4',
    description: "A stock passes if its sector's state is in this set.",
  },
  market_gate: {
    label: 'Market Gate',
    catalog: REGIME_STATES_ALL,
    methodologySection: '10',
    description: "Stocks AND ETFs pass if today's regime is in this set.",
  },
}

// Multiplier configs
export const MULTIPLIER_CONFIG: Record<string, {
  label: string
  catalog: readonly string[]
  min: number
  max: number
  step: number
  methodologySection: string
  description: string
}> = {
  risk_multipliers_stock: {
    label: 'Position-size multiplier (per stock risk_state)',
    catalog: RISK_STATES_ALL,
    min: 0.0, max: 2.0, step: 0.1,
    methodologySection: '13.3',
    description: 'Multiplied into base position size for stocks of each risk_state.',
  },
  market_multipliers: {
    label: 'Deployment multiplier (per regime_state)',
    catalog: REGIME_STATES_ALL,
    min: 0.0, max: 1.0, step: 0.1,
    methodologySection: '10',
    description: 'Cap on total portfolio deployment based on the regime.',
  },
}
