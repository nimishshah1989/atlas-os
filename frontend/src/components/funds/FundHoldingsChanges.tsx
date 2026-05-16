'use client'

import { useState } from 'react'
import type { LatestHoldingsChangeRow } from '@/lib/queries/funds'

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i
function safeSymbol(s: string | null): string {
  if (!s || UUID_RE.test(s)) return '—'
  return s
}

function rsStateColor(state: string | null): string {
  if (!state) return 'text-ink-tertiary'
  if (state === 'Leader' || state === 'Strong') return 'text-signal-pos'
  if (state === 'Weak' || state === 'Declining') return 'text-signal-neg'
  return 'text-signal-warn'
}

function QualityDot({ quality }: { quality: string | null }) {
  if (!quality) return <span className="text-ink-tertiary/40">·</span>
  const cls =
    quality === 'high'
      ? 'text-signal-pos font-semibold'
      : quality === 'low'
        ? 'text-signal-neg font-semibold'
        : 'text-ink-tertiary'
  const label = quality === 'high' ? '✓ Good' : quality === 'low' ? '✗ Poor' : '— Neutral'
  return (
    <span className={`font-sans text-[10px] ${cls}`} title={`Signal quality: ${quality}`}>
      {label}
    </span>
  )
}

function pctFmt(v: string): string {
  const n = parseFloat(v)
  return isNaN(n) ? '—' : `${(n * 100).toFixed(2)}%`
}

function deltaPctFmt(v: string): string {
  const n = parseFloat(v)
  if (isNaN(n)) return '—'
  const s = (n * 100).toFixed(2)
  return n > 0 ? `+${s}%` : `${s}%`
}

type ActionGroup = 'entry' | 'exit' | 'increase' | 'decrease'

const GROUP_CONFIG: Record<
  ActionGroup,
  { label: string; dotColor: string; rowBg: string; borderColor: string; description: string }
> = {
  entry: {
    label: 'New Entries',
    dotColor: 'bg-signal-pos',
    rowBg: 'bg-signal-pos/5 hover:bg-signal-pos/10',
    borderColor: 'border-signal-pos/20',
    description: 'Stocks added to the portfolio for the first time this period',
  },
  exit: {
    label: 'Full Exits',
    dotColor: 'bg-signal-neg',
    rowBg: 'bg-signal-neg/5 hover:bg-signal-neg/10',
    borderColor: 'border-signal-neg/20',
    description: 'Stocks fully removed from the portfolio this period',
  },
  increase: {
    label: 'Position Increases',
    dotColor: 'bg-blue-400',
    rowBg: 'bg-blue-50/50 hover:bg-blue-50',
    borderColor: 'border-blue-200/60',
    description: 'Existing holdings with increased allocation',
  },
  decrease: {
    label: 'Position Trims',
    dotColor: 'bg-orange-400',
    rowBg: 'bg-orange-50/50 hover:bg-orange-50',
    borderColor: 'border-orange-200/60',
    description: 'Existing holdings with reduced allocation',
  },
}

function ChangeGroup({
  action,
  rows,
  defaultExpanded,
}: {
  action: ActionGroup
  rows: LatestHoldingsChangeRow[]
  defaultExpanded: boolean
}) {
  const [expanded, setExpanded] = useState(defaultExpanded)
  const cfg = GROUP_CONFIG[action]
  if (rows.length === 0) return null

  return (
    <div className="border border-paper-rule rounded-sm overflow-hidden">
      {/* Group header */}
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        className="w-full flex items-center gap-2 px-3 py-2 bg-paper hover:bg-paper-rule/5 text-left"
        title={cfg.description}
      >
        <span className={`w-2 h-2 rounded-full shrink-0 ${cfg.dotColor}`} />
        <span className="font-sans text-xs font-semibold text-ink-primary">{cfg.label}</span>
        <span className="font-sans text-[10px] text-ink-tertiary ml-1">
          {rows.length} stock{rows.length !== 1 ? 's' : ''}
        </span>
        <span className="ml-auto font-sans text-[10px] text-ink-tertiary">{expanded ? '▲' : '▼'}</span>
      </button>

      {expanded && (
        <div className="overflow-x-auto">
          <table className="w-full border-collapse text-left">
            <thead>
              <tr className="border-y border-paper-rule bg-paper-rule/5">
                <th className="px-3 py-1.5 font-sans text-[9px] text-ink-tertiary uppercase tracking-wide whitespace-nowrap">
                  Stock
                </th>
                <th className="px-3 py-1.5 font-sans text-[9px] text-ink-tertiary uppercase tracking-wide whitespace-nowrap text-right">
                  Before
                </th>
                <th className="px-3 py-1.5 font-sans text-[9px] text-ink-tertiary uppercase tracking-wide whitespace-nowrap text-right">
                  After
                </th>
                <th
                  className="px-3 py-1.5 font-sans text-[9px] text-ink-tertiary uppercase tracking-wide whitespace-nowrap text-right"
                  title="Change in portfolio weight"
                >
                  Δ Weight
                </th>
                <th
                  className="px-3 py-1.5 font-sans text-[9px] text-ink-tertiary uppercase tracking-wide whitespace-nowrap"
                  title="RS state of the stock at the time of the disclosure date"
                >
                  RS State at decision
                </th>
                <th
                  className="px-3 py-1.5 font-sans text-[9px] text-ink-tertiary uppercase tracking-wide whitespace-nowrap"
                  title="Was this a high-quality, low-quality, or neutral decision based on RS state?"
                >
                  Signal quality
                </th>
                <th
                  className="px-3 py-1.5 font-sans text-[9px] text-ink-tertiary uppercase tracking-wide whitespace-nowrap"
                  title="How did this stock perform in the month after the disclosure?"
                >
                  1m outcome
                </th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr
                  key={`${row.symbol}-${row.action}`}
                  className={`border-b border-paper-rule/50 transition-colors ${cfg.rowBg}`}
                >
                  <td className="px-3 py-1.5">
                    <div className="font-mono text-xs font-semibold text-ink-primary">
                      {safeSymbol(row.symbol)}
                    </div>
                    {row.company_name && (
                      <div className="font-sans text-[9px] text-ink-tertiary truncate max-w-[160px]">
                        {row.company_name}
                      </div>
                    )}
                  </td>
                  <td className="px-3 py-1.5 text-right font-mono text-xs text-ink-tertiary">
                    {pctFmt(row.weight_before)}
                  </td>
                  <td className="px-3 py-1.5 text-right font-mono text-xs text-ink-secondary">
                    {pctFmt(row.weight_after)}
                  </td>
                  <td
                    className={`px-3 py-1.5 text-right font-mono text-xs font-semibold ${
                      parseFloat(row.weight_delta) > 0
                        ? 'text-signal-pos'
                        : parseFloat(row.weight_delta) < 0
                          ? 'text-signal-neg'
                          : 'text-ink-tertiary'
                    }`}
                  >
                    {deltaPctFmt(row.weight_delta)}
                  </td>
                  <td className={`px-3 py-1.5 font-sans text-[11px] ${rsStateColor(row.rs_state_at_action)}`}>
                    {row.rs_state_at_action ?? '—'}
                  </td>
                  <td className="px-3 py-1.5">
                    <QualityDot quality={row.signal_quality} />
                  </td>
                  <td className="px-3 py-1.5">
                    {row.outcome_quality_1m ? (
                      <span
                        className={`font-sans text-[10px] ${
                          row.outcome_quality_1m === 'good'
                            ? 'text-signal-pos'
                            : row.outcome_quality_1m === 'bad'
                              ? 'text-signal-neg'
                              : 'text-ink-tertiary'
                        }`}
                        title={row.outcome_ret_1m ? `1m return: ${(parseFloat(row.outcome_ret_1m) * 100).toFixed(1)}%` : undefined}
                      >
                        {row.outcome_quality_1m === 'good'
                          ? '✓ Good'
                          : row.outcome_quality_1m === 'bad'
                            ? '✗ Bad'
                            : '— Neutral'}
                        {row.outcome_ret_1m && (
                          <span className="ml-1 text-ink-tertiary">
                            ({(parseFloat(row.outcome_ret_1m) * 100).toFixed(1)}%)
                          </span>
                        )}
                      </span>
                    ) : (
                      <span className="font-sans text-[10px] text-ink-tertiary/50 italic">pending</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

type Props = {
  changes: LatestHoldingsChangeRow[]
}

export function FundHoldingsChanges({ changes }: Props) {
  if (changes.length === 0) {
    return (
      <p className="font-sans text-sm text-ink-secondary">
        No holdings changes recorded for the latest disclosure period.
      </p>
    )
  }

  const periodDate = changes[0].period_date
  const entries = changes.filter((c) => c.action === 'entry')
  const exits = changes.filter((c) => c.action === 'exit')
  const increases = changes.filter((c) => c.action === 'increase')
  const decreases = changes.filter((c) => c.action === 'decrease')

  return (
    <div className="space-y-3">
      {/* Period header */}
      <div className="flex items-center gap-3">
        <div className="font-sans text-[11px] text-ink-tertiary">
          Latest disclosure period:{' '}
          <span className="font-mono text-ink-secondary font-medium">{periodDate}</span>
        </div>
        <div className="flex items-center gap-3 font-sans text-[10px] text-ink-tertiary">
          {entries.length > 0 && (
            <span>
              <span className="text-signal-pos font-semibold">{entries.length}</span> entries
            </span>
          )}
          {exits.length > 0 && (
            <span>
              <span className="text-signal-neg font-semibold">{exits.length}</span> exits
            </span>
          )}
          {increases.length > 0 && (
            <span>
              <span className="text-blue-500 font-semibold">{increases.length}</span> increases
            </span>
          )}
          {decreases.length > 0 && (
            <span>
              <span className="text-orange-500 font-semibold">{decreases.length}</span> decreases
            </span>
          )}
        </div>
      </div>

      {/* Groups — entries and exits expanded by default; size changes collapsed */}
      <div className="space-y-2">
        <ChangeGroup action="entry" rows={entries} defaultExpanded />
        <ChangeGroup action="exit" rows={exits} defaultExpanded />
        <ChangeGroup action="increase" rows={increases} defaultExpanded={false} />
        <ChangeGroup action="decrease" rows={decreases} defaultExpanded={false} />
      </div>

      <div className="font-sans text-[10px] text-ink-tertiary pt-1">
        <strong>RS State at decision</strong> = the stock&apos;s relative strength state on the disclosure date.{' '}
        <strong>Signal quality</strong> = whether the buy/sell was consistent with momentum (high = good timing, low = poor timing).{' '}
        <strong>1m outcome</strong> = how the stock actually performed after the decision.
      </div>
    </div>
  )
}
