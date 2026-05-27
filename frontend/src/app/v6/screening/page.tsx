// frontend/src/app/v6/screening/page.tsx
// v6 multi-criteria stock screener — thin RSC shell (≤250 LOC).
// All rendering + interactivity lives in ScreenerClient.
//
// Architecture:
//   URL searchParams → paramsToFilter → screenStocks (SQL) → ScreenerClient
//
// The page re-fetches on every navigation (force-dynamic) so filter changes
// driven by client-side router.replace() automatically trigger a fresh SQL run.
//
// v6.0: stocks only. Funds + ETFs deferred to v6.1.

import type { Metadata } from 'next'
import { Suspense } from 'react'
import { screenStocks } from '@/lib/queries/v6/screen'
import { getHeldIidSet } from '@/lib/queries/v6/portfolio_holdings'
import { getLatestSnapshotDate } from '@/lib/queries/v6/snapshot'
import { DataSourceBanner } from '@/components/v6/DataSourceBanner'
import { ScreenerClient } from '@/components/v6/ScreenerClient'
import { decodeScreenerParams } from '@/lib/queries/v6/screen-filter'

export const dynamic = 'force-dynamic'

export const metadata: Metadata = {
  title: 'Screener · Atlas v6',
  description: 'Multi-criteria stock screener — filter by IC, sector, drift status, RS percentile, action, and cap tier.',
}

// Next.js 15 App Router page props: searchParams is a Promise<Record<string, ...>>
interface ScreeningPageProps {
  searchParams: Promise<Record<string, string | string[] | undefined>>
}

export default async function ScreeningPage({ searchParams }: ScreeningPageProps) {
  const rawParams = await searchParams
  const filter = decodeScreenerParams(rawParams)

  const [snapshotDate, heldIidSet] = await Promise.all([
    getLatestSnapshotDate(),
    getHeldIidSet(),
  ])

  const stocks = await screenStocks(filter, snapshotDate)
  const heldIids = Array.from(heldIidSet)

  const totalActive = Object.keys(filter).filter(k => {
    const v = filter[k as keyof typeof filter]
    if (Array.isArray(v)) return v.length > 0
    return v != null
  }).length

  return (
    <div className="flex flex-col h-[calc(100vh-56px)]">
      {/* ── Page header ────────────────────────────────────────────────── */}
      <div className="px-6 py-4 border-b border-paper-rule shrink-0">
        <div className="font-sans text-[10px] uppercase tracking-wider text-ink-tertiary mb-1">
          Screener · v6
        </div>
        <div className="flex items-start justify-between gap-4">
          <div>
            <h1 className="font-serif text-2xl lg:text-3xl font-semibold text-ink-primary">
              Stock Screener
            </h1>
            <p className="font-sans text-sm text-ink-secondary leading-relaxed mt-1 max-w-[600px]">
              Multi-criteria filter across {stocks.length} stocks.
              {totalActive > 0
                ? ` ${totalActive} filter${totalActive > 1 ? 's' : ''} active.`
                : ' No filters active — showing full universe.'}
            </p>
          </div>
          <div className="shrink-0 text-right">
            <span className="font-mono text-xs text-ink-tertiary block">as of {snapshotDate}</span>
            <span className="font-sans text-[10px] text-ink-tertiary">v6.0 · stocks only</span>
          </div>
        </div>
      </div>

      <DataSourceBanner source="live" asOf={snapshotDate} />

      {/* ── Screener body: filter panel + results table ─────────────────── */}
      <div className="flex-1 min-h-0 overflow-hidden">
        <Suspense
          fallback={
            <div className="px-6 py-12 text-center">
              <p className="font-sans text-sm text-ink-secondary">Loading screener…</p>
            </div>
          }
        >
          <ScreenerClient
            stocks={stocks}
            initialFilter={filter}
            heldIids={heldIids}
            snapshotDate={snapshotDate}
          />
        </Suspense>
      </div>
    </div>
  )
}
