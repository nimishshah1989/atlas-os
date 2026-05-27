'use client'

// frontend/src/components/v6/TodayClient.tsx
//
// C.17 — Top-level today page composition (client boundary).
// Receives all server-fetched data from page.tsx and renders:
//   - DiffSinceYesterdayPanel (D.1 + D.12)
//   - 3-column hero: regime card | BookAtAGlance | top conviction
//   - RecentSignalCalls table
//   - Sector ladder + cell matrix (existing)
//
// All data flows down as props — no useEffect or client-side fetches.

import Link from 'next/link'
import type { MarketRegime, ScreenStock, ScreenSector, Tier } from '@/lib/api/v1'
import type { MatrixCell } from '@/lib/queries/v6/cells'
import type { MatrixDiff } from '@/lib/queries/v6/matrix_diff'
import type { BookDiff } from '@/lib/queries/v6/book_diff'
import type { SignalCallEvent } from '@/lib/queries/v6/recent_signal_calls'
import { DiffSinceYesterdayPanel } from './DiffSinceYesterdayPanel'
import { BookAtAGlance } from './BookAtAGlance'
import { RecentSignalCalls } from './RecentSignalCalls'
import { RegimeIndicator } from './RegimeIndicator'
import { ConvictionTape } from './ConvictionTape'
import { SectorLadder } from './SectorLadder'
import { CellMatrix } from './CellMatrix'
import { DataSourceBanner } from './DataSourceBanner'
import { LinkedTicker } from '@/components/ui/LinkedToken'
import { LinkedCellById } from './LinkedCell'

// ---------------------------------------------------------------------------
// Prop types
// ---------------------------------------------------------------------------

export interface TodayClientProps {
  regime: MarketRegime
  topConviction: Record<Tier, ScreenStock[]>
  litCells: MatrixCell[]
  allCells: MatrixCell[]
  sectors: ScreenSector[]
  matrixDiff: MatrixDiff
  bookDiff: BookDiff
  signalCalls: SignalCallEvent[]
  activeCellsToday: number
  signalCallsOvernight: number
  driftWarnCount: number
  heldByVerdict: { positive: number; neutral: number; negative: number }
  snapshotDate: string
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function HeroLabel({ tier }: { tier: Tier }) {
  const map: Record<Tier, string> = { Large: 'Large-cap', Mid: 'Mid-cap', Small: 'Small-cap' }
  return (
    <div className="font-sans text-[10px] uppercase tracking-wider text-ink-tertiary mb-3">
      {map[tier]}
    </div>
  )
}

// ---------------------------------------------------------------------------
// TodayClient
// ---------------------------------------------------------------------------

export function TodayClient({
  regime,
  topConviction,
  litCells,
  allCells,
  sectors,
  matrixDiff,
  bookDiff,
  signalCalls,
  activeCellsToday,
  signalCallsOvernight,
  driftWarnCount,
  heldByVerdict,
  snapshotDate,
}: TodayClientProps) {
  const topSectors = sectors.slice(0, 5)

  return (
    <div className="max-w-[1400px] mx-auto">
      {/* Page header */}
      <div className="px-6 py-4 border-b border-paper-rule">
        <div className="font-sans text-[10px] uppercase tracking-wider text-ink-tertiary mb-1">
          Today · {regime.regime_state}
        </div>
        <h1 className="font-serif text-3xl font-semibold text-ink-primary leading-none">
          {regime.regime_state} — deploy {regime.deployment_pct}%
        </h1>
        <p className="font-sans text-sm text-ink-secondary leading-relaxed mt-2 max-w-[760px]">
          {activeCellsToday} cells firing today.{' '}
          {sectors.filter(s => s.sector_state === 'Overweight').length} sectors are Overweight.
        </p>
      </div>

      <DataSourceBanner source="live" asOf={snapshotDate} />

      {/* D.1 + D.12: Diff since yesterday panel */}
      <DiffSinceYesterdayPanel
        matrixDiff={matrixDiff}
        bookDiff={bookDiff}
        activeCellsToday={activeCellsToday}
        signalCallsOvernight={signalCallsOvernight}
        driftWarnCount={driftWarnCount}
      />

      {/* 3-column hero */}
      <div className="px-6 py-5 border-b border-paper-rule">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {/* Col 1: Regime card */}
          <div>
            <RegimeIndicator regime={regime} />
          </div>

          {/* Col 2: BookAtAGlance (D.2) — silent when book empty */}
          <div>
            <BookAtAGlance bookDiff={bookDiff} heldByVerdict={heldByVerdict} />
          </div>

          {/* Col 3: Top conviction by tier */}
          <div className="border border-paper-rule rounded-[2px] bg-paper p-4">
            <div className="font-sans text-[10px] uppercase tracking-wider text-ink-tertiary mb-2">
              Top conviction today
            </div>
            {(['Large', 'Mid', 'Small'] as Tier[]).map(tier => (
              <div key={tier} className="mb-3">
                <HeroLabel tier={tier} />
                <ul className="space-y-1.5">
                  {topConviction[tier].length === 0 ? (
                    <li className="font-sans text-xs text-ink-tertiary">No data.</li>
                  ) : (
                    topConviction[tier].map(s => (
                      <li key={s.iid} className="flex items-center gap-2">
                        <div className="font-mono text-sm font-semibold tabular-nums w-24">
                          <LinkedTicker symbol={s.symbol} />
                        </div>
                        <ConvictionTape tape={s.conviction_tape} compact />
                        <span className="font-sans text-[10px] text-ink-tertiary ml-auto truncate">
                          {s.sector}
                        </span>
                      </li>
                    ))
                  )}
                </ul>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Cells lit today */}
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
          {litCells.length === 0 ? (
            <p className="font-sans text-xs text-ink-tertiary col-span-2">No cells firing today.</p>
          ) : (
            litCells.map(c => (
              <LinkedCellById key={c.cell_id} cellId={c.cell_id}>
                <div className="flex items-center justify-between border border-paper-rule rounded-[2px] bg-paper px-3 py-2 hover:bg-paper-rule/10 transition-colors">
                  <div>
                    <span className="font-sans text-sm font-medium text-ink-primary">{c.cell_id}</span>
                    <span className="font-sans text-[10px] text-ink-tertiary uppercase tracking-wider ml-2">
                      {c.cap_tier} · {c.tenure}
                    </span>
                  </div>
                  <div className="flex items-center gap-3 font-mono text-xs tabular-nums">
                    <span className="text-signal-pos">
                      {Math.round(parseFloat(c.confidence_unconditional) * 100)}%
                    </span>
                    <span className="text-ink-tertiary">{c.n_firing_today} firing</span>
                    <span className="text-teal">→</span>
                  </div>
                </div>
              </LinkedCellById>
            ))
          )}
        </div>
      </div>

      {/* Sector ladder snapshot */}
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

      {/* C.17: Recent signal_calls */}
      <div className="px-6 py-5 border-b border-paper-rule">
        <div className="flex items-baseline justify-between mb-3">
          <h2 className="font-sans text-xs font-medium text-ink-tertiary uppercase tracking-wider">
            Recent Signal Calls
          </h2>
          <span className="font-sans text-xs text-ink-tertiary">Last 20 · 7 days</span>
        </div>
        <RecentSignalCalls calls={signalCalls} />
      </div>

      {/* Matrix snapshot */}
      <div className="px-6 py-5">
        <h2 className="font-sans text-xs font-medium text-ink-tertiary uppercase tracking-wider mb-3">
          Matrix snapshot
        </h2>
        <CellMatrix cells={allCells} showLegend={false} />
      </div>
    </div>
  )
}

export default TodayClient
