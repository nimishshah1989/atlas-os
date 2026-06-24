'use client'

// TVRatioChart — a DIRECT TradingView Advanced-Chart embed for a (ratio) symbol, e.g.
// "NSE:NIFTYMIDCAP150/NSE:CNX500" or "NSE:CNXIT/NSE:NIFTY". Zero Atlas data/code — TV's
// data and servers. Used for the index-ratio RS charts where a confirmed TV symbol exists
// (cap-tier RS, sector RS, ETF-vs-benchmark RS).
//
// Built on the same external-embedding script the stock-detail price chart uses (the
// widgetembed URL approach is deprecated and defaults to AAPL for many symbols).
//
// NOTE: TradingView blocks headless browsers, so this renders BLANK under Playwright —
// that is expected. Verify the live render in a real browser.
import { useEffect, useRef } from 'react'

function TVAdvancedRatio({ symbol, height, interval }: { symbol: string; height: number; interval: string }) {
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
      symbol,
      interval,
      timezone: 'Asia/Kolkata',
      theme: 'light',
      style: '3', // line — a ratio reads cleanest as a single line
      locale: 'en',
      allow_symbol_change: false,
      calendar: false,
      hide_side_toolbar: true,
    })
    container.appendChild(script)

    return () => {
      if (containerRef.current) containerRef.current.innerHTML = ''
    }
  }, [symbol, interval])

  return <div className="tradingview-widget-container w-full" ref={containerRef} style={{ height }} />
}

export function TVRatioChart({
  symbol, title, subtitle, height = 360, interval = 'W',
}: {
  symbol: string
  title?: string
  subtitle?: string
  height?: number
  interval?: string
}) {
  const openUrl = `https://www.tradingview.com/chart/?symbol=${encodeURIComponent(symbol)}`
  return (
    <div className="bg-paper border border-paper-rule rounded-sm overflow-hidden">
      {(title || subtitle) && (
        <div className="flex items-baseline justify-between gap-2 px-3 pt-2.5 pb-1.5 border-b border-paper-rule/60">
          <div>
            {title && <div className="font-sans text-[12px] text-ink-secondary font-medium">{title}</div>}
            {subtitle && <div className="font-sans text-[10px] text-ink-tertiary mt-0.5">{subtitle}</div>}
          </div>
          <a href={openUrl} target="_blank" rel="noopener noreferrer"
             className="font-sans text-[10px] text-ink-tertiary hover:text-teal transition-colors whitespace-nowrap shrink-0">
            TradingView ↗
          </a>
        </div>
      )}
      <TVAdvancedRatio symbol={symbol} height={height} interval={interval} />
    </div>
  )
}
