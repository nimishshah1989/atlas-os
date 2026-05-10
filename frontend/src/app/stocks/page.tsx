export const dynamic = 'force-dynamic'

import { getAllStocks } from '@/lib/queries/stocks'
import { getCurrentRegime } from '@/lib/queries/regime'
import { StockScreener } from '@/components/stocks/StockScreener'
import { StockBreadthPanel } from '@/components/stocks/StockBreadthPanel'
import { StockIntelligencePanel } from '@/components/stocks/StockIntelligencePanel'
import { StockBubbleChart } from '@/components/sectors/StockBubbleChart'

export default async function StocksPage() {
  const [stocks, regime] = await Promise.all([
    getAllStocks(),
    getCurrentRegime(),
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
        {/* TODO(Task-7): activeMaFilter/onMaFilter wired in StocksClientShell */}
        <StockBreadthPanel stocks={stocks} activeMaFilter={null} onMaFilter={() => {}} />

        {/* Bubble chart: 3M return vs RS percentile, sized by position */}
        <div className="border border-paper-rule rounded-sm p-4">
          <div className="font-sans text-[10px] font-semibold text-ink-tertiary uppercase tracking-wider mb-1">
            Positioning Map — 3M Return vs RS Percentile
          </div>
          <p className="font-sans text-[11px] text-ink-tertiary mb-3">
            Each bubble is a stock. X = 3-month return, Y = RS percentile vs peers. Color = RS + momentum state. Click any bubble to deep-dive.
          </p>
          <StockBubbleChart stocks={stocks} />
        </div>

        <div className="grid grid-cols-1 xl:grid-cols-[1fr_360px] gap-6">
          <StockScreener stocks={stocks} />

          <div>
            <div className="border border-paper-rule rounded-sm p-4 bg-paper sticky top-4">
              <div className="font-sans text-[10px] font-semibold text-ink-tertiary uppercase tracking-wider mb-3">
                Stock Intelligence
              </div>
              <StockIntelligencePanel
                stocks={stocks}
                regimeState={regime?.regime_state ?? 'Unknown'}
                deploymentMultiplier={parseFloat(regime?.deployment_multiplier ?? '0')}
              />
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
