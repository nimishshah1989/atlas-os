'use client'
// src/app/strategies/StrategiesView.tsx
// Client island: filter bar + sortable strategies table.
// allow-large: owns all interactive state for strategies list — filter chips, URL sync, table render

import { useRouter, usePathname, useSearchParams } from 'next/navigation'
import { useCallback } from 'react'
import Link from 'next/link'
import type { StrategyRow } from '@/lib/queries/strategies'

const TIERS = ['Aggressive', 'Moderate', 'Passive']
const ARCHETYPES = [
  'momentum_blend',
  'sector_rotation',
  'quality_growth',
  'low_volatility',
  'mean_reversion',
]

function formatPct(raw: string | null): string {
  if (raw == null) return '—'
  const n = parseFloat(raw)
  return isNaN(n) ? '—' : `${n >= 0 ? '+' : ''}${(n * 100).toFixed(2)}%`
}

function formatSharpe(raw: string | null): string {
  if (raw == null) return '—'
  const n = parseFloat(raw)
  return isNaN(n) ? '—' : n.toFixed(2)
}

function formatDate(d: Date | null): string {
  if (!d) return '—'
  const date = d instanceof Date ? d : new Date(String(d))
  return date.toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' })
}

type Props = {
  strategies: StrategyRow[]
  initialTier?: string
  initialArchetype?: string
  initialPaperActive?: string
}

export function StrategiesView({
  strategies,
  initialTier,
  initialArchetype,
  initialPaperActive,
}: Props) {
  const router = useRouter()
  const pathname = usePathname()
  const searchParams = useSearchParams()

  const updateParams = useCallback(
    (updates: Record<string, string | undefined>) => {
      const current = new URLSearchParams(searchParams.toString())
      for (const [key, val] of Object.entries(updates)) {
        if (val == null || val === '') {
          current.delete(key)
        } else {
          current.set(key, val)
        }
      }
      router.push(`${pathname}?${current.toString()}`)
    },
    [router, pathname, searchParams],
  )

  const activeTier = initialTier ?? ''
  const activeArchetype = initialArchetype ?? ''
  const activePaper = initialPaperActive ?? ''

  // Client-side filter (server already filtered by URL params, this is for instant UX)
  const filtered = strategies.filter((s) => {
    if (activeTier && s.tier !== activeTier) return false
    if (activeArchetype && s.archetype !== activeArchetype) return false
    if (activePaper === 'true' && !s.paper_active) return false
    if (activePaper === 'false' && s.paper_active) return false
    return true
  })

  return (
    <div>
      {/* Filter bar */}
      <div className="flex flex-wrap items-center gap-3 mb-5 pb-4 border-b border-paper-rule">
        {/* Tier chips */}
        <div className="flex gap-1.5">
          <span className="font-sans text-xs text-ink-tertiary self-center mr-1">Tier:</span>
          {TIERS.map((tier) => (
            <button
              key={tier}
              type="button"
              onClick={() => updateParams({ tier: activeTier === tier ? '' : tier })}
              className={`font-sans text-xs px-3 py-1 rounded-[2px] border transition-colors ${
                activeTier === tier
                  ? 'bg-accent text-white border-accent'
                  : 'text-ink-secondary border-paper-rule hover:text-ink-primary'
              }`}
            >
              {tier}
            </button>
          ))}
        </div>

        {/* Archetype chips */}
        <div className="flex gap-1.5 flex-wrap">
          <span className="font-sans text-xs text-ink-tertiary self-center mr-1">Archetype:</span>
          {ARCHETYPES.map((arch) => (
            <button
              key={arch}
              type="button"
              onClick={() => updateParams({ archetype: activeArchetype === arch ? '' : arch })}
              className={`font-sans text-xs px-2 py-1 rounded-[2px] border transition-colors ${
                activeArchetype === arch
                  ? 'bg-accent text-white border-accent'
                  : 'text-ink-secondary border-paper-rule hover:text-ink-primary'
              }`}
            >
              {arch.replace(/_/g, ' ')}
            </button>
          ))}
        </div>

        {/* Paper active toggle */}
        <button
          type="button"
          onClick={() => {
            const next = activePaper === 'true' ? '' : 'true'
            updateParams({ paper: next })
          }}
          className={`font-sans text-xs px-3 py-1 rounded-[2px] border transition-colors ${
            activePaper === 'true'
              ? 'bg-signal-pos/10 text-signal-pos border-signal-pos/30'
              : 'text-ink-secondary border-paper-rule hover:text-ink-primary'
          }`}
        >
          Paper Active
        </button>

        {(activeTier || activeArchetype || activePaper) && (
          <button
            type="button"
            onClick={() => updateParams({ tier: '', archetype: '', paper: '' })}
            className="font-sans text-xs text-ink-tertiary hover:text-ink-primary underline decoration-dotted"
          >
            Clear filters
          </button>
        )}
      </div>

      {/* Table */}
      <div className="overflow-x-auto">
        <table className="w-full text-left border-collapse">
          <thead>
            <tr className="border-b border-paper-rule">
              {['Name', 'Archetype', 'Tier', 'Sharpe', 'Alpha vs N500', 'Paper', 'Updated'].map(
                (col) => (
                  <th
                    key={col}
                    className="font-sans text-xs text-ink-tertiary uppercase tracking-wide pb-2 pr-4 font-medium"
                  >
                    {col}
                  </th>
                ),
              )}
            </tr>
          </thead>
          <tbody>
            {filtered.length === 0 && (
              <tr>
                <td colSpan={7} className="py-8 text-center font-sans text-sm text-ink-tertiary">
                  No strategies match the current filters.
                </td>
              </tr>
            )}
            {filtered.map((s) => (
              <tr
                key={s.id}
                className="border-b border-paper-rule/50 hover:bg-paper-rule/10 transition-colors cursor-pointer"
              >
                <td className="py-3 pr-4">
                  <Link
                    href={`/strategies/${s.id}`}
                    className="font-sans text-sm text-ink-primary hover:text-accent transition-colors"
                  >
                    {s.name}
                  </Link>
                </td>
                <td className="py-3 pr-4 font-sans text-xs text-ink-secondary">
                  {s.archetype.replace(/_/g, ' ')}
                </td>
                <td className="py-3 pr-4">
                  <span className="font-sans text-xs text-ink-secondary">{s.tier}</span>
                </td>
                <td className="py-3 pr-4 font-mono text-sm text-ink-primary text-right">
                  {formatSharpe(s.latest_sharpe)}
                </td>
                <td
                  className={`py-3 pr-4 font-mono text-sm text-right ${
                    s.latest_alpha_vs_nifty500 != null &&
                    parseFloat(s.latest_alpha_vs_nifty500) >= 0
                      ? 'text-signal-pos'
                      : 'text-signal-neg'
                  }`}
                >
                  {formatPct(s.latest_alpha_vs_nifty500)}
                </td>
                <td className="py-3 pr-4">
                  {s.paper_active ? (
                    <span className="inline-block w-2 h-2 rounded-full bg-signal-pos" title="Paper trading active" />
                  ) : (
                    <span className="inline-block w-2 h-2 rounded-full bg-paper-rule" title="Paper trading inactive" />
                  )}
                </td>
                <td className="py-3 font-sans text-xs text-ink-tertiary">
                  {formatDate(s.latest_backtest_at)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
