/**
 * Tests for frontend/src/components/setup/PolicyEditor.tsx
 *
 * Covers:
 * - Renders an editable control for every one of the 17 Policy fields
 * - Fields are grouped (Deployment / Concentration / Entry / Exit / Instrument / Benchmark / Cadence)
 * - Each field has a tooltip trigger (InfoTooltip with aria-label="info")
 * - house-default mode: all fields editable, no inherited/overridden markers
 * - portfolio mode: inherited fields show "inherited" marker + Override button;
 *   overridden fields show "overridden" marker + Revert button
 * - Changing a numeric field and clicking Save calls onSave with exactly that field
 * - Save is disabled when nothing has changed
 * - Reverted field is sent as null in onSave (explicit override clear)
 * - trailing_stop_pct can be cleared (null = off)
 * - buy_states multi-select: toggling a stage updates the selection
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { PolicyEditor } from '../PolicyEditor'
import type { EffectivePolicy } from '@/components/portfolio/PolicyPanel'

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

function makePolicy(overrides: Partial<EffectivePolicy> = {}): EffectivePolicy {
  const base: EffectivePolicy = {
    cash_floor_pct:         { value: '5', source: 'inherited' },
    respect_regime_cap:     { value: true, source: 'inherited' },
    max_per_stock_pct:      { value: '8', source: 'inherited' },
    max_per_sector_pct:     { value: '20', source: 'inherited' },
    max_small_cap_pct:      { value: '30', source: 'inherited' },
    min_holdings:           { value: '10', source: 'inherited' },
    max_positions:          { value: '25', source: 'inherited' },
    buy_states:             { value: ['stage_1', 'stage_2a'], source: 'inherited' },
    min_within_state_rank:  { value: '0.60', source: 'inherited' },
    min_rs_rank:            { value: '0.70', source: 'inherited' },
    hard_stop_pct:          { value: '8', source: 'inherited' },
    state_exit_trim:        { value: 'stage_3', source: 'inherited' },
    state_exit_full:        { value: 'stage_4', source: 'inherited' },
    trailing_stop_pct:      { value: null, source: 'inherited' },
    instrument_universe:    { value: 'direct_equity', source: 'inherited' },
    benchmark:              { value: 'NIFTY_500', source: 'inherited' },
    rebalance_cadence:      { value: 'weekly', source: 'inherited' },
  }
  return { ...base, ...overrides }
}

/** Policy with some overridden fields for portfolio mode */
function makePortfolioPolicy(): EffectivePolicy {
  return makePolicy({
    cash_floor_pct:    { value: '10', source: 'overridden' },
    max_positions:     { value: '15', source: 'overridden' },
  })
}

// ---------------------------------------------------------------------------
// Group rendering
// ---------------------------------------------------------------------------

describe('PolicyEditor — group rendering', () => {
  it('renders all 7 group headings', () => {
    render(
      <PolicyEditor
        policy={makePolicy()}
        mode="house-default"
        onSave={vi.fn()}
      />
    )
    // Query by heading role to avoid matching field labels with the same keywords
    const headings = screen.getAllByRole('heading', { level: 3 })
    const headingTexts = headings.map((h) => h.textContent?.toLowerCase() ?? '')
    expect(headingTexts.some((t) => t.includes('deployment'))).toBe(true)
    expect(headingTexts.some((t) => t.includes('concentration'))).toBe(true)
    expect(headingTexts.some((t) => t.includes('entry'))).toBe(true)
    expect(headingTexts.some((t) => t.includes('exit'))).toBe(true)
    expect(headingTexts.some((t) => t.includes('instrument'))).toBe(true)
    expect(headingTexts.some((t) => t.includes('benchmark'))).toBe(true)
    expect(headingTexts.some((t) => t.includes('cadence'))).toBe(true)
  })
})

// ---------------------------------------------------------------------------
// All 17 fields render editable controls
// ---------------------------------------------------------------------------

describe('PolicyEditor — field controls', () => {
  beforeEach(() => {
    render(
      <PolicyEditor
        policy={makePolicy()}
        mode="house-default"
        onSave={vi.fn()}
      />
    )
  })

  it('renders numeric input for cash_floor_pct', () => {
    expect(screen.getByTestId('field-cash_floor_pct')).toBeInTheDocument()
  })

  it('renders toggle for respect_regime_cap', () => {
    expect(screen.getByTestId('field-respect_regime_cap')).toBeInTheDocument()
  })

  it('renders numeric input for max_per_stock_pct', () => {
    expect(screen.getByTestId('field-max_per_stock_pct')).toBeInTheDocument()
  })

  it('renders numeric input for max_per_sector_pct', () => {
    expect(screen.getByTestId('field-max_per_sector_pct')).toBeInTheDocument()
  })

  it('renders numeric input for max_small_cap_pct', () => {
    expect(screen.getByTestId('field-max_small_cap_pct')).toBeInTheDocument()
  })

  it('renders numeric input for min_holdings', () => {
    expect(screen.getByTestId('field-min_holdings')).toBeInTheDocument()
  })

  it('renders numeric input for max_positions', () => {
    expect(screen.getByTestId('field-max_positions')).toBeInTheDocument()
  })

  it('renders multi-select checkboxes for buy_states', () => {
    expect(screen.getByTestId('field-buy_states')).toBeInTheDocument()
    // Should have 7 stage options
    const container = screen.getByTestId('field-buy_states')
    expect(container.querySelectorAll('input[type="checkbox"]').length).toBe(7)
  })

  it('renders numeric input for min_within_state_rank', () => {
    expect(screen.getByTestId('field-min_within_state_rank')).toBeInTheDocument()
  })

  it('renders numeric input for min_rs_rank', () => {
    expect(screen.getByTestId('field-min_rs_rank')).toBeInTheDocument()
  })

  it('renders numeric input for hard_stop_pct', () => {
    expect(screen.getByTestId('field-hard_stop_pct')).toBeInTheDocument()
  })

  it('renders select for state_exit_trim', () => {
    expect(screen.getByTestId('field-state_exit_trim')).toBeInTheDocument()
  })

  it('renders select for state_exit_full', () => {
    expect(screen.getByTestId('field-state_exit_full')).toBeInTheDocument()
  })

  it('renders trailing_stop_pct input with clear button', () => {
    expect(screen.getByTestId('field-trailing_stop_pct')).toBeInTheDocument()
  })

  it('renders select for instrument_universe', () => {
    expect(screen.getByTestId('field-instrument_universe')).toBeInTheDocument()
  })

  it('renders text input for benchmark', () => {
    expect(screen.getByTestId('field-benchmark')).toBeInTheDocument()
  })

  it('renders select for rebalance_cadence', () => {
    expect(screen.getByTestId('field-rebalance_cadence')).toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------
// Tooltips: every field has an InfoTooltip trigger
// ---------------------------------------------------------------------------

describe('PolicyEditor — tooltips', () => {
  it('renders an info tooltip for every field (17 total)', () => {
    render(
      <PolicyEditor
        policy={makePolicy()}
        mode="house-default"
        onSave={vi.fn()}
      />
    )
    // InfoTooltip renders a button with aria-label="info"
    const tooltipTriggers = screen.getAllByRole('button', { name: /info/i })
    // At minimum one per field
    expect(tooltipTriggers.length).toBeGreaterThanOrEqual(17)
  })
})

// ---------------------------------------------------------------------------
// Save button state
// ---------------------------------------------------------------------------

describe('PolicyEditor — Save button', () => {
  it('Save is disabled when nothing has changed', () => {
    render(
      <PolicyEditor
        policy={makePolicy()}
        mode="house-default"
        onSave={vi.fn()}
      />
    )
    const saveBtn = screen.getByRole('button', { name: /save/i })
    expect(saveBtn).toBeDisabled()
  })

  it('does not show unsaved-changes indicator initially', () => {
    render(
      <PolicyEditor
        policy={makePolicy()}
        mode="house-default"
        onSave={vi.fn()}
      />
    )
    expect(screen.queryByTestId('unsaved-indicator')).not.toBeInTheDocument()
  })

  it('Save is enabled after changing a field', async () => {
    const user = userEvent.setup()
    render(
      <PolicyEditor
        policy={makePolicy()}
        mode="house-default"
        onSave={vi.fn()}
      />
    )
    const cashInput = screen.getByTestId('input-cash_floor_pct')
    await user.clear(cashInput)
    await user.type(cashInput, '7')
    const saveBtn = screen.getByRole('button', { name: /save/i })
    expect(saveBtn).not.toBeDisabled()
  })

  it('shows unsaved-changes indicator after modifying a field', async () => {
    const user = userEvent.setup()
    render(
      <PolicyEditor
        policy={makePolicy()}
        mode="house-default"
        onSave={vi.fn()}
      />
    )
    const cashInput = screen.getByTestId('input-cash_floor_pct')
    await user.clear(cashInput)
    await user.type(cashInput, '7')
    expect(screen.getByTestId('unsaved-indicator')).toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------
// onSave called with exactly the changed fields
// ---------------------------------------------------------------------------

describe('PolicyEditor — onSave contract', () => {
  it('calls onSave with only the changed field when Save is clicked', async () => {
    const user = userEvent.setup()
    const onSave = vi.fn()
    render(
      <PolicyEditor
        policy={makePolicy()}
        mode="house-default"
        onSave={onSave}
      />
    )
    const cashInput = screen.getByTestId('input-cash_floor_pct')
    await user.clear(cashInput)
    await user.type(cashInput, '7')
    await user.click(screen.getByRole('button', { name: /save/i }))

    expect(onSave).toHaveBeenCalledOnce()
    const changedFields = onSave.mock.calls[0][0]
    expect(Object.keys(changedFields)).toEqual(['cash_floor_pct'])
    expect(changedFields.cash_floor_pct).toBe('7')
  })

  it('does not include unchanged fields in changedFields', async () => {
    const user = userEvent.setup()
    const onSave = vi.fn()
    render(
      <PolicyEditor
        policy={makePolicy()}
        mode="house-default"
        onSave={onSave}
      />
    )
    // Change only hard_stop_pct
    const input = screen.getByTestId('input-hard_stop_pct')
    await user.clear(input)
    await user.type(input, '10')
    await user.click(screen.getByRole('button', { name: /save/i }))

    const changedFields = onSave.mock.calls[0][0]
    expect(Object.keys(changedFields)).toEqual(['hard_stop_pct'])
    expect('cash_floor_pct' in changedFields).toBe(false)
  })

  it('Save is disabled again after saving (no pending changes)', async () => {
    const user = userEvent.setup()
    const onSave = vi.fn()
    render(
      <PolicyEditor
        policy={makePolicy()}
        mode="house-default"
        onSave={onSave}
      />
    )
    const cashInput = screen.getByTestId('input-cash_floor_pct')
    await user.clear(cashInput)
    await user.type(cashInput, '7')
    await user.click(screen.getByRole('button', { name: /save/i }))
    expect(screen.getByRole('button', { name: /save/i })).toBeDisabled()
  })
})

// ---------------------------------------------------------------------------
// portfolio mode — inherited / overridden markers and controls
// ---------------------------------------------------------------------------

describe('PolicyEditor — portfolio mode', () => {
  it('inherited field shows inherited marker', () => {
    render(
      <PolicyEditor
        policy={makePortfolioPolicy()}
        mode="portfolio"
        onSave={vi.fn()}
      />
    )
    // max_per_stock_pct is inherited in makePortfolioPolicy
    const badge = screen.getByTestId('source-badge-max_per_stock_pct')
    expect(badge).toHaveAttribute('data-source', 'inherited')
  })

  it('overridden field shows overridden marker', () => {
    render(
      <PolicyEditor
        policy={makePortfolioPolicy()}
        mode="portfolio"
        onSave={vi.fn()}
      />
    )
    // cash_floor_pct is overridden
    const badge = screen.getByTestId('source-badge-cash_floor_pct')
    expect(badge).toHaveAttribute('data-source', 'overridden')
  })

  it('inherited field shows Override button', () => {
    render(
      <PolicyEditor
        policy={makePortfolioPolicy()}
        mode="portfolio"
        onSave={vi.fn()}
      />
    )
    expect(screen.getByTestId('override-btn-max_per_stock_pct')).toBeInTheDocument()
  })

  it('overridden field shows Revert button', () => {
    render(
      <PolicyEditor
        policy={makePortfolioPolicy()}
        mode="portfolio"
        onSave={vi.fn()}
      />
    )
    expect(screen.getByTestId('revert-btn-cash_floor_pct')).toBeInTheDocument()
  })

  it('inherited field input is disabled until Override is clicked', () => {
    render(
      <PolicyEditor
        policy={makePortfolioPolicy()}
        mode="portfolio"
        onSave={vi.fn()}
      />
    )
    const input = screen.getByTestId('input-max_per_stock_pct')
    expect(input).toBeDisabled()
  })

  it('clicking Override enables the field input', async () => {
    const user = userEvent.setup()
    render(
      <PolicyEditor
        policy={makePortfolioPolicy()}
        mode="portfolio"
        onSave={vi.fn()}
      />
    )
    await user.click(screen.getByTestId('override-btn-max_per_stock_pct'))
    const input = screen.getByTestId('input-max_per_stock_pct')
    expect(input).not.toBeDisabled()
  })

  it('clicking Revert sends null for that field in onSave', async () => {
    const user = userEvent.setup()
    const onSave = vi.fn()
    render(
      <PolicyEditor
        policy={makePortfolioPolicy()}
        mode="portfolio"
        onSave={onSave}
      />
    )
    await user.click(screen.getByTestId('revert-btn-cash_floor_pct'))
    await user.click(screen.getByRole('button', { name: /save/i }))

    expect(onSave).toHaveBeenCalledOnce()
    const changedFields = onSave.mock.calls[0][0]
    expect(changedFields.cash_floor_pct).toBeNull()
  })

  it('overridden field remains editable in portfolio mode', () => {
    render(
      <PolicyEditor
        policy={makePortfolioPolicy()}
        mode="portfolio"
        onSave={vi.fn()}
      />
    )
    // cash_floor_pct is overridden — should be editable (not disabled)
    const input = screen.getByTestId('input-cash_floor_pct')
    expect(input).not.toBeDisabled()
  })
})

// ---------------------------------------------------------------------------
// trailing_stop_pct nullable — clear to off
// ---------------------------------------------------------------------------

describe('PolicyEditor — trailing_stop_pct nullable', () => {
  it('shows Off state when trailing_stop_pct is null', () => {
    render(
      <PolicyEditor
        policy={makePolicy({ trailing_stop_pct: { value: null, source: 'inherited' } })}
        mode="house-default"
        onSave={vi.fn()}
      />
    )
    // The input should be empty / disabled, an "off" indicator visible
    expect(screen.getByTestId('trailing-off-indicator')).toBeInTheDocument()
  })

  it('shows numeric input when trailing_stop_pct has a value', () => {
    render(
      <PolicyEditor
        policy={makePolicy({ trailing_stop_pct: { value: '12', source: 'inherited' } })}
        mode="house-default"
        onSave={vi.fn()}
      />
    )
    const input = screen.getByTestId('input-trailing_stop_pct')
    expect((input as HTMLInputElement).value).toBe('12')
  })

  it('clearing trailing_stop_pct sends null in onSave', async () => {
    const user = userEvent.setup()
    const onSave = vi.fn()
    render(
      <PolicyEditor
        policy={makePolicy({ trailing_stop_pct: { value: '12', source: 'inherited' } })}
        mode="house-default"
        onSave={onSave}
      />
    )
    await user.click(screen.getByTestId('trailing-clear-btn'))
    await user.click(screen.getByRole('button', { name: /save/i }))

    const changedFields = onSave.mock.calls[0][0]
    expect(changedFields.trailing_stop_pct).toBeNull()
  })
})

// ---------------------------------------------------------------------------
// buy_states multi-select
// ---------------------------------------------------------------------------

describe('PolicyEditor — buy_states multi-select', () => {
  it('renders human-readable stage labels not raw enum keys', () => {
    render(
      <PolicyEditor
        policy={makePolicy()}
        mode="house-default"
        onSave={vi.fn()}
      />
    )
    const container = screen.getByTestId('field-buy_states')
    expect(container).toHaveTextContent('Stage 1 Base')
    expect(container).toHaveTextContent('Stage 2A')
    expect(container).toHaveTextContent('Stage 3 Top')
    expect(container).not.toHaveTextContent('stage_1')
  })

  it('pre-checks the initially active states', () => {
    render(
      <PolicyEditor
        policy={makePolicy()}  // buy_states: stage_1, stage_2a
        mode="house-default"
        onSave={vi.fn()}
      />
    )
    const container = screen.getByTestId('field-buy_states')
    const checkboxes = container.querySelectorAll('input[type="checkbox"]') as NodeListOf<HTMLInputElement>
    const checkedLabels = Array.from(checkboxes)
      .filter(cb => cb.checked)
      .map(cb => cb.value)
    expect(checkedLabels).toContain('stage_1')
    expect(checkedLabels).toContain('stage_2a')
  })

  it('toggling a stage checkbox and saving includes updated buy_states in changedFields', async () => {
    const user = userEvent.setup()
    const onSave = vi.fn()
    render(
      <PolicyEditor
        policy={makePolicy()}
        mode="house-default"
        onSave={onSave}
      />
    )
    // Toggle stage_2b on (was off)
    const container = screen.getByTestId('field-buy_states')
    const stage2bCheckbox = container.querySelector('input[value="stage_2b"]') as HTMLInputElement
    await user.click(stage2bCheckbox)
    await user.click(screen.getByRole('button', { name: /save/i }))

    const changedFields = onSave.mock.calls[0][0]
    expect(changedFields.buy_states).toContain('stage_2b')
    expect(changedFields.buy_states).toContain('stage_1')
    expect(changedFields.buy_states).toContain('stage_2a')
  })
})

// ---------------------------------------------------------------------------
// respect_regime_cap toggle
// ---------------------------------------------------------------------------

describe('PolicyEditor — respect_regime_cap toggle', () => {
  it('shows Yes when true', () => {
    render(
      <PolicyEditor
        policy={makePolicy({ respect_regime_cap: { value: true, source: 'inherited' } })}
        mode="house-default"
        onSave={vi.fn()}
      />
    )
    const toggle = screen.getByTestId('field-respect_regime_cap')
    expect(toggle).toHaveTextContent('Yes')
  })

  it('shows No when false', () => {
    render(
      <PolicyEditor
        policy={makePolicy({ respect_regime_cap: { value: false, source: 'inherited' } })}
        mode="house-default"
        onSave={vi.fn()}
      />
    )
    const toggle = screen.getByTestId('field-respect_regime_cap')
    expect(toggle).toHaveTextContent('No')
  })

  it('clicking the toggle flips the value and enables Save', async () => {
    const user = userEvent.setup()
    const onSave = vi.fn()
    render(
      <PolicyEditor
        policy={makePolicy({ respect_regime_cap: { value: true, source: 'inherited' } })}
        mode="house-default"
        onSave={onSave}
      />
    )
    const toggleBtn = screen.getByTestId('toggle-respect_regime_cap')
    await user.click(toggleBtn)
    expect(screen.getByRole('button', { name: /save/i })).not.toBeDisabled()
    await user.click(screen.getByRole('button', { name: /save/i }))
    const changedFields = onSave.mock.calls[0][0]
    expect(changedFields.respect_regime_cap).toBe(false)
  })
})
