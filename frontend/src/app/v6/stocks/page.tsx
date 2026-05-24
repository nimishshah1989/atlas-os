// frontend/src/app/v6/stocks/page.tsx
// v6 stocks page — 4-tenure ConvictionTape per row + chip filters + drill-down.

import { getScreenStocks, getCellDefinitions } from '@/lib/api/v1'
import { StocksTableV6 } from '@/components/v6/StocksTableV6'
import { DataSourceBanner } from '@/components/v6/DataSourceBanner'
import type { CellRule } from '@/lib/api/v1'

export const dynamic = 'force-dynamic'

export default async function V6StocksPage() {
  const [stocksRes, cellsRes] = await Promise.all([
    getScreenStocks(),
    getCellDefinitions(),
  ])
  const stocks = stocksRes.data
  const cellRules = new Map<string, CellRule[]>(
    cellsRes.data.map(c => [c.cell_id, c.rules])
  )

  const investableCount = stocks.filter(s => s.is_investable).length
  const leaderCount = stocks.filter(s => s.rs_state === 'Leader' || s.rs_state === 'Strong').length

  return (
    <div className="max-w-[1400px] mx-auto">
      <div className="px-6 py-4 border-b border-paper-rule">
        <div className="font-sans text-[10px] uppercase tracking-wider text-ink-tertiary mb-1">
          Stocks · v6
        </div>
        <h1 className="font-serif text-2xl lg:text-3xl font-semibold text-ink-primary">
          Stock Universe
        </h1>
        <p className="font-sans text-sm text-ink-secondary leading-relaxed mt-2 max-w-[760px]">
          {stocks.length} instruments with the 4-tenure conviction tape. Click any
          tape segment → cell drill-down with the firing rule&apos;s predicates and metrics.
        </p>
      </div>

      <DataSourceBanner source={stocksRes.source_kind} asOf={stocksRes.meta.data_as_of} />

      <div className="px-6 py-3 border-b border-paper-rule flex items-center gap-6 flex-wrap">
        <span className="flex items-center gap-1.5 font-sans text-xs text-ink-secondary">
          <span className="inline-block w-2 h-2 rounded-full bg-teal" />
          {investableCount} Investable
        </span>
        <span className="flex items-center gap-1.5 font-sans text-xs text-ink-secondary">
          <span className="inline-block w-2 h-2 rounded-full bg-signal-pos" />
          {leaderCount} Leader/Strong
        </span>
      </div>

      <StocksTableV6 stocks={stocks} cellRules={cellRules} />
    </div>
  )
}
