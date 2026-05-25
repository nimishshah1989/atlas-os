// frontend/src/app/matrix/page.tsx
// The soul page — 3×8 grid of all cells. Click any cell → /v6/cells/<cell_id>.
// C.14: Switched from v1 API to direct Supabase (getMatrixCells + getHeldIidSet).
// Page shell ≤250 LOC.

import { Suspense } from 'react'
import Link from 'next/link'
import { CellMatrix } from '@/components/v6/CellMatrix'
import { getMatrixCells } from '@/lib/queries/v6/cells'
import { getHeldIidSet } from '@/lib/queries/v6/portfolio_holdings'
import { toNumber } from '@/lib/v6/decimal'

export const dynamic = 'force-dynamic'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function fmtPct(s: string | null): string {
  if (s == null) return '—'
  const n = toNumber(s)
  if (n === null) return '—'
  const pct = n * 100
  const sign = pct >= 0 ? '+' : ''
  return `${sign}${pct.toFixed(1)}%`
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default async function MatrixPage(): Promise<React.ReactElement> {
  const [cells, heldIidSet] = await Promise.all([
    getMatrixCells(),
    getHeldIidSet(),
  ])

  const firingCount = cells.filter((c) => c.n_firing_today > 0).length
  const totalCells = cells.length

  // Grade-bucket counts derived from n_gate_pass
  const shipReady = cells.filter((c) => c.n_gate_pass > 0 && c.drift_status !== 'deprecated').length
  const deprecated = cells.filter((c) => c.drift_status === 'deprecated').length
  const noSignal = cells.filter((c) => c.n_gate_pass === 0).length

  // Best cells by friction_adjusted_excess (positive direction, gate passed)
  const bestCells = cells
    .filter((c) => c.n_gate_pass > 0 && c.action === 'POSITIVE')
    .sort((a, b) => {
      const an = toNumber(a.friction_adjusted_excess) ?? 0
      const bn = toNumber(b.friction_adjusted_excess) ?? 0
      return bn - an
    })
    .slice(0, 5)

  return (
    <div className="max-w-[1400px] mx-auto">
      {/* ── Header ─────────────────────────────────────────────────────── */}
      <div className="px-6 py-4 border-b border-paper-rule">
        <div className="font-sans text-[10px] uppercase tracking-wider text-ink-tertiary mb-1"
          style={{ letterSpacing: '0.22em' }}>
          Decision Matrix
        </div>
        <h1 className="font-serif text-3xl font-semibold text-ink-primary leading-none">
          Today&apos;s matrix
        </h1>
        <p className="font-sans text-sm text-ink-secondary leading-relaxed mt-2 max-w-[760px]">
          <strong>{firingCount} of {totalCells}</strong> cells firing this snapshot.{' '}
          Twenty-four cells (3 market-cap tiers × 4 tenures × 2 directions) define
          Atlas&apos;s discovery space — every page in the platform is a projection of this matrix.
        </p>
      </div>

      {/* ── Grade-bucket summary bar ────────────────────────────────────── */}
      <div className="px-6 py-4 border-b border-paper-rule flex items-center gap-6 flex-wrap">
        <span className="flex items-center gap-1.5 font-sans text-xs text-ink-secondary">
          <span className="inline-block w-2 h-2 rounded-full bg-signal-pos" />
          {shipReady} ship-ready
        </span>
        <span className="flex items-center gap-1.5 font-sans text-xs text-ink-secondary">
          <span className="inline-block w-2 h-2 rounded-full bg-signal-warn" />
          {deprecated} deprecated
        </span>
        <span className="flex items-center gap-1.5 font-sans text-xs text-ink-secondary">
          <span className="inline-block w-2 h-2 rounded-full bg-signal-neg" />
          {noSignal} no signal
        </span>
        <span className="ml-auto font-sans text-xs text-ink-tertiary">
          Click any cell → cell drill-down
        </span>
      </div>

      {/* ── Main grid hero ──────────────────────────────────────────────── */}
      <div className="px-6 py-6 border-b border-paper-rule">
        <Suspense fallback={
          <div className="h-[380px] border border-paper-rule rounded-[2px] bg-paper animate-pulse" />
        }>
          <CellMatrix cells={cells} heldIidSet={heldIidSet} />
        </Suspense>
      </div>

      {/* ── Best POSITIVE cells ─────────────────────────────────────────── */}
      {bestCells.length > 0 && (
        <div className="px-6 py-5 border-b border-paper-rule">
          <h2 className="font-sans text-xs font-medium text-ink-tertiary uppercase tracking-wider mb-3">
            Top POSITIVE cells by friction-adjusted excess
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-5 gap-3">
            {bestCells.map((c) => (
              <Link
                key={c.cell_id}
                href={`/v6/cells/${encodeURIComponent(c.cell_id)}`}
                className="block border border-paper-rule rounded-[2px] bg-paper p-3 hover:bg-paper-deep/60 transition-colors"
              >
                <div className="font-sans text-[10px] uppercase tracking-wider text-ink-tertiary mb-1">
                  {c.cap_tier} · {c.tenure} · {c.action}
                </div>
                <div className="font-mono text-base font-semibold tabular-nums text-ink-primary">
                  {fmtPct(c.friction_adjusted_excess)}
                </div>
                <div className="font-mono text-[11px] tabular-nums text-ink-secondary mt-0.5">
                  conf {fmtPct(c.confidence_unconditional)}
                </div>
              </Link>
            ))}
          </div>
        </div>
      )}

      {/* ── Methodology footer ──────────────────────────────────────────── */}
      <div className="px-6 py-5">
        <h2 className="font-sans text-xs font-medium text-ink-tertiary uppercase tracking-wider mb-2">
          What this is
        </h2>
        <div className="max-w-[760px]">
          <p className="font-sans text-sm text-ink-secondary leading-relaxed mb-2">
            For each cell, the deep-search engine evaluates 191–321 candidate
            predicates, applies Benjamini-Hochberg multiple-testing correction
            (within-cell <em>and</em> cross-cell, 6,144 total tests), and keeps
            only the rules that pass:
          </p>
          <ul className="font-sans text-sm text-ink-secondary leading-relaxed list-disc list-inside space-y-1">
            <li>IC magnitude above the cell-specific floor (0.02–0.05)</li>
            <li>BH-FDR q-value ≤ 0.10 (cross-cell)</li>
            <li>Friction-adjusted excess return ≥ 0 (after slippage)</li>
            <li>Per-window consistency across 3 rolling OOS windows (2022–2025)</li>
          </ul>
          <p className="font-sans text-sm text-ink-secondary leading-relaxed mt-2">
            NEGATIVE-direction cells carry a survivorship-bias caveat — signal
            strength may be overstated on historical data.{' '}
            <Link href="/methodology" className="text-teal hover:underline">
              Methodology →
            </Link>
          </p>
        </div>
      </div>
    </div>
  )
}
