// frontend/src/app/calls/page.tsx
//
// RSC shell for /calls (Page 08 — Calls Performance).
// Thin shell per 250-LOC limit — all rendering in CallsClient.tsx.
//
// Route: /calls (root, per spec D8 — no /v6/ prefix on new routes)
// Source of truth: atlas.mv_calls_performance (587 rows, real win-rate data)
//
// Data reality as of 2026-05-27:
//   - 576/587 rows have realized_excess_pct
//   - 587/587 rows have is_hit
//   - Hit rates per cell range 25%–92%

import type { Metadata } from 'next'
import {
  getCallsHero,
  getCallsLedger,
  getMatrix24Cells,
  getTopSixCells,
  getCallsSummaryByCell,
  getCumulativeExcessSeries,
} from '@/lib/queries/v6/calls'
import { CallsClient } from '@/components/v6/calls/CallsClient'

export const dynamic = 'force-dynamic'
export const revalidate = 0

export const metadata: Metadata = {
  title: 'Calls Performance · Atlas',
  description:
    'Signal call accountability ledger — realized win rate by tier × tenure × direction, cell trajectories, excess performance.',
  robots: 'noindex, nofollow',
}

export default async function CallsPage() {
  const [hero, ledger, matrix, topSix, allCells, excessSeries] = await Promise.all([
    getCallsHero(),
    getCallsLedger(),
    getMatrix24Cells(),
    getTopSixCells(),
    getCallsSummaryByCell(),
    getCumulativeExcessSeries(),
  ])

  return (
    <CallsClient
      hero={hero}
      ledger={ledger}
      matrix={matrix}
      topSix={topSix}
      allCells={allCells}
      excessSeries={excessSeries}
    />
  )
}
