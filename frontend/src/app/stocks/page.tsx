export const dynamic = 'force-dynamic'

import { getAllStocks, getTopPicksAcrossSectors } from '@/lib/queries/stocks'
import { StockScreener } from '@/components/stocks/StockScreener'
import { StockBreadthPanel } from '@/components/stocks/StockBreadthPanel'
import { StockTopPicks } from '@/components/stocks/StockTopPicks'

export default async function StocksPage() {
  const [stocks, topPicks] = await Promise.all([
    getAllStocks(),
    getTopPicksAcrossSectors(),
  ])

  if (stocks.length === 0) {
    return (
      <div className="p-8">
        <p className="font-sans text-sm text-ink-secondary">
          No stock data available. Run the nightly pipeline first.
        </p>
      </div>
    )
  }

  const above30wMaCount  = stocks.filter(s => s.above_30w_ma).length
  const investableCount  = stocks.filter(s => s.is_investable).length
  const leaderCount      = stocks.filter(s => s.rs_state === 'Leader' || s.rs_state === 'Strong').length
  const improvingCount   = stocks.filter(s => s.momentum_state === 'Improving' || s.momentum_state === 'Accelerating').length

  return (
    <div className="max-w-[1400px] mx-auto">
      {/* Header band */}
      <div className="px-6 py-4 border-b border-paper-rule flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-6">
          <h1 className="font-sans text-sm font-semibold text-ink-primary uppercase tracking-wide">
            Stock Universe
          </h1>
          <div className="flex items-center gap-4">
            <span className="flex items-center gap-1.5 font-sans text-xs text-ink-secondary">
              <span className="inline-block w-2 h-2 rounded-full bg-teal" />
              {investableCount} Investable
            </span>
            <span className="flex items-center gap-1.5 font-sans text-xs text-ink-secondary">
              <span className="inline-block w-2 h-2 rounded-full bg-signal-pos" />
              {leaderCount} Leader/Strong
            </span>
            <span className="flex items-center gap-1.5 font-sans text-xs text-ink-secondary">
              <span className="inline-block w-2 h-2 rounded-full bg-signal-pos" />
              {improvingCount} Accel/Improving
            </span>
          </div>
        </div>
      </div>

      {/* Main content */}
      <div className="px-6 py-6 flex flex-col gap-6">
        <StockScreener stocks={stocks} />
        <StockBreadthPanel stocks={stocks} above30wMaCount={above30wMaCount} />
        <StockTopPicks picks={topPicks} />
      </div>
    </div>
  )
}
