export const dynamic = 'force-dynamic'

import { getAllStocks } from '@/lib/queries/stocks'
import { getCurrentRegime } from '@/lib/queries/regime'
import { StocksClientShell } from '@/components/stocks/StocksClientShell'

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

  const investableCount = stocks.filter(s => s.is_investable).length
  const leaderCount     = stocks.filter(s => s.rs_state === 'Leader' || s.rs_state === 'Strong').length
  const improvingCount  = stocks.filter(s => s.momentum_state === 'Improving' || s.momentum_state === 'Accelerating').length

  return (
    <div className="max-w-[1400px] mx-auto">
      <div className="px-6 py-4 border-b border-paper-rule flex items-center gap-6 flex-wrap">
        <h1 className="font-sans text-sm font-semibold text-ink-primary uppercase tracking-wide">
          Stock Universe
        </h1>
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

      <div className="px-6 py-6">
        <StocksClientShell
          stocks={stocks}
          regimeState={regime?.regime_state ?? 'Unknown'}
          deploymentMultiplier={Number(regime?.deployment_multiplier ?? '0')}
        />
      </div>
    </div>
  )
}
