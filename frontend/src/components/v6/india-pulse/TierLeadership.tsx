'use client'
// frontend/src/components/v6/india-pulse/TierLeadership.tsx
//
// Section 5 — Tier leadership: mid & small vs large.
// Left: placeholder RS Z-score chart (series not in MV — only current Z available).
// Right: Tier returns table (5 windows × SC/MC/LC/spreads).
// Uses Recharts for the returns comparison chart.

import type { TierLeadership as TierLeadershipData } from '@/lib/queries/v6/india_pulse'
import { fmtZ, fmtPct } from './helpers'

type Props = {
  tier_leadership: TierLeadershipData | null
}

/** Format spread (pp) without the % suffix — distinguishes from returns. */
function fmtSpread(v: number | null): string {
  if (v == null) return '—'
  const pct = v * 100
  const abs = Math.abs(pct).toFixed(1)
  if (pct < 0) return `−${abs}`
  return `+${abs}`
}

function retColor(v: number | null): string {
  if (v == null) return 'text-ink-tertiary'
  if (v > 0) return 'text-signal-pos'
  if (v < 0) return 'text-signal-neg'
  return 'text-ink-secondary'
}

function spreadColor(v: number | null): string {
  if (v == null) return 'text-ink-tertiary'
  if (v > 0) return 'text-signal-pos'
  if (v < 0) return 'text-signal-neg'
  return 'text-ink-secondary'
}

export function TierLeadership({ tier_leadership }: Props) {
  if (!tier_leadership) {
    return (
      <div className="text-sm text-ink-tertiary py-4">
        No tier leadership data available.
      </div>
    )
  }

  const { returns_table, smallcap_rs_z } = tier_leadership
  const zColor = smallcap_rs_z == null
    ? 'text-ink-tertiary'
    : smallcap_rs_z < 0
    ? 'text-signal-neg'
    : 'text-signal-pos'

  return (
    <div className="grid grid-cols-2 gap-4">
      {/* Left — Z-score summary card */}
      <div className="bg-paper border border-paper-rule rounded-sm p-5">
        <div className="flex items-baseline justify-between mb-4">
          <span className="font-serif text-[18px] text-ink-primary">
            Tier RS Z-scores · current
          </span>
        </div>

        {/* Smallcap Z-score hero */}
        <div className="mb-6">
          <div className="text-[10px] uppercase tracking-[0.18em] text-ink-tertiary font-semibold mb-1">
            Smallcap 250 RS Z-score (vs Nifty 100)
          </div>
          <div className={`font-mono text-[40px] font-medium leading-tight ${zColor}`}>
            {fmtZ(smallcap_rs_z)}
          </div>
          <div className="text-[12px] text-ink-tertiary mt-2 leading-[1.45]">
            {smallcap_rs_z != null ? (
              smallcap_rs_z < -1.0
                ? <><strong className="text-signal-neg">Deeply negative.</strong> Small-caps significantly underperforming large-caps. Strong defensive rotation.</>
                : smallcap_rs_z < 0
                ? <><strong className="text-signal-warn">Negative.</strong> Small-caps lagging large-caps. Defensive bias in the market.</>
                : smallcap_rs_z > 1.0
                ? <><strong className="text-signal-pos">Strongly positive.</strong> Small-caps leading — risk appetite high.</>
                : <><strong className="text-signal-pos">Positive.</strong> Small-caps outperforming large-caps.</>
            ) : 'Z-score data not yet populated for this date.'}
          </div>
        </div>

        {/* Regime interpretation */}
        <div className="border-t border-paper-rule pt-4">
          <div className="text-[11px] text-ink-tertiary leading-[1.6]">
            <strong className="text-ink-secondary">Regime signal:</strong> Small-cap RS Z-score is one of the
            four canonical regime inputs (per CONTEXT.md). A negative Z-score for 3+ consecutive weeks
            signals a shift to defensive / large-cap leadership. Z &lt; −1.0 is the hard threshold for
            the &ldquo;Defensive&rdquo; regime classification.
          </div>
        </div>
      </div>

      {/* Right — Tier returns table */}
      <div className="bg-paper border border-paper-rule rounded-sm p-5">
        <div className="flex items-baseline justify-between mb-4">
          <span className="font-serif text-[18px] text-ink-primary">
            Tier returns · trailing windows
          </span>
        </div>

        {returns_table.length === 0 ? (
          <div className="text-sm text-ink-tertiary">No tier returns data available.</div>
        ) : (() => {
          // Always render all 5 canonical windows — fill from MV data, em-dash for missing
          const WINDOWS: { key: string; label: string }[] = [
            { key: '1w', label: '1 week' },
            { key: '1m', label: '1 month' },
            { key: '3m', label: '3 months' },
            { key: '6m', label: '6 months' },
            { key: '12m', label: '12 months' },
          ]
          const rowByWindow = Object.fromEntries(returns_table.map(r => [r.window, r]))

          return (
            <table className="tbl-centered w-full border-collapse text-[12.5px]">
              <thead>
                <tr>
                  <th className="text-left text-[9px] uppercase tracking-[0.18em] text-ink-tertiary font-semibold py-2 border-b border-ink-rule">
                    Window
                  </th>
                  <th className="text-right font-mono text-[9px] uppercase tracking-[0.18em] text-ink-tertiary font-semibold py-2 border-b border-ink-rule">
                    SC 250
                  </th>
                  <th className="text-right font-mono text-[9px] uppercase tracking-[0.18em] text-ink-tertiary font-semibold py-2 border-b border-ink-rule">
                    MC 150
                  </th>
                  <th className="text-right font-mono text-[9px] uppercase tracking-[0.18em] text-ink-tertiary font-semibold py-2 border-b border-ink-rule">
                    Nifty 100
                  </th>
                  <th className="text-right font-mono text-[9px] uppercase tracking-[0.18em] text-ink-tertiary font-semibold py-2 border-b border-ink-rule">
                    SC−LC<span className="text-[7px] ml-0.5">pp</span>
                  </th>
                  <th className="text-right font-mono text-[9px] uppercase tracking-[0.18em] text-ink-tertiary font-semibold py-2 border-b border-ink-rule">
                    MC−LC<span className="text-[7px] ml-0.5">pp</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {WINDOWS.map(({ key, label }) => {
                  const row = rowByWindow[key]
                  return (
                    <tr key={key} className="border-b border-paper-rule last:border-b-0">
                      <td className="py-2 text-ink-secondary">
                        <strong className="text-ink-primary">{label}</strong>
                      </td>
                      <td className={`text-right font-mono py-2 ${retColor(row?.sc ?? null)}`}>
                        {fmtPct(row?.sc ?? null)}
                      </td>
                      <td className={`text-right font-mono py-2 ${retColor(row?.mc ?? null)}`}>
                        {fmtPct(row?.mc ?? null)}
                      </td>
                      <td className={`text-right font-mono py-2 ${retColor(row?.lc ?? null)}`}>
                        {fmtPct(row?.lc ?? null)}
                      </td>
                      <td className={`text-right font-mono py-2 ${spreadColor(row?.sc_lc_spread ?? null)}`}>
                        {fmtSpread(row?.sc_lc_spread ?? null)}
                      </td>
                      <td className={`text-right font-mono py-2 ${spreadColor(row?.mc_lc_spread ?? null)}`}>
                        {fmtSpread(row?.mc_lc_spread ?? null)}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          )
        })()}

        <p className="text-[12px] text-ink-tertiary mt-3 leading-[1.5]">
          Spread columns show small-cap and mid-cap return <em>minus</em> large-cap return for each window.
          Negative spreads = large-cap leadership. Watch the mid-cap spread — it historically leads
          small-cap by 4–8 weeks at regime turns.
        </p>
        <p className="text-[11px] text-ink-tertiary mt-2 leading-[1.4] border-t border-paper-rule pt-2">
          <em>Note:</em> Mid-cap RS Z-score dimension pending <span className="font-mono text-ink-secondary">mv_india_pulse</span> extension.
        </p>
      </div>
    </div>
  )
}
