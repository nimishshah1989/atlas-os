'use client'

import { useRouter } from 'next/navigation'
import { useState } from 'react'
import type { FundDecisionScoreRow, FundHoldingsChangeRow } from '@/lib/queries/funds'

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i
function safeSymbol(s: string | null | undefined): string {
  if (!s || UUID_RE.test(s)) return '—'
  return s
}

function ActionBadge({ action }: { action: string }) {
  const colors: Record<string, string> = {
    entry: 'bg-signal-pos/15 text-signal-pos font-semibold',
    exit: 'bg-signal-neg/15 text-signal-neg font-semibold',
    increase: 'bg-blue-50 text-blue-600',
    decrease: 'bg-orange-50 text-orange-600',
  }
  return (
    <span
      className={`inline-flex items-center px-1.5 py-0.5 rounded-[2px] font-sans text-[10px] uppercase ${colors[action] ?? ''}`}
    >
      {action}
    </span>
  )
}

function QualityBadge({ quality }: { quality: string | null }) {
  if (!quality) return <span className="text-ink-tertiary">—</span>
  const colors: Record<string, string> = {
    high: 'text-signal-pos font-semibold',
    low: 'text-signal-neg font-semibold',
    neutral: 'text-ink-tertiary',
    good: 'text-signal-pos font-semibold',
    bad: 'text-signal-neg font-semibold',
  }
  return <span className={`font-sans text-[11px] ${colors[quality] ?? ''}`}>{quality}</span>
}

function ScoreCard({
  label,
  value,
  pending = false,
}: {
  label: string
  value: string | null
  pending?: boolean
}) {
  const num = value !== null ? Number(value) : null
  const color =
    num === null
      ? 'text-ink-tertiary'
      : num >= 65
        ? 'text-signal-pos'
        : num >= 40
          ? 'text-signal-warn'
          : 'text-signal-neg'
  return (
    <div className="flex flex-col items-center bg-paper-rule/5 rounded-sm px-4 py-2 min-w-[100px]">
      <span className="font-sans text-[10px] text-ink-tertiary uppercase tracking-wide">{label}</span>
      <span className={`font-mono text-lg font-bold mt-0.5 ${color}`}>
        {pending ? (
          <span className="text-[11px] text-ink-tertiary italic">Pending</span>
        ) : num !== null ? (
          num.toFixed(1)
        ) : (
          '—'
        )}
      </span>
    </div>
  )
}

const ACTION_TABS = ['All', 'entry', 'exit', 'increase', 'decrease'] as const

type Props = {
  scores: FundDecisionScoreRow[]
  initialChanges: FundHoldingsChangeRow[]
  initialPeriod: string
}

export function FundManagerDecisionsDetail({ scores, initialChanges, initialPeriod }: Props) {
  const router = useRouter()
  const [activeTab, setActiveTab] = useState<(typeof ACTION_TABS)[number]>('All')

  const changes = initialChanges
  const currentScore = scores.find((s) => s.period_date === initialPeriod)
  const filtered = activeTab === 'All' ? changes : changes.filter((c) => c.action === activeTab)

  function handlePeriodChange(period: string) {
    router.push(`?period=${period}`)
  }

  return (
    <div className="space-y-4">
      {/* Period selector */}
      <div className="flex items-center gap-3">
        <label htmlFor="period-select" className="font-sans text-[11px] text-ink-tertiary">
          Period
        </label>
        <select
          id="period-select"
          value={initialPeriod}
          onChange={(e) => handlePeriodChange(e.target.value)}
          className="font-mono text-sm border border-paper-rule rounded px-2 py-1 bg-paper text-ink-primary"
        >
          {scores.map((s) => (
            <option key={s.period_date} value={s.period_date}>
              {s.period_date}
            </option>
          ))}
        </select>
      </div>

      {/* Score cards */}
      {currentScore && (
        <div className="flex gap-3 flex-wrap">
          <ScoreCard label="Signal Score" value={currentScore.signal_score} />
          <ScoreCard
            label="1m Outcome"
            value={currentScore.outcome_score_1m}
            pending={currentScore.outcome_score_1m === null}
          />
          <ScoreCard
            label="3m Outcome"
            value={currentScore.outcome_score_3m}
            pending={currentScore.outcome_score_3m === null}
          />
        </div>
      )}

      {/* Action tabs */}
      <div className="flex gap-1 border-b border-paper-rule">
        {ACTION_TABS.map((tab) => (
          <button
            key={tab}
            type="button"
            onClick={() => setActiveTab(tab)}
            className={`px-3 py-1.5 font-sans text-xs capitalize border-b-2 transition-colors ${
              activeTab === tab
                ? 'border-teal text-teal font-medium'
                : 'border-transparent text-ink-tertiary hover:text-ink-secondary'
            }`}
          >
            {tab === 'All'
              ? `All (${changes.length})`
              : `${tab} (${changes.filter((c) => c.action === tab).length})`}
          </button>
        ))}
      </div>

      {/* Changes table */}
      <div className="overflow-x-auto">
        <table className="w-full text-left border-collapse">
          <thead>
            <tr className="border-b border-paper-rule">
              {[
                'Symbol',
                'Action',
                'Before',
                'After',
                'Δ Weight',
                'RS State',
                'Signal',
                '1m Outcome',
                '3m Outcome',
              ].map((h) => (
                <th
                  key={h}
                  className="py-2 px-2 font-sans text-[10px] text-ink-tertiary uppercase tracking-wide whitespace-nowrap"
                >
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {filtered.map((row) => (
              <tr key={row.symbol} className="border-b border-paper-rule/50 hover:bg-paper-rule/5">
                <td className="py-1.5 px-2 font-mono text-xs font-medium">{safeSymbol(row.symbol)}</td>
                <td className="py-1.5 px-2">
                  <ActionBadge action={row.action} />
                </td>
                <td className="py-1.5 px-2 font-mono text-xs text-right">
                  {(Number(row.weight_before) * 100).toFixed(2)}%
                </td>
                <td className="py-1.5 px-2 font-mono text-xs text-right">
                  {(Number(row.weight_after) * 100).toFixed(2)}%
                </td>
                <td
                  className={`py-1.5 px-2 font-mono text-xs text-right ${Number(row.weight_delta) > 0 ? 'text-signal-pos' : Number(row.weight_delta) < 0 ? 'text-signal-neg' : 'text-ink-tertiary'}`}
                >
                  {Number(row.weight_delta) > 0 ? '+' : ''}
                  {(Number(row.weight_delta) * 100).toFixed(2)}%
                </td>
                <td className="py-1.5 px-2 font-sans text-[11px]">
                  {row.rs_state_at_action ?? '—'}
                </td>
                <td className="py-1.5 px-2">
                  <QualityBadge quality={row.signal_quality} />
                </td>
                <td className="py-1.5 px-2">
                  <QualityBadge quality={row.outcome_quality_1m} />
                </td>
                <td className="py-1.5 px-2">
                  <QualityBadge quality={row.outcome_quality_3m} />
                </td>
              </tr>
            ))}
            {filtered.length === 0 && (
              <tr>
                <td colSpan={9} className="py-6 text-center font-sans text-sm text-ink-tertiary">
                  No {activeTab === 'All' ? '' : activeTab} changes this period.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
