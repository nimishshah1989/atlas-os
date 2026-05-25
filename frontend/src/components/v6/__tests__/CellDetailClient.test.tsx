// frontend/src/components/v6/__tests__/CellDetailClient.test.tsx
//
// 5 test cases for CellDetailClient:
//  1. Hero renders all numbers; null bh_fdr_q → "—"
//  2. Stocks-firing-today table renders rows with PortfolioBadge column
//  3. atlas_ledger empty → "No realized outcomes yet" message
//  4. rule_dsl renders as plain-English predicates
//  5. drift_warn chip visible only when drift_status = 'drift_warn'

import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { CellDetailClient } from '../CellDetailClient'
import type { CellDetailClientProps } from '../CellDetailClient'
import type { Cell } from '@/lib/queries/v6/cells'
import type { SignalCallEvent } from '@/lib/queries/v6/recent_signal_calls'
import type { HoldingState } from '@/lib/queries/v6/portfolio_holdings'

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const BASE_CELL: Cell = {
  cell_id: '11111111-1111-1111-1111-111111111111',
  cap_tier: 'Mid',
  tenure: '12m',
  action: 'POSITIVE',
  confidence_unconditional: '0.072',
  friction_adjusted_excess: '0.055',
  predicted_excess: '0.031',
  drift_status: 'healthy',
  bh_fdr_q: null,
  methodology_lock_ref: null,
  rule_dsl: {
    entry: [
      { feature: 'log_med_tv_60d', op: '>=', threshold: 16.5, weight: 0.4 },
      { feature: 'rs_percentile', op: '>=', threshold: 0.65, weight: 0.6 },
    ],
  },
}

const CELL_DRIFT_WARN: Cell = {
  ...BASE_CELL,
  cell_id: '22222222-2222-2222-2222-222222222222',
  drift_status: 'drift_warn',
}

const ACTIVE_SIGNAL: SignalCallEvent = {
  signal_call_id: 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
  cell_id: BASE_CELL.cell_id,
  cell_name: 'Mid 12m POSITIVE',
  instrument_id: 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb',
  ticker: 'RELIANCE',
  action: 'POSITIVE',
  cap_tier: 'Mid',
  tenure: '12m',
  entry_date: '2026-05-20',
  entry_price: null,
  confidence_unconditional: '0.072',
  predicted_excess: '0.031',
  exit_date: null,
  is_active: true,
}

const HOLDING_STATE: HoldingState = {
  portfolio_count: 2,
  weight_range: ['0.02', '0.04'],
  aggregate_weight: '0.031',
  last_add_date: '2026-05-20',
}

const BASE_PROPS: CellDetailClientProps = {
  cell: BASE_CELL,
  cellLabel: 'Mid 12m POSITIVE',
  firingToday: [],
  signalHistory: [],
  holdingStates: {},
  walkForwardWindows: [],
  ledgerOutcomes: [],
  maintainerNotes: null,
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('CellDetailClient', () => {

  it('Hero renders all numbers; null bh_fdr_q renders as "—"', () => {
    render(<CellDetailClient {...BASE_PROPS} />)

    // Cell label in hero h1 (there may be multiple elements with this text)
    const h1 = document.querySelector('h1')
    expect(h1?.textContent).toBe('Mid 12m POSITIVE')

    // IC value (confidence_unconditional = 0.072 → 7.20 IC)
    // The hero renders it as "7.20 IC"
    expect(screen.getByText(/7\.20 IC/)).toBeInTheDocument()

    // bh_fdr_q is null → should render "—"
    // The StatPill with label "BH-FDR q" has value "—"
    const bh = screen.getByText('BH-FDR q')
    const bhContainer = bh.closest('div')
    expect(bhContainer?.textContent).toContain('—')

    // predicted_excess = 0.031 → "+3.1%" — check sign and magnitude
    expect(screen.getByText(/\+3\.1%/)).toBeInTheDocument()
  })

  it('Stocks-firing-today table renders rows with PortfolioBadge column', () => {
    const props: CellDetailClientProps = {
      ...BASE_PROPS,
      firingToday: [ACTIVE_SIGNAL],
      holdingStates: {
        'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb': HOLDING_STATE,
      },
    }
    render(<CellDetailClient {...props} />)

    // Table heading rendered
    expect(screen.getByText('RELIANCE')).toBeInTheDocument()

    // PortfolioBadge compact renders "Held" text
    expect(screen.getByText('Held')).toBeInTheDocument()

    // PortfolioBadge renders with aria-label containing "portfolios"
    const badge = screen.getByRole('status', { name: /portfolios/i })
    expect(badge).toBeInTheDocument()
  })

  it('atlas_ledger empty → "No realized outcomes yet" message', () => {
    render(<CellDetailClient {...BASE_PROPS} ledgerOutcomes={[]} />)

    expect(screen.getByText('No realized outcomes yet.')).toBeInTheDocument()
  })

  it('rule_dsl renders as plain-English predicates', () => {
    render(<CellDetailClient {...BASE_PROPS} />)

    // Feature "log_med_tv_60d" → "log median 60-day traded value"
    expect(screen.getByText(/log median 60-day traded value/)).toBeInTheDocument()

    // Feature "rs_percentile" → "relative strength percentile vs universe"
    expect(screen.getByText(/relative strength percentile vs universe/)).toBeInTheDocument()

    // Entry conditions label
    expect(screen.getByText('Entry conditions')).toBeInTheDocument()
  })

  it('drift_warn chip is visible only when drift_status = drift_warn', () => {
    // healthy: no drift chip (role="status" should not be present)
    const { rerender } = render(<CellDetailClient {...BASE_PROPS} cell={BASE_CELL} />)
    expect(screen.queryByRole('status')).not.toBeInTheDocument()

    // drift_warn: chip appears with canonical DriftWarnChip copy
    rerender(<CellDetailClient {...BASE_PROPS} cell={CELL_DRIFT_WARN} cellLabel="Mid 12m POSITIVE" />)
    expect(screen.getByRole('status', { name: /Drift warning/i })).toBeInTheDocument()
  })

})
