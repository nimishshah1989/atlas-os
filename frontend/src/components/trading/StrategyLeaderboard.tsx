'use client'

import Link from 'next/link'
import type { LeaderboardRow } from '@/lib/queries/strategy_lab'

type Props = {
  leaderboard: LeaderboardRow[]
  selectedId: string
}

function fmt(v: string | null, decimals = 2): string {
  if (!v) return '—'
  const n = Number(v)
  return isNaN(n) ? '—' : n.toFixed(decimals)
}

export function StrategyLeaderboard({ leaderboard, selectedId }: Props) {
  return (
    <div className="border border-paper-rule rounded-[2px] bg-paper">
      <div className="px-4 py-3 border-b border-paper-rule">
        <p className="font-sans text-xs text-ink-tertiary uppercase tracking-wide">Promoted Strategies</p>
        <p className="font-sans text-xs text-ink-tertiary mt-1">{leaderboard.length} on leaderboard</p>
      </div>
      <div className="divide-y divide-paper-rule">
        {leaderboard.length === 0 && (
          <div className="px-4 py-6">
            <p className="font-sans text-sm text-ink-tertiary">No strategies promoted yet.</p>
            <p className="font-sans text-xs text-ink-tertiary mt-1">Engine is still optimizing on first pass.</p>
          </div>
        )}
        {leaderboard.map((row) => {
          const isSelected = row.genome_id === selectedId
          const sortino = Number(row.sortino_oos ?? 0)
          return (
            <Link
              key={row.genome_id}
              href={`/strategies/lab/${row.genome_id}`}
              className={`block px-4 py-3 hover:bg-teal-50 transition-colors ${isSelected ? 'bg-teal-50 border-l-2 border-teal-600' : ''}`}
            >
              <div className="flex justify-between items-start">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-xs text-ink-tertiary">#{row.rank}</span>
                    <span className={`font-sans text-xs font-semibold truncate ${isSelected ? 'text-teal-700' : 'text-ink-primary'}`}>
                      {row.strategy_name}
                    </span>
                  </div>
                  <p className="font-sans text-xs text-ink-tertiary mt-0.5">Gen {row.generation}</p>
                </div>
                <div className="text-right ml-2 flex-shrink-0">
                  <p className={`font-mono text-sm font-semibold ${sortino >= 1.5 ? 'text-teal-600' : sortino >= 1.0 ? 'text-ink-primary' : 'text-amber-600'}`}>
                    {fmt(row.sortino_oos)}
                  </p>
                  <p className="font-sans text-xs text-ink-tertiary">Sortino</p>
                </div>
              </div>
              <div className="flex gap-3 mt-2">
                <div>
                  <span className="font-sans text-xs text-ink-tertiary">Calmar </span>
                  <span className="font-mono text-xs text-ink-primary">{fmt(row.calmar_oos)}</span>
                </div>
                <div>
                  <span className="font-sans text-xs text-ink-tertiary">Alpha </span>
                  <span className={`font-mono text-xs ${Number(row.alpha_30d ?? 0) >= 0 ? 'text-teal-600' : 'text-red-500'}`}>
                    {Number(row.alpha_30d ?? 0) >= 0 ? '+' : ''}{fmt(row.alpha_30d)}
                  </span>
                </div>
              </div>
              <div className="mt-2 h-1 bg-paper-rule rounded-full overflow-hidden">
                <div className="h-full rounded-full bg-teal-500"
                  style={{ width: `${Math.min(100, sortino * 25)}%` }} />
              </div>
            </Link>
          )
        })}
      </div>
    </div>
  )
}
