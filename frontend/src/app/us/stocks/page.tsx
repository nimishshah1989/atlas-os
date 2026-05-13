export const dynamic = 'force-dynamic'

import { getUSStocks, getUSSectorBreadth } from '@/lib/queries/us-stocks'
import { USSectorBreadthBar } from '@/components/us/USSectorBreadthBar'
import { USStockScreener } from '@/components/us/USStockScreener'

export default async function USStocksPage() {
  const [stocks, sectorBreadth] = await Promise.all([
    getUSStocks(),
    getUSSectorBreadth(),
  ])

  if (stocks.length === 0) {
    return (
      <div className="p-8">
        <p className="font-sans text-sm text-ink-secondary">
          No US stock data available. Run the US stocks backfill first.
        </p>
      </div>
    )
  }

  const dataAsOf   = stocks.find(s => s.data_as_of)?.data_as_of ?? null
  const totalCount = stocks.length
  const liveCount  = stocks.filter(s => s.history_gate_pass && s.liquidity_gate_pass).length
  const leaderCount = stocks.filter(s => s.rs_state === 'Leader' || s.rs_state === 'Strong').length
  const accelCount  = stocks.filter(
    s => s.momentum_state === 'Accelerating' || s.momentum_state === 'Improving'
  ).length

  return (
    <div className="max-w-[1600px] mx-auto">
      {/* Header band */}
      <div className="px-6 py-4 border-b border-paper-rule flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-6 flex-wrap">
          <h1 className="font-sans text-sm font-semibold text-ink-primary uppercase tracking-wide">
            US Stock Universe
          </h1>
          <span className="flex items-center gap-1.5 font-sans text-xs text-ink-secondary">
            <span className="inline-block w-2 h-2 rounded-full bg-ink-tertiary" />
            {totalCount} tickers
          </span>
          <span className="flex items-center gap-1.5 font-sans text-xs text-ink-secondary">
            <span className="inline-block w-2 h-2 rounded-full bg-teal" />
            {liveCount} live
          </span>
          <span className="flex items-center gap-1.5 font-sans text-xs text-ink-secondary">
            <span className="inline-block w-2 h-2 rounded-full bg-signal-pos" />
            {leaderCount} Leader/Strong
          </span>
          <span className="flex items-center gap-1.5 font-sans text-xs text-ink-secondary">
            <span className="inline-block w-2 h-2 rounded-full bg-signal-pos" />
            {accelCount} Accel/Improving
          </span>
        </div>
        {dataAsOf && (
          <span className="font-sans text-[11px] text-ink-tertiary">as of {dataAsOf}</span>
        )}
      </div>

      {/* Sector breadth bar */}
      <div className="px-6 pt-4">
        <USSectorBreadthBar sectorBreadth={sectorBreadth} />
      </div>

      {/* Main screener */}
      <div className="px-6 py-4">
        <USStockScreener stocks={stocks} />
      </div>
    </div>
  )
}
