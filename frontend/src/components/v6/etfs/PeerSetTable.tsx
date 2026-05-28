'use client'

// frontend/src/components/v6/etfs/PeerSetTable.tsx
//
// Peer set comparison table for ETF deep-dive (Page 07a).
// Shows the top peers within the same etf_category, sorted by composite_score desc.
// Data from mv_etf_deepdive.peer_set JSONB array.
//
// Columns: Ticker · Composite · Matrix conviction · ADV · Atlas leader · Rank · vs this

import Link from 'next/link'
import type { PeerSetEntry } from '@/lib/queries/v6/etfs'

function fmtScore(v: number | null): string {
  // composite_score / matrix_conviction_score come from atlas_etf_scorecard on
  // a 0-100 scale already; do NOT multiply by 100 again (the historical
  // *100 was a stale assumption from when scores were 0-1).
  if (v == null) return '—'
  return v.toFixed(1)
}

function fmtAdv(v: number | null): string {
  if (v == null) return '—'
  const cr = v / 1e7
  return `₹${cr.toFixed(1)} cr`
}

function deltaClass(v: number | null): string {
  if (v == null) return 'text-ink-tertiary'
  if (v > 0.05) return 'text-signal-pos'
  if (v < -0.05) return 'text-signal-neg'
  return 'text-ink-secondary'
}

function fmtDelta(v: number | null): string {
  // delta_composite is the difference between peer.composite_score and the
  // focus ETF's composite_score — both on 0-100 scale, so the delta is also
  // on that scale and does NOT need * 100.
  if (v == null) return '—'
  const sign = v > 0 ? '+' : ''
  return `${sign}${v.toFixed(1)}`
}

export interface PeerSetTableProps {
  ticker: string
  peers: PeerSetEntry[] | null
  category: string | null
}

export function PeerSetTable({ ticker, peers, category }: PeerSetTableProps) {
  if (!peers || peers.length === 0) {
    return (
      <div
        className="bg-paper border border-paper-rule rounded-sm p-4"
        data-testid="peer-set-table"
      >
        <div className="font-sans text-[10px] uppercase tracking-wider text-ink-tertiary mb-2">
          Peer set · {category ?? 'same category'}
        </div>
        <div className="font-sans text-[12px] text-ink-tertiary">
          No peer data for <strong className="text-ink-secondary">{ticker}</strong> in{' '}
          <strong className="text-ink-secondary">{category ?? 'this category'}</strong>.
          Either only one ETF exists in this category or peer JSONB is pending the next MV refresh.
        </div>
      </div>
    )
  }

  const sorted = [...peers].sort(
    (a, b) => (b.composite_score ?? 0) - (a.composite_score ?? 0),
  )

  return (
    <div
      className="bg-paper border border-paper-rule rounded-sm overflow-hidden"
      data-testid="peer-set-table"
    >
      <div className="px-4 py-2.5 border-b border-paper-rule bg-paper-soft flex items-center justify-between">
        <div className="font-sans text-[10px] uppercase tracking-wider text-ink-tertiary font-semibold">
          Peer set · {category ?? 'same category'}
        </div>
        <div className="font-sans text-[11px] text-ink-tertiary">
          Peers within same category · vs composite score of <strong className="text-ink-secondary">{ticker}</strong>
        </div>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full border-collapse text-[12px]" aria-label={`${ticker} peer set`}>
          <thead>
            <tr className="bg-paper-soft border-b border-ink-rule">
              {[
                { label: 'Ticker', align: 'left' },
                { label: 'Composite', align: 'center' },
                { label: 'Conviction', align: 'center' },
                { label: 'ADV', align: 'center' },
                { label: 'Leader', align: 'center' },
                { label: 'Rank', align: 'center' },
                { label: 'vs this', align: 'center' },
              ].map((h) => (
                <th
                  key={h.label}
                  className={`px-3 py-2 font-sans text-[9px] uppercase tracking-[0.13em] text-ink-tertiary font-semibold text-${h.align}`}
                >
                  {h.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {sorted.map((peer) => (
              <tr
                key={peer.ticker}
                className="border-b border-paper-rule hover:bg-paper-soft transition-colors"
              >
                <td className="px-3 py-2 text-left">
                  <Link
                    href={`/etfs/${encodeURIComponent(peer.ticker)}`}
                    className="font-mono font-semibold text-ink-primary text-[11.5px] hover:text-accent hover:underline transition-colors"
                  >
                    {peer.ticker}
                  </Link>
                  {peer.is_atlas_leader && (
                    <span className="ml-1.5 font-mono text-[8px] font-bold px-1 py-0.5 bg-signal-pos text-paper rounded-sm">
                      LEADER
                    </span>
                  )}
                </td>
                <td className="px-3 py-2 text-center font-mono text-[11.5px] text-ink-secondary tabular-nums">
                  {fmtScore(peer.composite_score)}
                </td>
                <td className="px-3 py-2 text-center font-mono text-[11.5px] text-ink-secondary tabular-nums">
                  {fmtScore(peer.matrix_conviction_score)}
                </td>
                <td className="px-3 py-2 text-center font-mono text-[11.5px] text-ink-secondary tabular-nums">
                  {fmtAdv(peer.adv_20d_inr)}
                </td>
                <td className="px-3 py-2 text-center font-sans text-[11px]">
                  {peer.is_atlas_leader ? (
                    <span className="text-signal-pos font-semibold">Yes</span>
                  ) : (
                    <span className="text-ink-tertiary">—</span>
                  )}
                </td>
                <td className="px-3 py-2 text-center font-mono text-[11.5px] text-ink-secondary tabular-nums">
                  {peer.rank_in_category != null ? `#${peer.rank_in_category}` : '—'}
                </td>
                <td
                  className={`px-3 py-2 text-center font-mono text-[11.5px] font-semibold tabular-nums ${deltaClass(peer.delta_composite)}`}
                >
                  {fmtDelta(peer.delta_composite)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

export default PeerSetTable
