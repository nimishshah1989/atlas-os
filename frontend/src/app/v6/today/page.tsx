// frontend/src/app/v6/today/page.tsx
// v6 Today — RegimeIndicator + Top Conviction stacks + Cells Lit Today + Sector Ladder top-5.

import Link from 'next/link'
import {
  getMarketRegime,
  getScreenStocks,
  getScreenSectors,
  getCellDefinitions,
} from '@/lib/api/v1'
import { RegimeIndicator } from '@/components/v6/RegimeIndicator'
import { ConvictionTape } from '@/components/v6/ConvictionTape'
import { CellMatrix } from '@/components/v6/CellMatrix'
import { SectorLadder } from '@/components/v6/SectorLadder'
import { DataSourceBanner } from '@/components/v6/DataSourceBanner'
import { LinkedTicker } from '@/components/ui/LinkedToken'
import { LinkedCellById } from '@/components/v6/LinkedCell'
import type { ScreenStock, Tier } from '@/lib/api/v1'

export const dynamic = 'force-dynamic'

function tapePosCount(s: ScreenStock): number {
  let n = 0
  for (const t of ['1m', '3m', '6m', '12m'] as const) {
    if (s.conviction_tape[t].direction === 'POSITIVE') n += 1
  }
  return n
}

function topConvictionByTier(stocks: ScreenStock[], tier: Tier, n: number): ScreenStock[] {
  return stocks
    .filter(s => s.tier === tier)
    .sort((a, b) => tapePosCount(b) - tapePosCount(a))
    .slice(0, n)
}

export default async function V6TodayPage() {
  const [regimeRes, stocksRes, sectorsRes, cellsRes] = await Promise.all([
    getMarketRegime(),
    getScreenStocks({ limit: 200 }),
    getScreenSectors(),
    getCellDefinitions(),
  ])

  const regime = regimeRes.data
  const stocks = stocksRes.data
  const sectors = sectorsRes.data
  const cells = cellsRes.data

  const top = {
    Large: topConvictionByTier(stocks, 'Large', 5),
    Mid: topConvictionByTier(stocks, 'Mid', 5),
    Small: topConvictionByTier(stocks, 'Small', 5),
  }

  const litCells = cells
    .filter(c => c.grade === 'green' && c.n_gate_pass > 0)
    .sort((a, b) => Math.abs(b.best_rule_ic ?? 0) - Math.abs(a.best_rule_ic ?? 0))
    .slice(0, 8)

  const topSectors = sectors.slice(0, 5)

  return (
    <div className="max-w-[1400px] mx-auto">
      <div className="px-6 py-4 border-b border-paper-rule">
        <div className="font-sans text-[10px] uppercase tracking-wider text-ink-tertiary mb-1">
          Today · {regime.regime_state}
        </div>
        <h1 className="font-serif text-3xl font-semibold text-ink-primary leading-none">
          {regime.regime_state} — deploy {regime.deployment_pct}%
        </h1>
        <p className="font-sans text-sm text-ink-secondary leading-relaxed mt-2 max-w-[760px]">
          Add Stage 2a/2b breakouts; prefer leading sectors. {litCells.length} cells
          firing today; {topSectors.filter(s => s.sector_state === 'Overweight').length} sectors are Overweight.
        </p>
      </div>

      <DataSourceBanner source={regimeRes.source_kind} asOf={regimeRes.meta.data_as_of} />

      <div className="px-6 py-5 border-b border-paper-rule">
        <RegimeIndicator regime={regime} />
      </div>

      <div className="px-6 py-5 border-b border-paper-rule">
        <div className="flex items-baseline justify-between mb-3">
          <h2 className="font-sans text-xs font-medium text-ink-tertiary uppercase tracking-wider">
            Top Conviction Today
          </h2>
          <Link href="/v6/stocks" className="font-sans text-xs text-teal hover:underline">
            See full universe →
          </Link>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {(['Large', 'Mid', 'Small'] as Tier[]).map(tier => (
            <div key={tier} className="border border-paper-rule rounded-[2px] bg-paper p-4">
              <div className="font-sans text-[10px] uppercase tracking-wider text-ink-tertiary mb-3">
                {tier === 'Large' ? 'Large-cap' : tier === 'Mid' ? 'Mid-cap' : 'Small-cap'}
              </div>
              <ul className="space-y-2">
                {top[tier].length === 0 ? (
                  <li className="font-sans text-xs text-ink-tertiary">No data in tier today.</li>
                ) : top[tier].map(s => (
                  <li key={s.iid} className="flex items-center gap-2">
                    <div className="font-mono text-sm font-semibold tabular-nums w-24">
                      <LinkedTicker symbol={s.symbol} />
                    </div>
                    <ConvictionTape tape={s.conviction_tape} compact />
                    <span className="font-sans text-[10px] text-ink-tertiary ml-auto">{s.sector}</span>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      </div>

      <div className="px-6 py-5 border-b border-paper-rule">
        <div className="flex items-baseline justify-between mb-3">
          <h2 className="font-sans text-xs font-medium text-ink-tertiary uppercase tracking-wider">
            Cells Lit Today
          </h2>
          <Link href="/matrix" className="font-sans text-xs text-teal hover:underline">
            See full matrix →
          </Link>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
          {litCells.map(c => (
            <LinkedCellById key={c.cell_id} cellId={c.cell_id}>
              <div className="flex items-center justify-between border border-paper-rule rounded-[2px] bg-paper px-3 py-2 hover:bg-paper-rule/10 transition-colors">
                <div>
                  <span className="font-sans text-sm font-medium text-ink-primary">{c.cell_id}</span>
                  <span className="font-sans text-[10px] text-ink-tertiary uppercase tracking-wider ml-2">
                    {c.best_archetype}
                  </span>
                </div>
                <div className="flex items-center gap-3 font-mono text-xs tabular-nums">
                  <span className="text-signal-pos">IC {c.best_rule_ic?.toFixed(3)}</span>
                  <span className="text-ink-tertiary">{c.rules[0]?.population_today ?? 0} stocks</span>
                  <span className="text-teal">→</span>
                </div>
              </div>
            </LinkedCellById>
          ))}
        </div>
      </div>

      <div className="px-6 py-5 border-b border-paper-rule">
        <div className="flex items-baseline justify-between mb-3">
          <h2 className="font-sans text-xs font-medium text-ink-tertiary uppercase tracking-wider">
            Sector Ladder — top 5
          </h2>
          <Link href="/v6/sectors" className="font-sans text-xs text-teal hover:underline">
            See all {sectors.length} →
          </Link>
        </div>
        <SectorLadder sectors={topSectors} />
      </div>

      <div className="px-6 py-5">
        <h2 className="font-sans text-xs font-medium text-ink-tertiary uppercase tracking-wider mb-3">
          Matrix snapshot
        </h2>
        <CellMatrix cells={cells} highlight={litCells.map(c => c.cell_id)} showLegend={false} />
      </div>
    </div>
  )
}
