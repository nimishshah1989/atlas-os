'use client'

// IndustrySnapshot — 4-6 stat callouts for the Funds and ETFs list pages.
// Renders: total count · Atlas Leaders · Atlas Avoid · median expense ·
//          median AUM · AMC leaderboard (top 5, included for BOTH funds and
//          ETFs per Vocabulary lock override of design-lock §6.5).
//
// All numeric values arrive as strings (Postgres NUMERIC transport).

import { toNumber, formatINR } from '@/lib/v6/decimal'
import type { IndustrySnapshot as IndustrySnapshotData } from '@/lib/queries/v6/industry_snapshot'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface IndustrySnapshotProps {
  snapshot: IndustrySnapshotData
  className?: string
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Map an avg_composite string (0-100 scale) to a quartile CSS class. */
function compositeClass(avgComposite: string): string {
  const v = toNumber(avgComposite)
  if (v == null) return 'text-ink-tertiary'
  if (v >= 70) return 'text-signal-pos font-semibold'
  if (v >= 55) return 'text-signal-warn font-semibold'
  return 'text-signal-neg font-semibold'
}

/** Format an expense ratio (stored as percentage, e.g. "0.92" → "0.92%"). */
function formatExpense(s: string | null): string {
  if (s == null) return '—'
  const v = toNumber(s)
  if (v == null) return '—'
  return `${v.toFixed(2)}%`
}

/** Format AUM in crores (e.g. "2450.00" → "₹2,450 Cr"). */
function formatAumCr(s: string | null): string {
  if (s == null) return '—'
  const v = toNumber(s)
  if (v == null) return '—'
  // Use formatINR on the raw crore number with compact flag would divide by crore again.
  // Instead, format directly: show as ₹X Cr with 2 dp
  return `₹${v.toFixed(0)} Cr`
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

interface StatTileProps {
  label: string
  value: string | number
  accent?: 'pos' | 'neg' | 'neutral'
  ariaLabel: string
}

function StatTile({ label, value, accent = 'neutral', ariaLabel }: StatTileProps) {
  const accentClass =
    accent === 'pos' ? 'text-signal-pos' :
    accent === 'neg' ? 'text-signal-neg' :
    'text-ink-primary'

  return (
    <div
      className="flex flex-col gap-1 rounded-[4px] border border-paper-deep bg-paper px-4 py-3 min-w-[100px]"
      aria-label={ariaLabel}
    >
      <span className={`text-xl font-bold tabular-nums ${accentClass}`}>
        {value}
      </span>
      <span className="text-[11px] text-ink-tertiary uppercase tracking-wide">
        {label}
      </span>
    </div>
  )
}

interface AmcRowProps {
  rank: number
  amc: string
  avgComposite: string
  nFunds: number
  assetClass: 'funds' | 'etfs'
}

function AmcRow({ rank, amc, avgComposite, nFunds, assetClass }: AmcRowProps) {
  const v = toNumber(avgComposite)
  const displayScore = v != null ? v.toFixed(1) : '—'
  const scoreClass = compositeClass(avgComposite)
  const label = assetClass === 'etfs' ? 'ETFs' : 'funds'

  return (
    <div className="flex items-center gap-3 py-1.5">
      <span className="w-5 text-[11px] text-ink-tertiary tabular-nums text-right">
        {rank}.
      </span>
      <span className="flex-1 text-sm text-ink-primary truncate" title={amc}>
        {amc}
      </span>
      <span className={`text-sm tabular-nums ${scoreClass}`}>
        {displayScore}
      </span>
      <span className="text-[11px] text-ink-tertiary tabular-nums w-16 text-right">
        {nFunds} {label}
      </span>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export function IndustrySnapshot({ snapshot, className = '' }: IndustrySnapshotProps) {
  const {
    asset_class,
    n_total,
    n_atlas_leaders,
    n_avoid,
    median_expense,
    median_aum_cr,
    amc_leaderboard,
  } = snapshot

  const title = asset_class === 'etfs' ? 'ETFs Industry' : 'Funds Industry'
  const leaderboardTitle =
    asset_class === 'etfs' ? 'Top AMCs — ETFs (by composite)' : 'Top AMCs — Funds (by composite)'

  return (
    <section
      className={`rounded-[6px] border border-paper-deep bg-paper p-5 space-y-5 ${className}`}
      aria-label={`${title} snapshot`}
    >
      {/* Header */}
      <h2 className="text-sm font-semibold text-ink-primary uppercase tracking-wide">
        {title}
      </h2>

      {/* Stat tiles — row 1: leadership counts */}
      <div className="flex flex-wrap gap-3">
        <StatTile
          label="Atlas Leaders"
          value={n_atlas_leaders}
          accent="pos"
          ariaLabel="Atlas Leaders stat tile"
        />
        <StatTile
          label="Atlas Avoid"
          value={n_avoid}
          accent="neg"
          ariaLabel="Atlas Avoid stat tile"
        />
        <StatTile
          label="Total in scope"
          value={n_total}
          accent="neutral"
          ariaLabel="Total in scope stat tile"
        />
      </div>

      {/* Stat tiles — row 2: medians */}
      <div className="flex flex-wrap gap-3">
        <StatTile
          label="Avg Expense Ratio"
          value={formatExpense(median_expense)}
          accent="neutral"
          ariaLabel="Average expense ratio stat tile"
        />
        <StatTile
          label="Avg AUM"
          value={formatAumCr(median_aum_cr)}
          accent="neutral"
          ariaLabel="Average AUM stat tile"
        />
      </div>

      {/* AMC Leaderboard */}
      <div>
        <p className="text-[11px] text-ink-tertiary uppercase tracking-wide mb-2">
          {leaderboardTitle}
        </p>

        {amc_leaderboard.length === 0 ? (
          <p
            className="text-sm text-ink-tertiary italic py-2"
            aria-label="AMC leaderboard insufficient data"
          >
            Insufficient data
          </p>
        ) : (
          <div
            className="divide-y divide-paper-deep"
            aria-label="AMC leaderboard"
          >
            {/* Column header */}
            <div className="flex items-center gap-3 pb-1.5">
              <span className="w-5" />
              <span className="flex-1 text-[11px] text-ink-tertiary uppercase tracking-wide">
                AMC
              </span>
              <span className="text-[11px] text-ink-tertiary uppercase tracking-wide">
                Avg Score
              </span>
              <span className="text-[11px] text-ink-tertiary uppercase tracking-wide w-16 text-right">
                Count
              </span>
            </div>

            {amc_leaderboard.map((row, idx) => (
              <AmcRow
                key={row.amc}
                rank={idx + 1}
                amc={row.amc}
                avgComposite={row.avg_composite}
                nFunds={row.n_funds}
                assetClass={asset_class}
              />
            ))}
          </div>
        )}
      </div>
    </section>
  )
}

export default IndustrySnapshot
