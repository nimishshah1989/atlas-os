// Tests for src/components/charts/EquityCurveChart.tsx (shared component used by portfolios/[id])
// Covers A5: empty state text is user-facing, no "v0" / "M16" jargon.

import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'

vi.mock('recharts', () => ({
  LineChart: ({ children }: { children: React.ReactNode }) => <div data-testid="line-chart">{children}</div>,
  Line: () => null,
  XAxis: () => null,
  YAxis: () => null,
  Tooltip: () => null,
  Legend: () => null,
  ResponsiveContainer: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}))

import { EquityCurveChart } from '@/components/charts/EquityCurveChart'
import type { PaperPerfRow } from '@/lib/queries/paper_perf'

const MOCK_ROWS: PaperPerfRow[] = [
  {
    id: 'p1',
    strategy_id: 's1',
    date: new Date('2026-01-01'),
    total_value: '1000000',
    daily_return: '0.001',
    benchmark_nifty500_return: '0.0008',
    benchmark_naive_atlas_return: null,
    regime: 'Risk-On',
    positions_count: 10,
  },
]

describe('EquityCurveChart (shared) — empty state (A5)', () => {
  it('renders a user-facing empty state without "v0" or "M16" jargon', () => {
    render(<EquityCurveChart data={[]} />)
    expect(document.body.textContent).not.toContain('v0')
    expect(document.body.textContent).not.toContain('M16')
  })

  it('empty state message references paper trading in plain language', () => {
    render(<EquityCurveChart data={[]} />)
    expect(screen.getByText(/equity curve will appear once paper trading is active/i)).toBeInTheDocument()
  })

  it('does not render a chart when data is empty', () => {
    render(<EquityCurveChart data={[]} />)
    expect(screen.queryByTestId('line-chart')).toBeNull()
  })
})

describe('EquityCurveChart (shared) — with data', () => {
  it('renders a chart when data is provided', () => {
    render(<EquityCurveChart data={MOCK_ROWS} />)
    expect(screen.getByTestId('line-chart')).toBeInTheDocument()
  })
})
