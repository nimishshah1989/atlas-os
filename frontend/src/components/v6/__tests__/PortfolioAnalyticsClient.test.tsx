// frontend/src/components/v6/__tests__/PortfolioAnalyticsClient.test.tsx
//
// TV-06 portfolio analytics tests:
//   1. Empty state renders when analytics is null
//   2. Portfolio name renders in header
//   3. All 7 metric cells render
//   4. Beta null renders "—" with tooltip "Requires 30+ trading days of data"
//   5. CSV export link has correct href
//   6. Positive Sharpe has text-signal-pos class; negative has text-signal-neg
//   7. Cumulative returns chart renders via mocked Recharts

import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { PortfolioAnalyticsClient } from '../PortfolioAnalyticsClient'
import type { PortfolioAnalytics } from '@/lib/queries/v6/portfolio_analytics'

// ---------------------------------------------------------------------------
// Mock recharts — jsdom doesn't implement SVG layout
// ---------------------------------------------------------------------------

vi.mock('recharts', () => ({
  ResponsiveContainer: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="responsive-container">{children}</div>
  ),
  LineChart: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="line-chart">{children}</div>
  ),
  Line: () => null,
  XAxis: () => null,
  YAxis: () => null,
  CartesianGrid: () => null,
  Tooltip: () => null,
}))

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const MOCK_DAILY_RETURNS = [
  { date: '2026-01-02', portfolio_return: 0.005, nifty50_return: 0.003 },
  { date: '2026-01-03', portfolio_return: -0.002, nifty50_return: 0.001 },
  { date: '2026-01-04', portfolio_return: 0.008, nifty50_return: 0.004 },
]

const MOCK_ANALYTICS: PortfolioAnalytics = {
  sharpe: 1.23,
  sortino: 1.85,
  calmar: 0.92,
  beta: 0.87,
  alpha: 0.05,
  max_drawdown: -0.12,
  twr: 0.18,
  annualised_return: 0.22,
  observation_days: 180,
  risk_free_rate_used: 0.065,
  daily_returns: MOCK_DAILY_RETURNS,
}

const NEGATIVE_ANALYTICS: PortfolioAnalytics = {
  ...MOCK_ANALYTICS,
  sharpe: -0.45,
  alpha: -0.03,
}

const NULL_BETA_ANALYTICS: PortfolioAnalytics = {
  ...MOCK_ANALYTICS,
  beta: null,
  alpha: null,
  sharpe: null,
}

// ---------------------------------------------------------------------------
// Test 1: Empty state when analytics is null
// ---------------------------------------------------------------------------

describe('PortfolioAnalyticsClient — empty state', () => {
  it('shows empty state message when analytics is null', () => {
    render(
      <PortfolioAnalyticsClient
        portfolioId="test-123"
        portfolioName="My Portfolio"
        analytics={null}
      />,
    )
    expect(screen.getByText(/No closed positions yet/)).toBeInTheDocument()
    expect(screen.getByText(/Analytics require at least 1 completed trade/)).toBeInTheDocument()
  })

  it('renders portfolio name in empty state', () => {
    render(
      <PortfolioAnalyticsClient
        portfolioId="test-123"
        portfolioName="Growth Portfolio"
        analytics={null}
      />,
    )
    expect(screen.getByText('Growth Portfolio')).toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------
// Test 2: Portfolio name in header
// ---------------------------------------------------------------------------

describe('PortfolioAnalyticsClient — header', () => {
  it('renders portfolio name', () => {
    render(
      <PortfolioAnalyticsClient
        portfolioId="abc"
        portfolioName="Alpha Fund"
        analytics={MOCK_ANALYTICS}
      />,
    )
    expect(screen.getByText('Alpha Fund')).toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------
// Test 3: All 7 metric labels render
// ---------------------------------------------------------------------------

describe('PortfolioAnalyticsClient — 7-metric grid', () => {
  it('renders all 7 metric labels', () => {
    render(
      <PortfolioAnalyticsClient
        portfolioId="abc"
        portfolioName="Test"
        analytics={MOCK_ANALYTICS}
      />,
    )
    // Labels are uppercase; rendered via font-mono text
    const labels = ['Sharpe', 'Sortino', 'Calmar', 'Beta', 'Alpha', 'Max Drawdown', 'TWR']
    for (const label of labels) {
      const elements = screen.getAllByText(new RegExp(label, 'i'))
      expect(elements.length).toBeGreaterThan(0)
    }
  })

  it('renders Sharpe value', () => {
    render(
      <PortfolioAnalyticsClient
        portfolioId="abc"
        portfolioName="Test"
        analytics={MOCK_ANALYTICS}
      />,
    )
    expect(screen.getByText('1.23')).toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------
// Test 4: Beta null shows "—" and tooltip
// ---------------------------------------------------------------------------

describe('PortfolioAnalyticsClient — null values', () => {
  it('shows — for null Beta', () => {
    render(
      <PortfolioAnalyticsClient
        portfolioId="abc"
        portfolioName="Test"
        analytics={NULL_BETA_ANALYTICS}
      />,
    )
    // Multiple — possible (sharpe + beta + alpha all null here)
    const dashes = screen.getAllByText('—')
    expect(dashes.length).toBeGreaterThan(0)
  })

  it('Beta cell has tooltip about 30+ trading days when null', () => {
    render(
      <PortfolioAnalyticsClient
        portfolioId="abc"
        portfolioName="Test"
        analytics={NULL_BETA_ANALYTICS}
      />,
    )
    // The MetricCell with Beta label should have title attr when beta is null
    const container = document.querySelector('[title="Requires 30+ trading days of data"]')
    expect(container).not.toBeNull()
  })
})

// ---------------------------------------------------------------------------
// Test 5: CSV export link
// ---------------------------------------------------------------------------

describe('PortfolioAnalyticsClient — CSV export', () => {
  it('CSV export link points to correct URL', () => {
    render(
      <PortfolioAnalyticsClient
        portfolioId="my-portfolio-id"
        portfolioName="Test"
        analytics={MOCK_ANALYTICS}
      />,
    )
    const link = screen.getByText(/Export to TradingView CSV/)
    expect(link.closest('a')).toHaveAttribute('href', '/v1/portfolios/my-portfolio-id/tv-export.csv')
  })
})

// ---------------------------------------------------------------------------
// Test 6: Positive Sharpe → signal-pos; negative → signal-neg
// ---------------------------------------------------------------------------

describe('PortfolioAnalyticsClient — value colors', () => {
  it('positive Sharpe value renders without signal-neg', () => {
    const { container } = render(
      <PortfolioAnalyticsClient
        portfolioId="abc"
        portfolioName="Test"
        analytics={MOCK_ANALYTICS}
      />,
    )
    // The "1.23" text should be in a signal-pos element
    const sharpeEl = screen.getByText('1.23')
    expect(sharpeEl.className).toContain('text-signal-pos')
    // container used to suppress unused var lint
    expect(container).toBeTruthy()
  })

  it('negative Sharpe value has text-signal-neg class', () => {
    render(
      <PortfolioAnalyticsClient
        portfolioId="abc"
        portfolioName="Test"
        analytics={NEGATIVE_ANALYTICS}
      />,
    )
    // "-0.45" sharpe should render in text-signal-neg
    const sharpeEl = screen.getByText('-0.45')
    expect(sharpeEl.className).toContain('text-signal-neg')
  })
})

// ---------------------------------------------------------------------------
// Test 7: Recharts chart renders
// ---------------------------------------------------------------------------

describe('PortfolioAnalyticsClient — chart', () => {
  it('renders cumulative returns chart', () => {
    render(
      <PortfolioAnalyticsClient
        portfolioId="abc"
        portfolioName="Test"
        analytics={MOCK_ANALYTICS}
      />,
    )
    expect(screen.getByTestId('responsive-container')).toBeInTheDocument()
    expect(screen.getByTestId('line-chart')).toBeInTheDocument()
  })
})
