'use client'
// src/components/portfolio/DeteriorationPanel.tsx
// Per-portfolio deterioration panel: surfaces holdings that hit a Policy exit rule.
//
// Rules evaluated (C3 — each item shows WHY it deteriorated):
//   state_exit_full  → "Stage 4 — full exit required"
//   state_exit_trim  → "Stage 3 — trim position"
//   hard_stop_pct    → NOT evaluated (no entry-price data; labelled honestly as n/a)
//
// C1 — every ticker links to its stock detail page via LinkedTicker.
// C5 — no synthetic data; hard_stop_pct shows "n/a — entry price not tracked".
//
// Regime worklist (TodayWorklist / mv_deterioration_watch) is cross-portfolio
// and UNTOUCHED. This panel is the per-portfolio, policy-driven companion.

import { LinkedTicker } from '@/components/ui/LinkedToken'
import { InfoTooltip } from '@/components/ui/InfoTooltip'
import type { DeteriItem } from '@/lib/policy-deterioration'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type Props = {
  items: DeteriItem[]
  /** Pass false to show the hard-stop as "n/a — entry price not tracked". Defaults false. */
  hardStopTracked?: boolean
}

// ---------------------------------------------------------------------------
// Formatting
// ---------------------------------------------------------------------------

function fmtPct(n: number): string {
  return `${n.toFixed(2)}%`
}

// ---------------------------------------------------------------------------
// Rule badge sub-component
// ---------------------------------------------------------------------------

const RULE_TOOLTIPS: Record<'full_exit' | 'trim', string> = {
  full_exit:
    'This holding has entered the full-exit state defined by the portfolio policy. ' +
    'The policy recommends exiting 100% of this position.',
  trim:
    'This holding has entered the trim state defined by the portfolio policy. ' +
    'The policy recommends reducing this position.',
}

function RuleBadge({ rule, itemId }: { rule: 'full_exit' | 'trim'; itemId: string }) {
  const isFullExit = rule === 'full_exit'
  const label = isFullExit ? 'Full Exit' : 'Trim'
  const colorClass = isFullExit
    ? 'border-signal-neg/40 text-signal-neg bg-signal-neg/8'
    : 'border-signal-warn/40 text-signal-warn bg-signal-warn/8'

  return (
    <span className="inline-flex items-center gap-1">
      <span
        data-testid={`rule-badge-${itemId}`}
        className={`font-sans text-[10px] px-1.5 py-0.5 rounded-[2px] border ${colorClass}`}
      >
        {label}
      </span>
      <InfoTooltip content={RULE_TOOLTIPS[rule]} />
    </span>
  )
}

// ---------------------------------------------------------------------------
// Empty state
// ---------------------------------------------------------------------------

function EmptyState() {
  return (
    <div
      data-testid="deterioration-empty"
      className="flex items-center gap-2 rounded-[3px] border border-signal-pos/30 bg-signal-pos/5 px-4 py-3"
    >
      <span className="inline-block w-2 h-2 rounded-full bg-signal-pos shrink-0" />
      <span className="font-sans text-xs text-signal-pos">
        No holdings hitting an exit rule
      </span>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export function DeteriorationPanel({ items, hardStopTracked = false }: Props) {
  return (
    <div>
      {/* Hard-stop status — honest labelling when entry price is not tracked */}
      <div className="flex items-center gap-2 mb-3">
        <span className="font-sans text-xs text-ink-tertiary">Hard stop:</span>
        <span
          data-testid="hard-stop-status"
          className="font-sans text-xs text-ink-tertiary"
        >
          {hardStopTracked ? 'evaluated' : 'n/a — entry price not tracked'}
        </span>
        <InfoTooltip content="The hard-stop rule (exit if down X% from entry) requires the original entry price. Entry price data is not stored in this portfolio builder — hard-stop evaluation is not available." />
      </div>

      {items.length === 0 ? (
        <EmptyState />
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse" role="table">
            <thead>
              <tr className="border-b border-paper-rule">
                <th className="font-sans text-xs text-ink-tertiary uppercase tracking-wide pb-2 pr-4 font-medium">
                  Holding
                </th>
                <th className="font-sans text-xs text-ink-tertiary uppercase tracking-wide pb-2 pr-4 font-medium">
                  Rule
                </th>
                <th className="font-sans text-xs text-ink-tertiary uppercase tracking-wide pb-2 pr-4 font-medium">
                  State
                </th>
                <th className="font-sans text-xs text-ink-tertiary uppercase tracking-wide pb-2 font-medium text-right">
                  Current Weight
                </th>
              </tr>
            </thead>
            <tbody>
              {items.map((item) => (
                <tr
                  key={item.instrument_id}
                  data-testid={`deterioration-row-${item.instrument_id}`}
                  className="border-b border-paper-rule/50"
                >
                  <td className="py-2 pr-4 font-mono text-xs">
                    <LinkedTicker symbol={item.symbol} />
                  </td>
                  <td className="py-2 pr-4">
                    <RuleBadge rule={item.rule} itemId={item.instrument_id} />
                  </td>
                  <td className="py-2 pr-4 font-mono text-xs text-ink-secondary">
                    {item.engine_state}
                  </td>
                  <td
                    data-testid={`weight-${item.instrument_id}`}
                    className="py-2 font-mono text-xs text-right text-signal-neg"
                  >
                    {fmtPct(item.weight_pct)}
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
