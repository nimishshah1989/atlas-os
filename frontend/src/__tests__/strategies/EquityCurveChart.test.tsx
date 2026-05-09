// Tests for src/app/strategies/[id]/EquityCurveChart.tsx
// Verifies empty state, data rendering, and placeholder text.

import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'

// Mock Recharts — it doesn't work in jsdom; only verify render logic
vi.mock('recharts', () => ({
  LineChart: ({ children }: { children: React.ReactNode }) => <div data-testid="line-chart">{children}</div>,
  Line: () => null,
  XAxis: () => null,
  YAxis: () => null,
  Tooltip: () => null,
  Legend: () => null,
  ResponsiveContainer: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}))

import { EquityCurveChart } from '@/app/strategies/[id]/EquityCurveChart'
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
  {
    id: 'p2',
    strategy_id: 's1',
    date: new Date('2026-01-02'),
    total_value: '1005000',
    daily_return: '0.005',
    benchmark_nifty500_return: '0.002',
    benchmark_naive_atlas_return: null,
    regime: 'Risk-On',
    positions_count: 10,
  },
]

describe('EquityCurveChart', () => {
  it('renders placeholder when data is empty', () => {
    render(<EquityCurveChart data={[]} />)
    expect(
      screen.getByText(/Backtest equity series unavailable in v0/i)
    ).toBeTruthy()
  })

  it('renders placeholder text about M16 hookup', () => {
    render(<EquityCurveChart data={[]} />)
    expect(screen.getByText(/M16 paper-trader hookup/i)).toBeTruthy()
  })

  it('renders chart when data is provided', () => {
    render(<EquityCurveChart data={MOCK_ROWS} />)
    expect(screen.getByTestId('line-chart')).toBeTruthy()
  })

  it('renders equity curve heading', () => {
    render(<EquityCurveChart data={MOCK_ROWS} />)
    expect(screen.getByText(/Equity Curve/i)).toBeTruthy()
  })

  it('does not render chart when data is empty', () => {
    render(<EquityCurveChart data={[]} />)
    expect(screen.queryByTestId('line-chart')).toBeNull()
  })
})
