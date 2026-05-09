// frontend/src/components/sectors/SectorStocksTab.tsx
'use client'
import { useState, useMemo } from 'react'
import { Info } from 'lucide-react'
import type { StockRow } from '@/lib/queries/sector-deep-dive'
import type { TimeRange } from '@/lib/time-range'
import { StockBubbleChart } from './StockBubbleChart'
import { StocksTable } from './StocksTable'
import { TopPicksCallout } from './TopPicksCallout'
import type { MarketRegimeRow } from '@/lib/queries/regime'
import { MarketRegimeBanner } from './MarketRegimeBanner'

type Filter = 'all' | 'investable' | 'nifty50' | 'nifty100' | 'nifty500'

const FILTERS: { id: Filter; label: string }[] = [
  { id: 'all',        label: 'All' },
  { id: 'investable', label: 'Investable only' },
  { id: 'nifty50',    label: 'Nifty 50' },
  { id: 'nifty100',   label: 'Nifty 100' },
  { id: 'nifty500',   label: 'Nifty 500' },
]

export function SectorStocksTab({
  sectorName,
  stocks,
  range,
  regime,
}: {
  sectorName: string
  stocks: StockRow[]
  range?: TimeRange
  regime: MarketRegimeRow | null
}) {
  const [filter, setFilter] = useState<Filter>('all')
  const [unit, setUnit] = useState<'inr' | 'gold'>('inr')

  const filtered = useMemo(() => {
    switch (filter) {
      case 'investable': return stocks.filter(s => s.is_investable === true)
      case 'nifty50':    return stocks.filter(s => s.in_nifty_50)
      case 'nifty100':   return stocks.filter(s => s.in_nifty_100)
      case 'nifty500':   return stocks.filter(s => s.in_nifty_500)
      default:           return stocks
    }
  }, [stocks, filter])

  // Hide gold toggle if literally no stocks have gold data
  const hasAnyGold = stocks.some(s => s.rs_3m_tier_gold != null)

  if (stocks.length === 0) {
    return (
      <div className="max-w-[920px]">
        {regime && <MarketRegimeBanner regime={regime} />}
        <div className="px-6 py-12">
          <div className="px-6 py-12 border border-paper-rule rounded-sm text-center">
            <p className="font-sans text-sm text-ink-secondary mb-1">
              No stocks classified to {sectorName}.
            </p>
            <p className="font-sans text-xs text-ink-tertiary">
              This sector may have too few constituents or may be a holding-company bucket. See the Methodology tab (coming soon).
            </p>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div>
      {regime && <MarketRegimeBanner regime={regime} />}
      <div className="px-6 py-6 space-y-5">
      {/* Top Picks callout */}
      <TopPicksCallout stocks={stocks} />

      {/* Bubble chart */}
      <div>
        <div className="flex items-baseline gap-3 mb-3">
          <h3 className="font-sans text-xs font-medium text-ink-tertiary uppercase tracking-wider flex items-center gap-1.5">
            Stock Positioning Matrix
            <span title="Each bubble is a stock in this sector. X = 3-month absolute return (right is positive). Y = RS percentile vs peers within the same tier (up = top of pack). Bubble size = recommended position size. LEADERS (top-right) = positive return + outperforming peers. LAGGARDS (bottom-left) = losing money + underperforming.">
              <Info className="w-3 h-3 opacity-60 cursor-help" />
            </span>
          </h3>
          <span className="font-sans text-xs text-ink-tertiary">{filtered.length} of {stocks.length} stocks · current snapshot</span>
        </div>
        <StockBubbleChart stocks={filtered} />
      </div>

      {/* Filter + unit toggle */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-1.5 flex-wrap">
          <span className="font-sans text-[10px] text-ink-tertiary uppercase tracking-wider mr-1">Filter:</span>
          {FILTERS.map(f => (
            <button
              key={f.id}
              onClick={() => setFilter(f.id)}
              className={`px-2.5 py-1 rounded-[2px] font-sans text-xs transition-colors ${
                filter === f.id
                  ? 'bg-ink-primary text-paper'
                  : 'border border-paper-rule text-ink-secondary hover:bg-paper-rule/30'
              }`}
            >
              {f.label}
              {f.id === 'investable' && (
                <span className="ml-1 text-[10px] opacity-70">
                  ({stocks.filter(s => s.is_investable === true).length})
                </span>
              )}
            </button>
          ))}
        </div>

        {hasAnyGold && (
          <div className="inline-flex border border-paper-rule rounded-[2px] overflow-hidden" role="group" aria-label="Currency unit">
            <button
              onClick={() => setUnit('inr')}
              className={`px-2.5 py-1 font-sans text-xs transition-colors ${unit === 'inr' ? 'bg-accent text-paper' : 'text-ink-secondary hover:bg-paper-rule/30'}`}
              aria-pressed={unit === 'inr'}
            >
              ₹ INR
            </button>
            <button
              onClick={() => setUnit('gold')}
              className={`px-2.5 py-1 font-sans text-xs transition-colors ${unit === 'gold' ? 'bg-accent text-paper' : 'text-ink-secondary hover:bg-paper-rule/30'}`}
              aria-pressed={unit === 'gold'}
            >
              Au Gold
            </button>
          </div>
        )}
      </div>

      {/* Table */}
      <StocksTable stocks={filtered} unit={unit} activeRange={range} />
    </div>
    </div>
  )
}
