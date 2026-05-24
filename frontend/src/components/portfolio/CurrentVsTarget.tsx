'use client'
// src/components/portfolio/CurrentVsTarget.tsx
// Current-vs-target weight table for a static portfolio.
//
// Renders:
//   - Per-holding row: ticker (LinkedTicker), current %, target % or "—", gap (signed, green/red)
//   - Pending proposed changes as visually distinct rows with a "proposed" badge
//   - Compliance banner (breach list or "Policy-compliant" confirmation)
//   - Weights-sum footer: invested % · cash %
//
// C5: null target_weight_pct → renders "—", never "0". Gap omitted when no target.
// C7: weights-sum computed from current holdings. Compliance runs checkCompliance().

import { LinkedTicker } from '@/components/ui/LinkedToken'
import { InfoTooltip } from '@/components/ui/InfoTooltip'
import { checkCompliance } from '@/lib/policy-compliance'
import type { CompliancePolicy } from '@/lib/policy-compliance'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type CurrentVsTargetHolding = {
  instrument_id: string
  instrument_type: 'stock' | 'etf' | 'fund'
  // symbol is the display ticker (e.g. "HDFCBANK"). Null = LinkedTicker renders "—".
  symbol: string | null
  weight_pct: number
  // null means no target set — renders "—" in Target column. Gap is also omitted.
  target_weight_pct: number | null
  sector: string
  is_small_cap: boolean
}

export type PendingProposedChange = {
  id: string
  instrument_id: string
  // symbol resolved by the caller from the universe; null for unknown instruments
  symbol: string | null
  proposed_weight: number
  rationale: string | null
}

type Props = {
  holdings: CurrentVsTargetHolding[]
  pendingChanges: PendingProposedChange[]
  policy: CompliancePolicy
}

// ---------------------------------------------------------------------------
// Formatting helpers
// ---------------------------------------------------------------------------

function fmtPct(n: number): string {
  return `${n.toFixed(2)}%`
}

function fmtGap(gap: number): string {
  return gap >= 0 ? `+${gap.toFixed(2)}%` : `${gap.toFixed(2)}%`
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function ComplianceBanner({ breaches }: { breaches: ReturnType<typeof checkCompliance> }) {
  if (breaches.length === 0) {
    return (
      <div className="flex items-center gap-2 rounded-[3px] border border-signal-pos/30 bg-signal-pos/5 px-4 py-2 mb-4">
        <span className="inline-block w-2 h-2 rounded-full bg-signal-pos shrink-0" />
        <span className="font-sans text-xs text-signal-pos">Policy-compliant</span>
      </div>
    )
  }

  return (
    <div
      data-testid="compliance-banner"
      className="rounded-[3px] border border-signal-neg/30 bg-signal-neg/5 px-4 py-3 mb-4"
    >
      <div className="flex items-center gap-2 mb-2">
        <span className="inline-block w-2 h-2 rounded-full bg-signal-neg shrink-0" />
        <span className="font-sans text-xs font-semibold text-signal-neg">
          {breaches.length} policy {breaches.length === 1 ? 'breach' : 'breaches'}
        </span>
      </div>
      <ul className="space-y-1">
        {breaches.map((b, i) => (
          <li key={i} className="font-sans text-xs text-signal-neg leading-relaxed">
            {b.message}
          </li>
        ))}
      </ul>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Column header tooltips
// ---------------------------------------------------------------------------

const COL_TOOLTIPS = {
  current:
    'Current weight of this holding as a percentage of total portfolio value. This is the live allocation, not the target.',
  target:
    'Target weight set by the fund manager. "—" means no target has been configured for this holding yet.',
  gap: 'Gap = Target − Current. A positive gap means the holding is underweight vs. target (consider adding). A negative gap means overweight (consider trimming).',
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export function CurrentVsTarget({ holdings, pendingChanges, policy }: Props) {
  // Weights sum (C7)
  const investedPct = holdings.reduce((sum, h) => sum + h.weight_pct, 0)
  const cashPct = 100 - investedPct

  // Compliance check
  const complianceHoldings = holdings.map((h) => ({
    instrument_id: h.symbol ?? h.instrument_id,
    weight_pct: h.weight_pct,
    sector: h.sector,
    is_small_cap: h.is_small_cap,
  }))
  const breaches = checkCompliance(complianceHoldings, policy)

  return (
    <div>
      <ComplianceBanner breaches={breaches} />

      <div className="overflow-x-auto">
        <table className="w-full text-left border-collapse">
          <thead>
            <tr className="border-b border-paper-rule">
              <th className="font-sans text-xs text-ink-tertiary uppercase tracking-wide pb-2 pr-4 font-medium">
                Holding
              </th>
              <th className="font-sans text-xs text-ink-tertiary uppercase tracking-wide pb-2 pr-4 font-medium text-right">
                <span className="inline-flex items-center gap-1 justify-end">
                  Current
                  <InfoTooltip content={COL_TOOLTIPS.current} />
                </span>
              </th>
              <th className="font-sans text-xs text-ink-tertiary uppercase tracking-wide pb-2 pr-4 font-medium text-right">
                <span className="inline-flex items-center gap-1 justify-end">
                  Target
                  <InfoTooltip content={COL_TOOLTIPS.target} />
                </span>
              </th>
              <th className="font-sans text-xs text-ink-tertiary uppercase tracking-wide pb-2 font-medium text-right">
                <span className="inline-flex items-center gap-1 justify-end">
                  Gap
                  <InfoTooltip content={COL_TOOLTIPS.gap} />
                </span>
              </th>
            </tr>
          </thead>
          <tbody>
            {/* Current holdings rows */}
            {holdings.map((h) => {
              const gap =
                h.target_weight_pct !== null ? h.target_weight_pct - h.weight_pct : null
              const gapColor =
                gap === null
                  ? ''
                  : gap > 0
                    ? 'text-signal-pos'
                    : gap < 0
                      ? 'text-signal-neg'
                      : 'text-ink-primary'

              return (
                <tr
                  key={h.instrument_id}
                  className="border-b border-paper-rule/50"
                >
                  <td className="py-2 pr-4 font-mono text-xs">
                    {h.instrument_type === 'stock' ? (
                      <LinkedTicker symbol={h.symbol} />
                    ) : (
                      <span className="text-ink-primary">{h.symbol ?? h.instrument_id}</span>
                    )}
                  </td>
                  <td className="py-2 pr-4 font-mono text-xs text-right text-ink-primary">
                    {fmtPct(h.weight_pct)}
                  </td>
                  <td className="py-2 pr-4 font-mono text-xs text-right text-ink-secondary">
                    {h.target_weight_pct !== null ? (
                      fmtPct(h.target_weight_pct)
                    ) : (
                      <span className="text-ink-tertiary">—</span>
                    )}
                  </td>
                  <td className={`py-2 font-mono text-xs text-right ${gapColor}`}>
                    {gap !== null ? (
                      fmtGap(gap)
                    ) : (
                      <span className="text-ink-tertiary">—</span>
                    )}
                  </td>
                </tr>
              )
            })}

            {/* Pending proposed changes — visually distinct rows */}
            {pendingChanges.map((pc) => (
              <tr
                key={pc.id}
                className="border-b border-paper-rule/50 bg-signal-warn/5"
              >
                <td className="py-2 pr-4 font-mono text-xs">
                  <span className="flex items-center gap-2">
                    <LinkedTicker symbol={pc.symbol} />
                    <span className="font-sans text-[10px] px-1.5 py-0.5 rounded-[2px] border border-signal-warn/40 text-signal-warn bg-signal-warn/10">
                      proposed
                    </span>
                    {pc.rationale && (
                      <InfoTooltip content={pc.rationale} />
                    )}
                  </span>
                </td>
                <td className="py-2 pr-4 font-mono text-xs text-right text-ink-tertiary">
                  —
                </td>
                <td className="py-2 pr-4 font-mono text-xs text-right text-signal-warn">
                  {fmtPct(pc.proposed_weight)}
                </td>
                <td className="py-2 font-mono text-xs text-right text-ink-tertiary">
                  —
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* C7: Weights sum footer */}
      <div
        data-testid="weights-sum"
        className="mt-3 flex items-center gap-4 font-sans text-xs text-ink-secondary border-t border-paper-rule pt-2"
      >
        <span>
          Invested{' '}
          <span className="font-mono text-ink-primary">{fmtPct(investedPct)}</span>
        </span>
        <span className="text-ink-tertiary">·</span>
        <span>
          Cash{' '}
          <span className={`font-mono ${cashPct < 0 ? 'text-signal-neg' : 'text-ink-primary'}`}>
            {fmtPct(cashPct)}
          </span>
        </span>
        <span className="text-ink-tertiary">·</span>
        <span>
          {holdings.length} {holdings.length === 1 ? 'position' : 'positions'}
        </span>
      </div>
    </div>
  )
}
