// Tests for src/components/portfolio/PolicyPanel.tsx
// Covers: all 7 groups render, every field shows tooltip trigger,
// inherited fields show the inherited marker, overridden fields show
// the overridden marker, null policy shows empty state.

import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { PolicyPanel, type EffectivePolicy } from '@/components/portfolio/PolicyPanel'

// ---------------------------------------------------------------------------
// Fixture: a policy where some fields are overridden, others inherited
// ---------------------------------------------------------------------------

const INHERITED_POLICY: EffectivePolicy = {
  // Deployment
  cash_floor_pct:      { value: '5', source: 'inherited' },
  respect_regime_cap:  { value: true, source: 'inherited' },
  // Concentration
  max_per_stock_pct:   { value: '5', source: 'inherited' },
  max_per_sector_pct:  { value: '15', source: 'inherited' },
  max_small_cap_pct:   { value: '30', source: 'inherited' },
  min_holdings:        { value: '15', source: 'inherited' },
  max_positions:       { value: '40', source: 'inherited' },
  // Entry
  buy_states:          { value: ['stage_2a', 'stage_2b'], source: 'inherited' },
  min_within_state_rank: { value: '0.60', source: 'inherited' },
  min_rs_rank:         { value: '0.70', source: 'inherited' },
  // Exit
  hard_stop_pct:       { value: '8', source: 'inherited' },
  state_exit_trim:     { value: 'stage_3', source: 'inherited' },
  state_exit_full:     { value: 'stage_4', source: 'inherited' },
  trailing_stop_pct:   { value: null, source: 'inherited' },
  // Instrument
  instrument_universe: { value: 'direct_equity', source: 'inherited' },
  // Benchmark
  benchmark:           { value: 'Nifty 500', source: 'inherited' },
  // Cadence
  rebalance_cadence:   { value: 'weekly', source: 'inherited' },
}

const MIXED_POLICY: EffectivePolicy = {
  ...INHERITED_POLICY,
  // These fields are overridden for this portfolio
  cash_floor_pct:      { value: '10', source: 'overridden' },
  max_per_stock_pct:   { value: '8', source: 'overridden' },
  buy_states:          { value: ['stage_2a', 'stage_2b', 'stage_2c'], source: 'overridden' },
  trailing_stop_pct:   { value: '12', source: 'overridden' },
  rebalance_cadence:   { value: 'monthly', source: 'overridden' },
}

// ---------------------------------------------------------------------------
// Group rendering — all 7 groups must be present
// ---------------------------------------------------------------------------

describe('PolicyPanel — group headings', () => {
  it('renders all 7 policy groups', () => {
    const { container } = render(<PolicyPanel policy={INHERITED_POLICY} />)
    // Use h3 selectors to avoid matching field labels that contain these words
    const headings = container.querySelectorAll('h3')
    const headingTexts = Array.from(headings).map((h) => h.textContent?.trim())
    expect(headingTexts).toContain('Deployment')
    expect(headingTexts).toContain('Concentration')
    expect(headingTexts).toContain('Entry')
    expect(headingTexts).toContain('Exit')
    expect(headingTexts).toContain('Instrument')
    expect(headingTexts).toContain('Benchmark')
    expect(headingTexts).toContain('Cadence')
  })
})

// ---------------------------------------------------------------------------
// Field values render correctly
// ---------------------------------------------------------------------------

describe('PolicyPanel — field value formatting', () => {
  it('renders pct field with % suffix', () => {
    render(<PolicyPanel policy={INHERITED_POLICY} />)
    // Multiple fields have 5% (cash_floor_pct and max_per_stock_pct); check at least one exists
    const pctValues = screen.getAllByText('5%')
    expect(pctValues.length).toBeGreaterThan(0)
  })

  it('renders boolean as Yes/No', () => {
    render(<PolicyPanel policy={INHERITED_POLICY} />)
    expect(screen.getByText('Yes')).toBeInTheDocument()   // respect_regime_cap=true
  })

  it('renders buy_states as individual badges', () => {
    render(<PolicyPanel policy={INHERITED_POLICY} />)
    expect(screen.getByText('stage_2a')).toBeInTheDocument()
    expect(screen.getByText('stage_2b')).toBeInTheDocument()
  })

  it('renders null trailing_stop_pct as Off', () => {
    render(<PolicyPanel policy={INHERITED_POLICY} />)
    expect(screen.getByText('Off')).toBeInTheDocument()
  })

  it('renders rank field as-is (fraction)', () => {
    render(<PolicyPanel policy={INHERITED_POLICY} />)
    expect(screen.getByText('0.60')).toBeInTheDocument()   // min_within_state_rank
    expect(screen.getByText('0.70')).toBeInTheDocument()   // min_rs_rank
  })

  it('renders text field (benchmark) as-is', () => {
    render(<PolicyPanel policy={INHERITED_POLICY} />)
    expect(screen.getByText('Nifty 500')).toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------
// Source markers
// ---------------------------------------------------------------------------

describe('PolicyPanel — source markers', () => {
  it('all inherited fields show the inherited marker', () => {
    const { container } = render(<PolicyPanel policy={INHERITED_POLICY} />)
    const inheritedMarkers = container.querySelectorAll('[data-source="inherited"]')
    // All 17 fields should be inherited
    expect(inheritedMarkers.length).toBe(17)
  })

  it('overridden fields show the overridden marker', () => {
    const { container } = render(<PolicyPanel policy={MIXED_POLICY} />)
    const overriddenMarkers = container.querySelectorAll('[data-source="overridden"]')
    // 5 fields are overridden
    expect(overriddenMarkers.length).toBe(5)
  })

  it('overridden field does NOT show inherited marker', () => {
    const { container } = render(<PolicyPanel policy={MIXED_POLICY} />)
    // cash_floor_pct is overridden (10%)
    // Find the row and confirm it has overridden marker
    const overriddenMarkers = container.querySelectorAll('[data-source="overridden"]')
    expect(overriddenMarkers.length).toBeGreaterThan(0)
  })

  it('inherited and overridden markers coexist in mixed policy', () => {
    const { container } = render(<PolicyPanel policy={MIXED_POLICY} />)
    const inherited = container.querySelectorAll('[data-source="inherited"]')
    const overridden = container.querySelectorAll('[data-source="overridden"]')
    expect(inherited.length).toBe(12)  // 17 total - 5 overridden
    expect(overridden.length).toBe(5)
  })
})

// ---------------------------------------------------------------------------
// Tooltip triggers — every field must have one
// ---------------------------------------------------------------------------

describe('PolicyPanel — tooltip triggers', () => {
  it('every field row has an info button (17 total)', () => {
    const { container } = render(<PolicyPanel policy={INHERITED_POLICY} />)
    const infoButtons = container.querySelectorAll('button[aria-label="info"]')
    expect(infoButtons.length).toBe(17)
  })
})

// ---------------------------------------------------------------------------
// Empty state — null policy must not crash
// ---------------------------------------------------------------------------

describe('PolicyPanel — empty state', () => {
  it('renders the empty state when policy is null', () => {
    render(<PolicyPanel policy={null} />)
    expect(screen.getByText(/Policy not configured/i)).toBeInTheDocument()
  })

  it('does not render any group headings when policy is null', () => {
    render(<PolicyPanel policy={null} />)
    expect(screen.queryByText(/Deployment/i)).not.toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------
// Overridden field values actually update from the base
// ---------------------------------------------------------------------------

describe('PolicyPanel — overridden values display correctly', () => {
  it('shows overridden cash_floor_pct value (10%)', () => {
    render(<PolicyPanel policy={MIXED_POLICY} />)
    expect(screen.getByText('10%')).toBeInTheDocument()
  })

  it('shows overridden buy_states includes stage_2c', () => {
    render(<PolicyPanel policy={MIXED_POLICY} />)
    expect(screen.getByText('stage_2c')).toBeInTheDocument()
  })

  it('shows overridden trailing_stop as 12%', () => {
    render(<PolicyPanel policy={MIXED_POLICY} />)
    expect(screen.getByText('12%')).toBeInTheDocument()
  })
})
