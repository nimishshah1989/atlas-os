// frontend/src/app/v6/today/page.tsx
// v6 Today — thin RSC shell.
// All rendering is delegated to TodayClient.
// C.17 + D.1 + D.2 + D.12 bundled (co-ownership matrix).

import { getMatrixCells } from '@/lib/queries/v6/cells'
import { getCurrentRegime } from '@/lib/queries/v6/regime'
import { getStocksForDate } from '@/lib/queries/v6/stocks'
import { getSectorsForDate } from '@/lib/queries/v6/sectors'
import { getLatestSnapshotDate } from '@/lib/queries/v6/snapshot'
import { getMatrixDiff } from '@/lib/queries/v6/matrix_diff'
import { getBookDiff } from '@/lib/queries/v6/book_diff'
import { getHeldIidSet } from '@/lib/queries/v6/portfolio_holdings'
import { getRecentSignalCalls } from '@/lib/queries/v6/recent_signal_calls'
import { getDriftWarnCount } from '@/lib/queries/v6/drift_status_rollup'
import { TodayClient } from '@/components/v6/TodayClient'
import type { ScreenStock, Tier } from '@/lib/api/v1'

export const dynamic = 'force-dynamic'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

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

// ---------------------------------------------------------------------------
// Page shell — fetches all data, delegates rendering to TodayClient
// ---------------------------------------------------------------------------

export default async function V6TodayPage() {
  const snapshotDate = await getLatestSnapshotDate()

  const [regime, stocks, sectors, cellsRes, matrixDiff, bookDiff, signalCalls, driftWarnCount, heldIidSet] =
    await Promise.all([
      getCurrentRegime(),
      getStocksForDate(snapshotDate, { limit: 200 }),
      getSectorsForDate(snapshotDate),
      getMatrixCells(),
      getMatrixDiff(),
      getBookDiff(),
      getRecentSignalCalls(20, 7),
      getDriftWarnCount(),
      getHeldIidSet(),
    ])

  const allCells = cellsRes

  // Top conviction (5 per tier)
  const topConviction = {
    Large: topConvictionByTier(stocks, 'Large', 5),
    Mid:   topConvictionByTier(stocks, 'Mid', 5),
    Small: topConvictionByTier(stocks, 'Small', 5),
  }

  // Lit cells: firing today + gate pass, ordered by confidence_unconditional desc
  const litCells = allCells
    .filter(c => c.n_firing_today > 0 && c.n_gate_pass > 0)
    .sort((a, b) => parseFloat(b.confidence_unconditional) - parseFloat(a.confidence_unconditional))
    .slice(0, 8)

  // D.1: active cells today = count of unique cell_ids firing (from matrixDiff totals
  // we approximate from the signal_calls overnight feed; fallback to litCells count)
  const activeCellsToday = litCells.length
  const signalCallsOvernight = signalCalls.length

  // D.2: held verdicts — derive from stocks intersected with held set
  const heldByVerdict = { positive: 0, neutral: 0, negative: 0 }
  if (heldIidSet.size > 0) {
    for (const s of stocks) {
      if (!heldIidSet.has(s.iid)) continue
      // Use 6m tape direction as the primary verdict proxy
      const dir = s.conviction_tape['6m']?.direction
      if (dir === 'POSITIVE') heldByVerdict.positive += 1
      else if (dir === 'NEGATIVE') heldByVerdict.negative += 1
      else heldByVerdict.neutral += 1
    }
  }

  return (
    <TodayClient
      regime={regime}
      topConviction={topConviction}
      litCells={litCells}
      allCells={allCells}
      sectors={sectors}
      matrixDiff={matrixDiff}
      bookDiff={bookDiff}
      signalCalls={signalCalls}
      activeCellsToday={activeCellsToday}
      signalCallsOvernight={signalCallsOvernight}
      driftWarnCount={driftWarnCount}
      heldByVerdict={heldByVerdict}
      snapshotDate={snapshotDate}
    />
  )
}
