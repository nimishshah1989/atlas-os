// frontend/src/app/v6/cells/[cell_id]/page.tsx
//
// Cell detail page — thin RSC wrapper (≤250 LOC).
// All logic lives in CellDetailClient.tsx.
//
// Data sources:
//   - atlas_cell_definitions via getCellById (C.1)
//   - atlas_signal_calls via getSignalCallsByCell (C.6 recent_signal_calls)
//   - atlas_paper_portfolio via getHeldIidSet (B.1 portfolio_holdings)
//   - atlas_cell_walkforward_runs (direct query)
//   - atlas_ledger (direct query — empty at v6.0)

import { notFound } from 'next/navigation'
import sql from '@/lib/db'
import { getCellById } from '@/lib/queries/v6/cells'
import { getSignalCallsByCell } from '@/lib/queries/v6/recent_signal_calls'
import { getHoldingState, getHeldIidSet } from '@/lib/queries/v6/portfolio_holdings'
import { CellDetailClient } from '@/components/v6/CellDetailClient'
import type { WalkForwardWindow, LedgerOutcome } from '@/components/v6/CellDetailClient'
import type { HoldingState } from '@/lib/queries/v6/portfolio_holdings'
import type { CapTier, Tenure } from '@/lib/queries/v6/cells'

export const dynamic = 'force-dynamic'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function buildCellLabel(cap_tier: CapTier, tenure: Tenure, action: string): string {
  // e.g. "Mid 12m POSITIVE" → but we want something more readable
  // Use action display name
  const actionDisplay: Record<string, string> = {
    POSITIVE: 'POSITIVE',
    NEGATIVE: 'NEGATIVE',
    NEUTRAL: 'NEUTRAL',
  }
  return `${cap_tier} ${tenure} ${actionDisplay[action] ?? action}`
}

// ---------------------------------------------------------------------------
// Walk-forward windows query
// ---------------------------------------------------------------------------

type WalkForwardRow = {
  run_id: string
  window_train_start: string
  window_train_end: string
  window_test_start: string
  window_test_end: string
  tp_rate: string | null
  median_excess: string | null
  friction_adjusted_excess: string | null
  n_observations: number | string
  status: string
}

async function getWalkForwardWindows(cell_id: string): Promise<WalkForwardWindow[]> {
  const rows = await sql<WalkForwardRow[]>`
    SELECT
      run_id::text,
      window_train_start::text,
      window_train_end::text,
      window_test_start::text,
      window_test_end::text,
      tp_rate::text,
      median_excess::text,
      friction_adjusted_excess::text,
      n_observations::int,
      status::text
    FROM atlas.atlas_cell_walkforward_runs
    WHERE cell_id = ${cell_id}::uuid
      AND status = 'completed'
    ORDER BY window_test_start DESC
    LIMIT 10
  `
  return rows.map((r): WalkForwardWindow => ({
    run_id: r.run_id,
    window_train_start: r.window_train_start,
    window_train_end: r.window_train_end,
    window_test_start: r.window_test_start,
    window_test_end: r.window_test_end,
    tp_rate: r.tp_rate ?? null,
    median_excess: r.median_excess ?? null,
    friction_adjusted_excess: r.friction_adjusted_excess ?? null,
    n_observations: typeof r.n_observations === 'string'
      ? parseInt(r.n_observations, 10)
      : r.n_observations,
    status: r.status,
  }))
}

// ---------------------------------------------------------------------------
// Ledger query (empty at v6.0)
// ---------------------------------------------------------------------------

type LedgerRow = {
  signal_call_id: string
  realized_excess: string
  realized_at: string
  status: string
}

async function getLedgerOutcomes(cell_id: string): Promise<LedgerOutcome[]> {
  // atlas_ledger joins to atlas_signal_calls via signal_call_id FK.
  // Filter to calls for this cell. Empty at v6.0 launch.
  const rows = await sql<LedgerRow[]>`
    SELECT
      l.signal_call_id::text,
      l.realized_excess::text,
      l.realized_at::text,
      l.status::text
    FROM atlas.atlas_ledger l
    JOIN atlas.atlas_signal_calls sc ON sc.signal_call_id = l.signal_call_id
    WHERE sc.cell_id = ${cell_id}::uuid
    ORDER BY l.realized_at DESC
    LIMIT 50
  `
  return rows.map((r): LedgerOutcome => ({
    signal_call_id: r.signal_call_id,
    realized_excess: r.realized_excess,
    realized_at: r.realized_at,
    status: r.status,
  }))
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default async function CellDetailPage({
  params,
}: {
  params: Promise<{ cell_id: string }>
}) {
  const { cell_id } = await params

  // Parallel data fetch
  const [cell, signalHistory, heldIidSet, walkForwardWindows, ledgerOutcomes] =
    await Promise.all([
      getCellById(cell_id),
      getSignalCallsByCell(cell_id, 50),
      getHeldIidSet(),
      getWalkForwardWindows(cell_id),
      getLedgerOutcomes(cell_id),
    ])

  if (!cell) {
    notFound()
  }

  // Stocks firing today = active signal calls (exit_date is null)
  const firingToday = signalHistory.filter((sc) => sc.is_active)

  // Build per-instrument holding states for all firing instruments
  const firingInstrumentIds = [
    ...new Set([
      ...firingToday.map((sc) => sc.instrument_id),
      ...signalHistory.map((sc) => sc.instrument_id),
    ]),
  ]

  // Only fetch holdingState for instruments actually in the held set
  // (avoids N queries when portfolio is empty — the v6.0 common case)
  const holdingStates: Record<string, HoldingState> = {}
  const heldInFiring = firingInstrumentIds.filter((id) => heldIidSet.has(id))

  if (heldInFiring.length > 0) {
    const states = await Promise.all(
      heldInFiring.map((id) => getHoldingState(id).then((s) => ({ id, s })))
    )
    for (const { id, s } of states) {
      if (s !== null) holdingStates[id] = s
    }
  }

  const cellLabel = buildCellLabel(cell.cap_tier, cell.tenure, cell.action)

  return (
    <CellDetailClient
      cell={cell}
      cellLabel={cellLabel}
      firingToday={firingToday}
      signalHistory={signalHistory}
      holdingStates={holdingStates}
      walkForwardWindows={walkForwardWindows}
      ledgerOutcomes={ledgerOutcomes}
      maintainerNotes={null}
    />
  )
}
