'use client'

import Link from 'next/link'
import type { LeaderboardRow, InsightRow, GenePoolHealth } from '@/lib/queries/strategy_lab'
import { StrategyConfigurator } from './StrategyConfigurator'

type Props = {
  leaderboard: LeaderboardRow[]
  insights: InsightRow | null
  health: GenePoolHealth
  showConfigurator?: boolean
}

function fmt(v: string | null, decimals = 2): string {
  if (!v) return '—'
  const n = Number(v)
  return isNaN(n) ? '—' : n.toFixed(decimals)
}

function SignBadge({ value }: { value: string | null }) {
  const n = Number(value ?? '0')
  return (
    <span className={`font-mono font-semibold ${n >= 0 ? 'text-teal-600' : 'text-red-600'}`}>
      {n >= 0 ? '+' : ''}{fmt(value)}
    </span>
  )
}

export function MorningBrief({ leaderboard, insights, health, showConfigurator }: Props) {
  const top = leaderboard[0]
  const today = new Date().toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' })
  return (
    <div className="space-y-6">
      {showConfigurator && <StrategyConfigurator />}
      <header>
        <p className="font-sans text-xs text-ink-tertiary uppercase tracking-wide">Strategy Lab</p>
        <h1 className="font-serif text-2xl text-ink-primary mt-1">Morning Brief</h1>
        <p className="font-sans text-xs text-ink-tertiary mt-1">{today}</p>
      </header>
      {top ? (
        <section className="border border-paper-rule rounded-[2px] p-5 bg-paper">
          <p className="font-sans text-xs text-ink-tertiary uppercase tracking-wide mb-3">Top Strategy — Rank #{top.rank}</p>
          <h2 className="font-serif text-lg text-ink-primary">{top.strategy_name}</h2>
          <p className="font-sans text-xs text-ink-tertiary mt-1">Generation {top.generation}</p>
          <div className="grid grid-cols-3 gap-4 mt-4">
            <div><p className="font-sans text-xs text-ink-tertiary">Sortino (OOS)</p>
              <p className="font-mono text-xl font-semibold text-ink-primary mt-1">{fmt(top.sortino_oos)}</p></div>
            <div><p className="font-sans text-xs text-ink-tertiary">Calmar (OOS)</p>
              <p className="font-mono text-xl font-semibold text-ink-primary mt-1">{fmt(top.calmar_oos)}</p></div>
            <div><p className="font-sans text-xs text-ink-tertiary">30d Alpha</p><SignBadge value={top.alpha_30d} /></div>
          </div>
          <Link href={`/strategies/lab/${top.genome_id}`} className="inline-block mt-4 font-sans text-xs text-teal-600 hover:underline">
            View Strategy Explorer →
          </Link>
        </section>
      ) : (
        <section className="border border-paper-rule rounded-[2px] p-5 bg-paper">
          <p className="font-sans text-sm text-ink-tertiary">No strategies promoted yet. Engine running first optimization pass.</p>
        </section>
      )}
      <section className="grid grid-cols-3 gap-3">
        {[
          { label: 'Active Genomes', value: health.active_count },
          { label: 'Promoted', value: health.promoted_count },
          { label: 'Killed This Cycle', value: health.killed_count },
        ].map(({ label, value }) => (
          <div key={label} className="border border-paper-rule rounded-[2px] p-3 bg-paper">
            <p className="font-sans text-xs text-ink-tertiary uppercase tracking-wide">{label}</p>
            <p className="font-mono text-lg font-semibold text-ink-primary mt-1">{value}</p>
          </div>
        ))}
      </section>
      {insights && insights.insight_bullets.length > 0 && (
        <section className="border border-paper-rule rounded-[2px] p-5 bg-paper">
          <p className="font-sans text-xs text-ink-tertiary uppercase tracking-wide mb-3">What the Engine Learned Last Night</p>
          <ul className="space-y-2">
            {insights.insight_bullets.map((bullet, i) => (
              <li key={i} className="font-sans text-sm text-ink-primary flex gap-2">
                <span className="text-teal-600 font-mono">→</span>
                <span>{bullet.replace(/^\d+\.\s*/, '')}</span>
              </li>
            ))}
          </ul>
        </section>
      )}
      <nav className="flex gap-4">
        <Link href="/strategies/lab" className="font-sans text-xs border border-paper-rule rounded-[2px] px-4 py-2 text-ink-secondary hover:bg-paper-rule">Morning Brief</Link>
        <Link href={top ? `/strategies/lab/${top.genome_id}` : '/strategies/lab'} className="font-sans text-xs border border-paper-rule rounded-[2px] px-4 py-2 text-ink-secondary hover:bg-paper-rule">Strategy Explorer</Link>
        <Link href="/strategies/lab/engine" className="font-sans text-xs border border-paper-rule rounded-[2px] px-4 py-2 text-ink-secondary hover:bg-paper-rule">Engine Room</Link>
        <Link href="/strategies/lab?configurator=1" className="font-sans text-xs border border-teal-600 rounded-[2px] px-4 py-2 text-teal-600 hover:bg-teal-50">Configure</Link>
      </nav>
    </div>
  )
}
