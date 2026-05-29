'use client'

import { useState } from 'react'
import { FundamentalsStrip } from './FundamentalsStrip'

interface StockChartPanelProps {
  symbol: string
  commentary: string
  pe: number | null
  ps: number | null
  pb: number | null
  debtToEquity: number | null
  roe: number | null
}

// Light-theme widgetembed URL — white background matches Atlas paper tokens.
// `allow_symbol_change=0` prevents the chart from drifting to other symbols.
function tvUrl(symbol: string): string {
  const params = new URLSearchParams({
    symbol: `NSE:${symbol}`,
    interval: 'D',
    timezone: 'Asia/Kolkata',
    theme: 'light',
    style: '1',
    locale: 'en',
    toolbar_bg: '#F8F4EC',
    hide_side_toolbar: 'false',
    hide_top_toolbar: 'false',
    allow_symbol_change: 'false',
    studies: '["MASimple@tv-basicstudies","MASimple@tv-basicstudies","MAExp@tv-basicstudies","Volume@tv-basicstudies"]',
  })
  return `https://www.tradingview.com/widgetembed/?${params.toString()}`
}

export function StockChartPanel({ symbol, commentary, pe, ps, pb, debtToEquity, roe }: StockChartPanelProps) {
  const [chartError, setChartError] = useState(false)

  return (
    <section className="border-b border-paper-rule">
      {chartError ? (
        <div className="bg-paper-deep flex items-center justify-center h-[300px]">
          <div className="text-center">
            <p className="font-sans text-sm text-ink-3 mb-2">Chart unavailable</p>
            <a
              href={`https://www.tradingview.com/chart/?symbol=NSE:${symbol}`}
              target="_blank"
              rel="noopener noreferrer"
              className="font-sans text-sm text-accent hover:underline"
            >
              Open in TradingView ↗
            </a>
          </div>
        </div>
      ) : (
        <iframe
          src={tvUrl(symbol)}
          className="w-full h-[420px] md:h-[520px] border-0 bg-paper"
          sandbox="allow-scripts allow-same-origin allow-popups allow-popups-to-escape-sandbox"
          onError={() => setChartError(true)}
          title={`${symbol} daily price chart`}
          loading="lazy"
        />
      )}
      <div className="px-6 py-4 border-t border-paper-rule bg-paper">
        <p className="font-mono text-[10px] text-teal uppercase tracking-wider mb-2">Atlas Chart Reading</p>
        <p className="font-sans text-sm text-ink leading-relaxed">{commentary}</p>
      </div>
      <div className="px-6 pb-4">
        <FundamentalsStrip pe={pe} ps={ps} pb={pb} debtToEquity={debtToEquity} roe={roe} />
      </div>
    </section>
  )
}
