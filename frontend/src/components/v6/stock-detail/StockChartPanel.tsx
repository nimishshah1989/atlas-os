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

function tvUrl(symbol: string): string {
  const encodedSymbol = encodeURIComponent(`NSE:${symbol}`)
  return (
    `https://www.tradingview.com/widgetembed/?frameElementId=tradingview_atlas` +
    `&symbol=${encodedSymbol}&interval=W&hidesidetoolbar=1&hidetoptoolbar=0` +
    `&symboledit=0&saveimage=0&toolbarbg=1A1714&theme=Dark&style=1` +
    `&timezone=Asia%2FKolkata&locale=en`
  )
}

export function StockChartPanel({ symbol, commentary, pe, ps, pb, debtToEquity, roe }: StockChartPanelProps) {
  const [chartError, setChartError] = useState(false)

  return (
    <section className="border-b border-paper-rule">
      {chartError ? (
        <div className="bg-paper-deep flex items-center justify-center h-[300px]">
          <div className="text-center">
            <p className="font-sans text-sm text-ink-3 mb-2">Chart unavailable</p>
            <a href={`https://www.tradingview.com/chart/?symbol=NSE:${symbol}`} target="_blank" rel="noopener noreferrer" className="font-sans text-sm text-accent hover:underline">
              Open in TradingView ↗
            </a>
          </div>
        </div>
      ) : (
        <iframe
          src={tvUrl(symbol)}
          className="w-full h-[340px] md:h-[420px] border-0"
          onError={() => setChartError(true)}
          title={`${symbol} weekly price chart`}
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
