'use client'

// Sector vs stock 12-month sparkline comparison with period selector.
// Explains relative-strength divergence to users who may not know what to look for.

import { useState } from 'react'
import { TVMiniOverview } from './TVWidgets'

type DateRange = '1M' | '3M' | '6M' | '12M'

interface SparklineComparisonPanelProps {
  symbol: string
  sectorLabel: string
  sectorTvSymbol: string
}

const PERIODS: { label: string; value: DateRange }[] = [
  { label: '1M', value: '1M' },
  { label: '3M', value: '3M' },
  { label: '6M', value: '6M' },
  { label: '12M', value: '12M' },
]

export function SparklineComparisonPanel({
  symbol,
  sectorLabel,
  sectorTvSymbol,
}: SparklineComparisonPanelProps) {
  const [period, setPeriod] = useState<DateRange>('12M')

  return (
    <section className="px-6 py-4 border-b border-paper-rule bg-paper-deep">
      {/* Header with period selector */}
      <div className="flex items-start justify-between mb-3">
        <div>
          <p className="font-mono text-[10px] uppercase tracking-wider text-ink-tertiary">
            Price Momentum — Stock vs. Sector
          </p>
          <p className="font-sans text-[11px] text-ink-secondary mt-0.5">
            Divergence between the stock and its sector index signals relative strength or weakness
          </p>
        </div>
        <div className="flex gap-1 shrink-0 ml-4">
          {PERIODS.map((p) => (
            <button
              key={p.value}
              onClick={() => setPeriod(p.value)}
              className={[
                'px-2.5 py-1 font-mono text-[10px] uppercase rounded-[2px] transition-colors border',
                period === p.value
                  ? 'bg-teal text-paper border-teal font-semibold'
                  : 'bg-paper border-paper-rule text-ink-tertiary hover:text-ink-primary hover:border-ink-tertiary',
              ].join(' ')}
            >
              {p.label}
            </button>
          ))}
        </div>
      </div>

      {/* Sparklines */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="border border-paper-rule rounded-[2px] p-4 bg-paper">
          <p className="font-mono text-[10px] uppercase tracking-wider text-ink-tertiary mb-1">
            {sectorLabel} · {period}
          </p>
          <TVMiniOverview symbol={sectorTvSymbol} exchange="NSE" dateRange={period} />
        </div>
        <div className="border border-paper-rule rounded-[2px] p-4 bg-paper">
          <p className="font-mono text-[10px] uppercase tracking-wider text-ink-tertiary mb-1">
            {symbol} · {period}
          </p>
          <TVMiniOverview symbol={symbol} exchange="NSE" dateRange={period} />
        </div>
      </div>

      {/* How to read commentary */}
      <div className="mt-3 p-3 bg-paper border border-paper-rule rounded-[2px]">
        <p className="font-mono text-[10px] uppercase tracking-wider text-teal mb-1">How to read this</p>
        <p className="font-sans text-[11px] text-ink-secondary leading-relaxed">
          <strong className="font-semibold text-ink-primary">Stock trending above sector</strong> — relative strength (RS) is positive; institutional money is rotating into this name.{' '}
          <strong className="font-semibold text-ink-primary">Stock lagging sector</strong> — RS is weakening; sector tailwind isn't lifting this stock.{' '}
          Use <span className="font-semibold">3M</span> to confirm current momentum direction;{' '}
          <span className="font-semibold">12M</span> shows the full trend cycle. Atlas enters only when stock RS is in the top 40th percentile.
        </p>
      </div>
    </section>
  )
}
