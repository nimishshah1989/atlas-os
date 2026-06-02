'use client'

import { useEffect, useRef } from 'react'
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

// TradingView Advanced Chart via the external-embedding script API.
// The script reads its own textContent as a JSON config and resolves NSE:SYMBOL correctly.
// widgetembed (URL-param approach) is deprecated and defaults to AAPL for many symbols.
function TVAdvancedChart({ symbol }: { symbol: string }) {
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const container = containerRef.current
    if (!container) return

    container.innerHTML = ''

    const widgetDiv = document.createElement('div')
    widgetDiv.className = 'tradingview-widget-container__widget'
    widgetDiv.style.cssText = 'height:100%;width:100%'
    container.appendChild(widgetDiv)

    const script = document.createElement('script')
    script.src = 'https://s3.tradingview.com/external-embedding/embed-widget-advanced-chart.js'
    script.type = 'text/javascript'
    script.async = true
    script.textContent = JSON.stringify({
      autosize: true,
      symbol: `NSE:${symbol}`,
      interval: 'D',
      timezone: 'Asia/Kolkata',
      theme: 'light',
      style: '1',
      locale: 'en',
      allow_symbol_change: false,
      calendar: false,
      hide_side_toolbar: false,
      studies: ['STD;SMA', 'STD;EMA', 'STD;Volume'],
    })
    container.appendChild(script)

    return () => {
      if (containerRef.current) containerRef.current.innerHTML = ''
    }
  }, [symbol])

  return (
    <div
      className="tradingview-widget-container w-full"
      ref={containerRef}
      style={{ height: '480px' }}
    />
  )
}

export function StockChartPanel({ symbol, commentary, pe, ps, pb, debtToEquity, roe }: StockChartPanelProps) {
  const tvOpenUrl = `https://www.tradingview.com/symbols/NSE-${encodeURIComponent(symbol)}/`

  return (
    <section className="border-b border-paper-rule">
      <div className="relative">
        <TVAdvancedChart symbol={symbol} />
        <a
          href={tvOpenUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="absolute top-2 right-2 font-sans text-[11px] text-ink-tertiary hover:text-teal transition-colors bg-paper/80 px-2 py-1 rounded-[2px] z-10"
        >
          Open in TradingView ↗
        </a>
      </div>
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
