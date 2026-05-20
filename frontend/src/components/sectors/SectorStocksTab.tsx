// frontend/src/components/sectors/SectorStocksTab.tsx
// allow-large: this file is the main stocks tab — RSDistribution, ReturnConcentration, and the overextension callout must all live here to share the `stocks` array without prop drilling through parent shells
'use client'
import { useState, useMemo } from 'react'
import Link from 'next/link'
import { Info, AlertTriangle } from 'lucide-react'
import { RSStateChip } from '@/lib/stock-formatters'
import type { StockRow } from '@/lib/queries/sector-deep-dive'
import type { TimeRange } from '@/lib/time-range'
import { StockBubbleChart } from './StockBubbleChart'
import { StocksTable } from './StocksTable'
import { TopPicksCallout } from './TopPicksCallout'
import { SectorMultiStateBreadth } from './SectorMultiStateBreadth'
import { SectorQualityPanel } from './SectorQualityPanel'
import type { MarketRegimeRow } from '@/lib/queries/regime'
import { MarketRegimeBanner } from './MarketRegimeBanner'

const RS_STATES = ['Leader', 'Strong', 'Consolidating', 'Emerging', 'Average', 'Weak', 'Laggard'] as const
const RS_COLORS: Record<string, string> = {
  Leader:        '#2F6B43',
  Strong:        '#4CAF78',
  Consolidating: '#1D9E75',
  Emerging:      '#d97706',
  Average:       '#94a3b8',
  Weak:          '#ef6644',
  Laggard:       '#B0492C',
}

function RSDistributionBar({ stocks }: { stocks: { rs_state: string | null }[] }) {
  const total = stocks.length
  if (total === 0) return null
  const counts = RS_STATES.map(s => ({
    state: s,
    count: stocks.filter(st => st.rs_state === s).length,
  })).filter(x => x.count > 0)

  return (
    <div className="space-y-2">
      <div className="font-sans text-[10px] text-ink-tertiary uppercase tracking-wider">
        RS State Distribution
      </div>
      <div className="flex h-3 rounded-sm overflow-hidden gap-px">
        {counts.map(({ state, count }) => (
          <div
            key={state}
            style={{ width: `${(count / total) * 100}%`, background: RS_COLORS[state] }}
            title={`${state}: ${count}`}
          />
        ))}
      </div>
      <div className="flex flex-wrap gap-x-3 gap-y-1">
        {counts.map(({ state, count }) => (
          <span key={state} className="inline-flex items-center gap-1 font-sans text-[10px] text-ink-secondary">
            <RSStateChip value={state} />
            <span className="text-ink-tertiary">{count}</span>
          </span>
        ))}
      </div>
    </div>
  )
}

function ReturnConcentrationBar({ stocks, range }: { stocks: StockRow[]; range?: TimeRange }) {
  const field = range === '1M' ? 'ret_1m' : range === '6M' ? 'ret_6m' : 'ret_3m'
  const label = range === '1M' ? '1M' : range === '6M' ? '6M' : '3M'

  const valid = useMemo(
    () =>
      stocks
        .filter(s => s[field] != null && !isNaN(parseFloat(s[field] as string)))
        .map(s => ({ ...s, ret: parseFloat(s[field] as string) }))
        .sort((a, b) => b.ret - a.ret),
    [stocks, field],
  )

  if (valid.length < 4) return null

  const top5  = valid.slice(0, 5)
  const bot3  = valid.slice(-3).reverse()
  const maxAbs = Math.max(...valid.map(s => Math.abs(s.ret)))

  const Bar = ({ s, pos }: { s: typeof valid[0]; pos: boolean }) => (
    <div className="flex items-center gap-2">
      <div className="w-20 text-right font-sans text-[10px] text-ink-secondary truncate" title={s.company_name}>{s.symbol}</div>
      <div className="flex-1 bg-paper-rule/30 rounded-sm h-1.5 overflow-hidden">
        <div
          className={`h-full rounded-sm ${pos ? 'bg-signal-pos/60' : 'bg-signal-neg/60'}`}
          style={{ width: `${Math.abs(s.ret) / maxAbs * 100}%` }}
        />
      </div>
      <div className={`w-11 text-right font-sans text-[10px] font-medium tabular-nums ${s.ret >= 0 ? 'text-signal-pos' : 'text-signal-neg'}`}>
        {s.ret >= 0 ? '+' : ''}{(s.ret * 100).toFixed(1)}%
      </div>
      {!s.in_nifty_500 && (
        <span className="font-sans text-[8px] text-ink-tertiary bg-paper-rule/40 px-1 rounded leading-4">off-idx</span>
      )}
    </div>
  )

  const offIdxCount = top5.filter(s => !s.in_nifty_500).length

  return (
    <div className="space-y-2.5">
      <div className="font-sans text-[10px] text-ink-tertiary uppercase tracking-wider">Return Drivers — {label}</div>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-2">
        <div className="space-y-1.5">
          <div className="font-sans text-[10px] text-signal-pos/80 font-medium">Top Contributors</div>
          {top5.map(s => <Bar key={s.symbol} s={s} pos />)}
        </div>
        <div className="space-y-1.5">
          <div className="font-sans text-[10px] text-signal-neg/80 font-medium">Bottom Contributors</div>
          {bot3.map(s => <Bar key={s.symbol} s={s} pos={s.ret >= 0} />)}
        </div>
      </div>
      {offIdxCount >= 2 && (
        <div className="font-sans text-[10px] text-ink-tertiary leading-relaxed">
          <span className="text-ink-secondary font-medium">{offIdxCount} of the top 5</span> are off-index (not in Nifty 500). This explains a higher bottom-up average vs the top-down index return — the index only captures index constituents, market-cap weighted.
        </div>
      )}
    </div>
  )
}

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

  // Detect sector-strong / stock-overextended divergence
  const overextensionAlert = useMemo(() => {
    const total = stocks.length
    if (total === 0) return null
    const investable = stocks.filter(s => s.is_investable === true).length
    if (investable > 0) return null // not needed when stocks are actionable
    const marketBlocked = stocks.filter(s => s.market_gate === false).length
    if (marketBlocked > total * 0.5) return null // market-wide block, not sector-specific
    const highRisk = stocks.filter(s => s.risk_state === 'High' || s.risk_state === 'Below Trend').length
    const goodRS = stocks.filter(s => ['Leader', 'Strong', 'Emerging'].includes(s.rs_state ?? '')).length
    if (highRisk > total * 0.3 && goodRS > total * 0.15) {
      return { highRisk, goodRS, total }
    }
    return null
  }, [stocks])

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
      {/* Screener handoff — step 2→3 of the decision flow */}
      <div className="flex items-center justify-between">
        <span className="font-sans text-xs text-ink-tertiary">
          {stocks.length} stocks in {sectorName}
        </span>
        <Link
          href={`/stocks?sector=${encodeURIComponent(sectorName)}`}
          className="inline-flex items-center gap-1 font-sans text-xs font-medium text-teal hover:underline"
        >
          View all {sectorName} stocks in screener →
        </Link>
      </div>

      {/* Top Picks callout */}
      <TopPicksCallout stocks={stocks} />

      {/* Overextension divergence callout */}
      {overextensionAlert && (
        <div className="border border-signal-warn/30 bg-signal-warn/5 rounded-sm p-3">
          <div className="flex items-start gap-2">
            <AlertTriangle className="w-3.5 h-3.5 text-signal-warn flex-shrink-0 mt-0.5" />
            <div className="space-y-1">
              <div className="font-sans text-xs font-semibold text-signal-warn">
                Sector Strong — Stocks Overextended
              </div>
              <div className="font-sans text-[11px] text-ink-secondary leading-relaxed">
                This sector has good relative strength ({overextensionAlert.goodRS} stocks with Leader/Strong/Emerging RS),
                but {overextensionAlert.highRisk} of {overextensionAlert.total} stocks are failing the Risk Gate
                because they are significantly above their moving averages (risk_state = High or Below Trend).
                No stocks are currently investable — the sector's RS is real but the entry risk is elevated.
              </div>
              <div className="font-sans text-[11px] text-ink-tertiary leading-relaxed">
                Wait for a pullback. Stocks that correct while the sector stays Overweight become high-conviction entries.
                Monitor the RS and Direction gates — stocks that hold their RS during a price correction are the strongest candidates.
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Return concentration — who's driving this sector's returns */}
      <ReturnConcentrationBar stocks={stocks} range={range} />

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

      {/* RS Distribution + multi-state breadth */}
      <RSDistributionBar stocks={filtered} />
      <SectorMultiStateBreadth stocks={filtered} />

      {/* Quality & signal funnel */}
      <SectorQualityPanel stocks={filtered} />

      {/* Table */}
      <StocksTable stocks={filtered} unit={unit} activeRange={range} />
    </div>
    </div>
  )
}
