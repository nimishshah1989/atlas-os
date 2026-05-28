// frontend/src/components/v6/__tests__/TVMetricsBadge.test.tsx
//
// TV-05 badge tests:
//   1. Renders null when tvRecommendLabel=null and fetchedAt=null (no data)
//   2. Shows BUY pill with signal-pos color
//   3. Shows STRONG SELL pill with signal-neg color
//   4. Shows NEUTRAL pill with signal-warn color
//   5. Shows stale label when fetchedAt > 2 days
//   6. Does not show stale label when fetchedAt < 2 days
//   7. Shows RSI and MACD values
//   8. TVMetricsBadgeFromRow renders null for null row

import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { TVMetricsBadge, TVMetricsBadgeFromRow } from '../TVMetricsBadge'
import type { TVMetricsRow } from '@/lib/api/v1'

// ---------------------------------------------------------------------------
// Test 1: Renders null when no data
// ---------------------------------------------------------------------------

describe('TVMetricsBadge — renders null when no data', () => {
  it('returns null when tvRecommendLabel=null and fetchedAt=null', () => {
    const { container } = render(
      <TVMetricsBadge
        symbol="RELIANCE"
        tvRecommendLabel={null}
        recommendAll={null}
        rsi14={null}
        macdMacd={null}
        fetchedAt={null}
      />,
    )
    expect(container.firstChild).toBeNull()
  })
})

// ---------------------------------------------------------------------------
// Test 2: BUY pill color
// ---------------------------------------------------------------------------

describe('TVMetricsBadge — BUY signal', () => {
  it('shows BUY pill with signal-pos color', () => {
    const recentDate = new Date(Date.now() - 60000).toISOString()
    render(
      <TVMetricsBadge
        symbol="RELIANCE"
        tvRecommendLabel="BUY"
        recommendAll={0.5}
        rsi14={58.3}
        macdMacd={12.4}
        fetchedAt={recentDate}
      />,
    )
    const pill = screen.getByTestId('tv-recommend-pill')
    expect(pill).toBeInTheDocument()
    expect(pill.textContent).toContain('BUY')
    // Spec TV-05: BUY → bg-signal-pos text-white
    expect(pill.className).toContain('bg-signal-pos')
    expect(pill.className).toContain('text-white')
  })

  it('shows STRONG BUY pill with signal-pos background', () => {
    const recentDate = new Date(Date.now() - 60000).toISOString()
    render(
      <TVMetricsBadge
        symbol="TCS"
        tvRecommendLabel="STRONG_BUY"
        recommendAll={0.8}
        rsi14={62.0}
        macdMacd={8.5}
        fetchedAt={recentDate}
      />,
    )
    const pill = screen.getByTestId('tv-recommend-pill')
    expect(pill.textContent).toContain('STRONG BUY')
    expect(pill.className).toContain('bg-signal-pos')
  })
})

// ---------------------------------------------------------------------------
// Test 3: STRONG SELL pill color
// ---------------------------------------------------------------------------

describe('TVMetricsBadge — SELL signal', () => {
  it('shows STRONG SELL pill with signal-neg color', () => {
    const recentDate = new Date(Date.now() - 60000).toISOString()
    render(
      <TVMetricsBadge
        symbol="ZOMATO"
        tvRecommendLabel="STRONG_SELL"
        recommendAll={-0.8}
        rsi14={28.0}
        macdMacd={-15.2}
        fetchedAt={recentDate}
      />,
    )
    const pill = screen.getByTestId('tv-recommend-pill')
    expect(pill.textContent).toContain('STRONG SELL')
    // Spec TV-05: SELL → bg-signal-neg text-white
    expect(pill.className).toContain('bg-signal-neg')
  })
})

// ---------------------------------------------------------------------------
// Test 4: NEUTRAL pill color
// ---------------------------------------------------------------------------

describe('TVMetricsBadge — NEUTRAL signal', () => {
  it('shows NEUTRAL pill with signal-warn color', () => {
    const recentDate = new Date(Date.now() - 60000).toISOString()
    render(
      <TVMetricsBadge
        symbol="INFY"
        tvRecommendLabel="NEUTRAL"
        recommendAll={0.0}
        rsi14={50.0}
        macdMacd={0.2}
        fetchedAt={recentDate}
      />,
    )
    const pill = screen.getByTestId('tv-recommend-pill')
    expect(pill.textContent).toContain('NEUTRAL')
    // Spec TV-05: NEUTRAL → bg-signal-warn text-white
    expect(pill.className).toContain('bg-signal-warn')
  })
})

// ---------------------------------------------------------------------------
// Test 5: Stale label when > 2 days
// ---------------------------------------------------------------------------

describe('TVMetricsBadge — stale label', () => {
  it('shows stale label when fetchedAt > 2 days old', () => {
    const staleDate = new Date(Date.now() - 3 * 24 * 60 * 60 * 1000).toISOString()
    render(
      <TVMetricsBadge
        symbol="HDFC"
        tvRecommendLabel="BUY"
        recommendAll={0.4}
        rsi14={55.0}
        macdMacd={5.0}
        fetchedAt={staleDate}
      />,
    )
    const staleEl = screen.getByTestId('tv-stale-label')
    expect(staleEl).toBeInTheDocument()
    expect(staleEl.textContent).toMatch(/^STALE \d{2}-[A-Za-z]{3}$/)
  })

  it('does NOT show stale label when fetchedAt is recent', () => {
    const recentDate = new Date(Date.now() - 60 * 60 * 1000).toISOString()
    render(
      <TVMetricsBadge
        symbol="HDFC"
        tvRecommendLabel="BUY"
        recommendAll={0.4}
        rsi14={55.0}
        macdMacd={5.0}
        fetchedAt={recentDate}
      />,
    )
    expect(screen.queryByTestId('tv-stale-label')).not.toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------
// Test 6: RSI and MACD values render
// ---------------------------------------------------------------------------

describe('TVMetricsBadge — RSI and MACD values', () => {
  it('shows RSI value', () => {
    const recentDate = new Date(Date.now() - 60000).toISOString()
    render(
      <TVMetricsBadge
        symbol="WIPRO"
        tvRecommendLabel="BUY"
        recommendAll={0.3}
        rsi14={64.7}
        macdMacd={9.1}
        fetchedAt={recentDate}
      />,
    )
    const badge = screen.getByTestId('tv-metrics-badge')
    expect(badge.textContent).toContain('RSI')
    expect(badge.textContent).toContain('64.7')
  })

  it('shows MACD value with sign', () => {
    const recentDate = new Date(Date.now() - 60000).toISOString()
    render(
      <TVMetricsBadge
        symbol="WIPRO"
        tvRecommendLabel="BUY"
        recommendAll={0.3}
        rsi14={64.7}
        macdMacd={9.1}
        fetchedAt={recentDate}
      />,
    )
    const badge = screen.getByTestId('tv-metrics-badge')
    expect(badge.textContent).toContain('MACD')
    expect(badge.textContent).toContain('+9.10')
  })

  it('shows — for null RSI', () => {
    const recentDate = new Date(Date.now() - 60000).toISOString()
    render(
      <TVMetricsBadge
        symbol="WIPRO"
        tvRecommendLabel="BUY"
        recommendAll={0.3}
        rsi14={null}
        macdMacd={null}
        fetchedAt={recentDate}
      />,
    )
    // Multiple — possible (RSI + MACD). Check RSI section contains —
    const badge = screen.getByTestId('tv-metrics-badge')
    expect(badge.textContent).toContain('RSI')
    expect(badge.textContent).toContain('—')
  })
})

// ---------------------------------------------------------------------------
// Test 7: TVMetricsBadgeFromRow — renders null for null row
// ---------------------------------------------------------------------------

describe('TVMetricsBadgeFromRow', () => {
  it('renders null when row is null', () => {
    const { container } = render(
      <TVMetricsBadgeFromRow symbol="TEST" row={null} />,
    )
    expect(container.firstChild).toBeNull()
  })

  it('renders badge for a full row', () => {
    const row: TVMetricsRow = {
      symbol: 'RELIANCE',
      tv_recommend_label: 'BUY',
      recommend_all: '0.4',
      recommend_ma: '0.6',
      recommend_other: '0.2',
      rsi_14: '61.5',
      macd_macd: '14.3',
      ema_20: '2950.00',
      ema_50: '2900.00',
      ema_200: '2700.00',
      atr_14: '45.00',
      price: '2980.00',
      high_52w: '3100.00',
      low_52w: '2400.00',
      fetched_at: new Date(Date.now() - 60000).toISOString(),
      is_stale: false,
    }
    render(<TVMetricsBadgeFromRow symbol="RELIANCE" row={row} />)
    expect(screen.getByTestId('tv-metrics-badge')).toBeInTheDocument()
    expect(screen.getByTestId('tv-recommend-pill').textContent).toContain('BUY')
  })
})
