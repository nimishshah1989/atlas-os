'use client'
// src/app/portfolios/PortfoliosView.tsx
// Client island for /portfolios — filterable table of FM portfolios.

import Link from 'next/link'
import type { PortfolioListRow } from '@/lib/queries/portfolios'

function fmtSharpe(raw: string | null): string {
  if (raw == null) return '—'
  const n = parseFloat(raw)
  return isNaN(n) ? '—' : n.toFixed(2)
}

function fmtDate(d: Date): string {
  const date = d instanceof Date ? d : new Date(String(d))
  return date.toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' })
}

type Props = {
  portfolios: PortfolioListRow[]
}

export function PortfoliosView({ portfolios }: Props) {
  if (portfolios.length === 0) {
    return (
      <div className="text-center py-16">
        <p className="font-sans text-sm text-ink-tertiary mb-4">No portfolios yet.</p>
        <Link
          href="/portfolios/new?type=static"
          className="font-sans text-sm px-4 py-2 bg-accent text-white rounded-[2px] hover:bg-accent/90 transition-colors"
        >
          + New Portfolio
        </Link>
      </div>
    )
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left border-collapse">
        <thead>
          <tr className="border-b border-paper-rule">
            {['Name', 'Type', 'Composition', 'Latest Sharpe', 'Paper Active', 'Created'].map((col) => (
              <th
                key={col}
                className="font-sans text-xs text-ink-tertiary uppercase tracking-wide pb-2 pr-4 font-medium"
              >
                {col}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {portfolios.map((p) => (
            <tr
              key={p.id}
              className="border-b border-paper-rule/50 hover:bg-accent/5 transition-colors"
            >
              <td className="py-2.5 pr-4">
                <Link
                  href={`/portfolios/${p.id}`}
                  className="font-sans text-sm text-ink-primary hover:text-accent transition-colors"
                >
                  {p.name}
                </Link>
              </td>
              <td className="py-2.5 pr-4">
                <TypeBadge type={p.type} />
              </td>
              <td className="py-2.5 pr-4 font-sans text-xs text-ink-tertiary">
                {p.type === 'static'
                  ? p.instrument_count != null
                    ? `${p.instrument_count} instrument${p.instrument_count !== 1 ? 's' : ''}`
                    : '—'
                  : 'Rule-Based'}
              </td>
              <td className="py-2.5 pr-4 font-mono text-sm text-right">
                {fmtSharpe(p.latest_sharpe)}
              </td>
              <td className="py-2.5 pr-4">
                {p.paper_trading_active ? (
                  <span className="inline-flex items-center gap-1.5 font-sans text-xs text-signal-pos">
                    <span className="inline-block w-2 h-2 rounded-full bg-signal-pos" />
                    Active
                  </span>
                ) : (
                  <span className="font-sans text-xs text-ink-tertiary">—</span>
                )}
              </td>
              <td className="py-2.5 font-sans text-xs text-ink-tertiary">
                {fmtDate(p.created_at)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function TypeBadge({ type }: { type: 'static' | 'rule-based' }) {
  const styles =
    type === 'static'
      ? 'text-accent bg-accent/10 border-accent/20'
      : 'text-signal-warn bg-signal-warn/10 border-signal-warn/20'
  return (
    <span
      className={`font-sans text-xs px-2 py-0.5 rounded-[2px] border capitalize ${styles}`}
    >
      {type === 'static' ? 'Static' : 'Rule-Based'}
    </span>
  )
}
