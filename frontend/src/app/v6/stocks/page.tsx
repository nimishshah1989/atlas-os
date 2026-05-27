// frontend/src/app/v6/stocks/page.tsx
// v6 stocks list — column chooser + portfolio badge + virtualized table.
// Thin server-component shell (≤250 LOC). All logic lives in StocksListV6.

import { getStocksForDate } from '@/lib/queries/v6/stocks'
import { getLatestSnapshotDate } from '@/lib/queries/v6/snapshot'
import { getHeldIidSet } from '@/lib/queries/v6/portfolio_holdings'
import { DataSourceBanner } from '@/components/v6/DataSourceBanner'
import { StocksListV6 } from '@/components/v6/StocksListV6'

export const dynamic = 'force-dynamic'

export default async function V6StocksPage() {
  const snapshotDate = await getLatestSnapshotDate()

  // Parallel fetch: stocks + held iid set (empty at v6.0 launch — graceful)
  const [stocks, heldIidSet] = await Promise.all([
    getStocksForDate(snapshotDate),
    getHeldIidSet(),
  ])

  // Convert Set → Array for serialization across RSC boundary
  const heldIids = Array.from(heldIidSet)

  const investableCount = stocks.filter(s => s.is_investable).length
  const leaderCount = stocks.filter(
    s => s.rs_state === 'Leader' || s.rs_state === 'Strong',
  ).length

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
          {stocks.length} instruments · {investableCount} investable ·{' '}
          {leaderCount} Leader/Strong · as of {snapshotDate}
        </p>
      </div>

      <DataSourceBanner source="live" asOf={snapshotDate} />

      <StocksListV6
        stocks={stocks}
        heldIids={heldIids}
        snapshotDate={snapshotDate}
      />
    </div>
  )
}
