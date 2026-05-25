// frontend/src/components/v6/__tests__/CellMatrix.test.tsx
//
// C.14 test suite for the extended CellMatrix component.
// 6 test cases:
//   1. Renders 21 cells from mocked data (no placeholder tiles for missing combos)
//   2. Failed-gate microcopy: (n_gate_pass=0, n_candidates>0)  → "No rule survived"
//   3. Failed-gate microcopy: (n_gate_pass=0, n_candidates=0)  → "No candidates tested"
//   4. Failed-gate microcopy: (n_candidates=0, empty rule_dsl) → "Insufficient data"
//   5. Held-count overlay appears when n_held_firing > 0
//   6. drift_warn chip visible only when drift_status = 'drift_warn'
//   7. Click tile fires router.push to /v6/cells/[cell_id]
//   8. Empty state: renders "Matrix data unavailable" when cells array is empty
//
// ARIA: aria-label format tested in case 7.

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { CellMatrix } from '../CellMatrix'
import type { MatrixCell } from '@/lib/queries/v6/cells'

// ── next/navigation mock ─────────────────────────────────────────────────────

const _routerPush = vi.fn()

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: _routerPush }),
}))

// ── Fixture factory ──────────────────────────────────────────────────────────

function makeCell(overrides: Partial<MatrixCell> = {}): MatrixCell {
  return {
    cell_id: 'Mid_6m_POSITIVE',
    cap_tier: 'Mid',
    tenure: '6m',
    action: 'POSITIVE',
    confidence_unconditional: '0.1500',   // → AA grade
    friction_adjusted_excess: '0.045000',
    predicted_excess: '0.038000',
    drift_status: 'healthy',
    bh_fdr_q: null,
    methodology_lock_ref: 'lock-2026-05-23',
    rule_dsl: { operator: 'AND', conditions: [] },
    n_firing_today: 12,
    n_candidates: 5,
    n_gate_pass: 3,
    n_held_firing: 0,
    ...overrides,
  }
}

/**
 * Build a minimal set of 21 cells covering all 24 grid slots except the
 * 3 confirmed missing combinations (Small/NEG/1m, Small/NEG/12m, Large/POS/1m).
 */
function make21Cells(): MatrixCell[] {
  const tiers = ['Large', 'Mid', 'Small'] as const
  const tenures = ['1m', '3m', '6m', '12m'] as const
  const actions = ['POSITIVE', 'NEGATIVE'] as const

  const missing = new Set([
    'Small_1m_NEGATIVE',
    'Small_12m_NEGATIVE',
    'Large_1m_POSITIVE',
  ])

  const cells: MatrixCell[] = []
  for (const tier of tiers) {
    for (const tenure of tenures) {
      for (const action of actions) {
        const key = `${tier}_${tenure}_${action}`
        if (!missing.has(key)) {
          cells.push(
            makeCell({
              cell_id: key,
              cap_tier: tier,
              tenure,
              action,
            }),
          )
        }
      }
    }
  }
  return cells
}

// ── Test suite ───────────────────────────────────────────────────────────────

describe('CellMatrix', () => {
  beforeEach(() => {
    _routerPush.mockReset()
  })

  // ── Case 1: 21 cells render ──────────────────────────────────────────────

  it('renders exactly 21 cells from mocked data (no synthetic tiles for missing combos)', () => {
    const cells = make21Cells()
    expect(cells).toHaveLength(21)

    const { container } = render(<CellMatrix cells={cells} />)

    // Each present cell renders a navigation <button> with an aria-label.
    // The tile uses an overlay-button pattern to avoid nested <button> elements
    // (required because InfoTooltip uses a <button> internally).
    // Filter out the InfoTooltip "info" buttons — they have aria-label="info".
    const tileBtns = Array.from(
      container.querySelectorAll('button[aria-label]'),
    ).filter(
      (b) => (b as HTMLButtonElement).getAttribute('aria-label') !== 'info',
    )
    expect(tileBtns.length).toBe(21)

    // 3 empty grid slots (missing combos) render as aria-hidden divs with "—"
    const emptySlots = container.querySelectorAll('div[aria-hidden="true"]')
    expect(emptySlots.length).toBe(3)
  })

  // ── Case 2: Failed-gate microcopy — "No rule survived" ───────────────────

  it('shows "No rule survived" when n_gate_pass=0 and n_candidates>0', () => {
    const cell = makeCell({
      cell_id: 'Large_3m_POSITIVE',
      cap_tier: 'Large',
      tenure: '3m',
      action: 'POSITIVE',
      n_gate_pass: 0,
      n_candidates: 5,
      confidence_unconditional: '0',
    })
    render(<CellMatrix cells={[cell]} />)
    expect(screen.getByText('No rule survived')).toBeInTheDocument()
  })

  // ── Case 3: Failed-gate microcopy — "No candidates tested" ───────────────

  it('shows "No candidates tested" when n_gate_pass=0 and n_candidates=0 (non-empty rule_dsl)', () => {
    const cell = makeCell({
      cell_id: 'Large_3m_POSITIVE',
      cap_tier: 'Large',
      tenure: '3m',
      action: 'POSITIVE',
      n_gate_pass: 0,
      n_candidates: 0,
      confidence_unconditional: '0',
      // Non-empty rule_dsl → distinguishes from "Insufficient data" path
      rule_dsl: { operator: 'AND', conditions: [{ feature: 'rs_residual_6m', gt: 0 }] },
    })
    render(<CellMatrix cells={[cell]} />)
    expect(screen.getByText('No candidates tested')).toBeInTheDocument()
  })

  // ── Case 4: Failed-gate microcopy — "Insufficient data" ──────────────────

  it('shows "Insufficient data" when n_candidates=0 and rule_dsl is empty', () => {
    const cell = makeCell({
      cell_id: 'Large_3m_POSITIVE',
      cap_tier: 'Large',
      tenure: '3m',
      action: 'POSITIVE',
      n_gate_pass: 0,
      n_candidates: 0,
      confidence_unconditional: '0',
      rule_dsl: {},
    })
    render(<CellMatrix cells={[cell]} />)
    expect(screen.getByText('Insufficient data')).toBeInTheDocument()
  })

  // ── Case 5: Held-count overlay ───────────────────────────────────────────

  it('shows held-count badge when n_held_firing > 0', () => {
    const withHeld = makeCell({
      cell_id: 'Mid_6m_POSITIVE',
      cap_tier: 'Mid',
      tenure: '6m',
      action: 'POSITIVE',
      n_held_firing: 3,
    })
    const withoutHeld = makeCell({
      cell_id: 'Mid_3m_POSITIVE',
      cap_tier: 'Mid',
      tenure: '3m',
      action: 'POSITIVE',
      n_held_firing: 0,
    })
    render(<CellMatrix cells={[withHeld, withoutHeld]} />)

    // Badge with aria-label "3 held" should appear
    const badge = screen.getByLabelText('3 held')
    expect(badge).toBeInTheDocument()
    expect(badge.textContent).toBe('3')

    // No badge for the cell with n_held_firing=0
    const badges = document.querySelectorAll('[aria-label="0 held"]')
    expect(badges.length).toBe(0)
  })

  // ── Case 6: drift_warn chip visibility ──────────────────────────────────

  it('shows DRIFT chip only when drift_status = "drift_warn"; hidden for "healthy"; "deprecated" shows DEPRECATED', () => {
    const driftWarnCell = makeCell({
      cell_id: 'Mid_6m_POSITIVE',
      cap_tier: 'Mid',
      tenure: '6m',
      action: 'POSITIVE',
      drift_status: 'drift_warn',
      n_gate_pass: 2,
    })
    const healthyCell = makeCell({
      cell_id: 'Mid_3m_POSITIVE',
      cap_tier: 'Mid',
      tenure: '3m',
      action: 'POSITIVE',
      drift_status: 'healthy',
      n_gate_pass: 2,
    })
    const deprecatedCell = makeCell({
      cell_id: 'Large_6m_POSITIVE',
      cap_tier: 'Large',
      tenure: '6m',
      action: 'POSITIVE',
      drift_status: 'deprecated',
      n_gate_pass: 2,
    })

    render(<CellMatrix cells={[driftWarnCell, healthyCell, deprecatedCell]} />)

    // "drift_warn" → DRIFT chip visible
    expect(screen.getByText('DRIFT')).toBeInTheDocument()

    // "deprecated" → DEPRECATED chip visible
    expect(screen.getByText('DEPRECATED')).toBeInTheDocument()

    // "healthy" → no chip rendered; confirm no extra drift chips
    const driftChips = screen.queryAllByText('DRIFT')
    expect(driftChips).toHaveLength(1)
  })

  // ── Case 7: Click fires router.push ─────────────────────────────────────

  it('clicking a tile calls router.push to /v6/cells/[cell_id]', () => {
    const cell = makeCell({
      cell_id: 'Mid_6m_POSITIVE',
      cap_tier: 'Mid',
      tenure: '6m',
      action: 'POSITIVE',
    })
    render(<CellMatrix cells={[cell]} />)

    const btn = screen.getByRole('button', { name: /Mid 6m POSITIVE/i })
    fireEvent.click(btn)

    expect(_routerPush).toHaveBeenCalledTimes(1)
    expect(_routerPush).toHaveBeenCalledWith(
      `/v6/cells/${encodeURIComponent('Mid_6m_POSITIVE')}`,
    )
  })

  // ── Case 8: Empty state ──────────────────────────────────────────────────

  it('renders "Matrix data unavailable" when cells array is empty', () => {
    render(<CellMatrix cells={[]} />)
    expect(screen.getByText('Matrix data unavailable')).toBeInTheDocument()
  })
})
