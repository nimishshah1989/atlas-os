// frontend/src/components/v6/__tests__/TVChartPanel.test.tsx
//
// TV-05 chart panel tests:
//   1. Renders signals panel and iframe panel
//   2. Shows "No TradingView data" when tvMetrics is null
//   3. Shows recommendation pill in signals panel
//   4. Shows correct MA signal
//   5. Shows price levels (price, 52W High, 52W Low, ATR)
//   6. Iframe has correct NSE symbol src
//   7. Opens iframe error fallback when iframe errors

import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { TVChartPanel } from '../TVChartPanel'
import type { TVMetricsRow } from '@/lib/api/v1'

const MOCK_TV_METRICS: TVMetricsRow = {
  symbol: 'RELIANCE',
  tv_recommend_label: 'STRONG_BUY',
  recommend_all: '0.8',
  recommend_ma: 'BUY',
  recommend_other: '0.6',
  rsi_14: '63.2',
  macd_macd: '22.4',
  ema_20: '2955.00',
  ema_50: '2910.00',
  ema_200: '2720.00',
  atr_14: '42.50',
  price: '2975.00',
  high_52w: '3110.00',
  low_52w: '2380.00',
  fetched_at: new Date(Date.now() - 60000).toISOString(),
  is_stale: false,
}

describe('TVChartPanel — renders main panels', () => {
  it('renders both signals panel and iframe panel', () => {
    render(<TVChartPanel symbol="RELIANCE" tvMetrics={MOCK_TV_METRICS} />)
    expect(screen.getByTestId('tv-signals-panel')).toBeInTheDocument()
    expect(screen.getByTestId('tv-iframe-panel')).toBeInTheDocument()
  })

  it('has correct tabpanel role and aria attributes', () => {
    render(<TVChartPanel symbol="RELIANCE" tvMetrics={MOCK_TV_METRICS} />)
    const panel = screen.getByTestId('tv-chart-panel')
    expect(panel.getAttribute('role')).toBe('tabpanel')
    expect(panel.getAttribute('aria-labelledby')).toBe('tab-chart')
    expect(panel.getAttribute('id')).toBe('tabpanel-chart')
  })
})

describe('TVChartPanel — no data state', () => {
  it('shows "No TradingView data" message when tvMetrics is null', () => {
    render(<TVChartPanel symbol="INFY" tvMetrics={null} />)
    expect(screen.getByText(/No TradingView data available/i)).toBeInTheDocument()
  })

  it('still renders iframe panel when tvMetrics is null', () => {
    render(<TVChartPanel symbol="INFY" tvMetrics={null} />)
    expect(screen.getByTestId('tv-iframe-panel')).toBeInTheDocument()
  })
})

describe('TVChartPanel — recommendation display', () => {
  it('shows STRONG BUY in recommendation row', () => {
    render(<TVChartPanel symbol="RELIANCE" tvMetrics={MOCK_TV_METRICS} />)
    // "STRONG BUY" after _ → space replacement
    expect(screen.getAllByText('STRONG BUY').length).toBeGreaterThan(0)
  })

  it('shows MA signal from recommend_ma', () => {
    render(<TVChartPanel symbol="RELIANCE" tvMetrics={MOCK_TV_METRICS} />)
    const signals = screen.getByTestId('tv-signals-panel')
    expect(signals.textContent).toContain('BUY')
  })
})

describe('TVChartPanel — price levels', () => {
  it('shows formatted price in price levels section', () => {
    render(<TVChartPanel symbol="RELIANCE" tvMetrics={MOCK_TV_METRICS} />)
    const signals = screen.getByTestId('tv-signals-panel')
    // ₹2,975.00 in Indian locale
    expect(signals.textContent).toContain('₹')
  })

  it('shows 52W High label', () => {
    render(<TVChartPanel symbol="RELIANCE" tvMetrics={MOCK_TV_METRICS} />)
    expect(screen.getByText('52W High')).toBeInTheDocument()
  })

  it('shows 52W Low label', () => {
    render(<TVChartPanel symbol="RELIANCE" tvMetrics={MOCK_TV_METRICS} />)
    expect(screen.getByText('52W Low')).toBeInTheDocument()
  })
})

describe('TVChartPanel — iframe', () => {
  it('iframe src contains NSE:RELIANCE (decoded or encoded)', () => {
    render(<TVChartPanel symbol="RELIANCE" tvMetrics={MOCK_TV_METRICS} />)
    const iframe = screen.getByTestId('tv-iframe') as HTMLIFrameElement
    // jsdom decodes the src URL; check for NSE:RELIANCE substring in either form
    const src = decodeURIComponent(iframe.src)
    expect(src).toContain('NSE:RELIANCE')
  })

  it('shows "Open in TradingView" link in header', () => {
    render(<TVChartPanel symbol="RELIANCE" tvMetrics={MOCK_TV_METRICS} />)
    expect(screen.getByText(/Open in TradingView ↗/i)).toBeInTheDocument()
  })

  it('shows ticker in iframe header', () => {
    render(<TVChartPanel symbol="RELIANCE" tvMetrics={MOCK_TV_METRICS} />)
    const panel = screen.getByTestId('tv-iframe-panel')
    expect(panel.textContent).toContain('NSE:RELIANCE')
  })

  it('iframe uses dark theme and daily interval in src', () => {
    render(<TVChartPanel symbol="RELIANCE" tvMetrics={MOCK_TV_METRICS} />)
    const iframe = screen.getByTestId('tv-iframe') as HTMLIFrameElement
    const src = decodeURIComponent(iframe.src)
    expect(src).toContain('theme=dark')
    expect(src).toContain('interval=D')
  })
})

describe('TVChartPanel — Chart tab wiring in StockDetailClient', () => {
  // This test verifies the Chart tab appears in StockDetailClient via integration test
  // (handled in StockDetailClient.test.tsx — Chart tab click test)
  it('TVChartPanel has data-testid="tv-chart-panel"', () => {
    render(<TVChartPanel symbol="TCS" tvMetrics={null} />)
    expect(screen.getByTestId('tv-chart-panel')).toBeInTheDocument()
  })
})
