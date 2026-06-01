'use client'

// frontend/src/components/v6/calls/WinRateMatrix.tsx
//
// 3 tiers × 4 tenures × 2 directions (POS/NEG) win-rate matrix.
// Shows realized hit_rate (win %) and avg realized_excess_pct per cell.
// Color-coded using CSS color-mix with Atlas token variables (M1 — no hardcoded rgba).
// Matches mockup layout: tiers as rows, tenure × direction as columns.

import type { CSSProperties } from 'react'
import Link from 'next/link'
import type { WinRateCell } from '@/lib/queries/v6/calls'
import { fmtSignedPct } from '@/lib/format-number'

interface WinRateMatrixProps {
  cells: WinRateCell[]
}

const TIERS = ['Large', 'Mid', 'Small'] as const
const TENURES = ['1m', '3m', '6m', '12m'] as const
const ACTIONS = ['POSITIVE', 'NEGATIVE'] as const

type CellKey = `${string}|${string}|${string}`

function buildLookup(cells: WinRateCell[]): Map<CellKey, WinRateCell> {
  const map = new Map<CellKey, WinRateCell>()
  for (const c of cells) {
    map.set(`${c.cap_tier}|${c.tenure}|${c.action}`, c)
  }
  return map
}

/**
 * M1: Color scale using color-mix with Atlas CSS token variables.
 * Keyed on hit_rate (win rate). Falls back to avg_realized_excess when hit_rate null.
 */
function cellStyle(
  hitRate: number | null,
  realizedExcess: number | null,
): { style: CSSProperties; textClass: string } {
  // Use hit_rate as primary metric, realized_excess as fallback
  const metric = hitRate

  if (metric === null && realizedExcess === null) {
    return { style: {}, textClass: 'text-ink-4' }
  }

  if (metric !== null) {
    // Color by win rate
    if (metric >= 0.75)
      return {
        style: { background: 'color-mix(in srgb, var(--color-signal-pos, #1D9E75) 55%, transparent)' },
        textClass: 'text-paper',
      }
    if (metric >= 0.60)
      return {
        style: { background: 'color-mix(in srgb, var(--color-signal-pos, #1D9E75) 38%, transparent)' },
        textClass: 'text-ink-primary',
      }
    if (metric >= 0.50)
      return {
        style: { background: 'color-mix(in srgb, var(--color-signal-pos, #1D9E75) 22%, transparent)' },
        textClass: 'text-ink-primary',
      }
    if (metric >= 0.40)
      return {
        style: { background: 'color-mix(in srgb, var(--color-signal-warn, #B8860B) 20%, transparent)' },
        textClass: 'text-ink-primary',
      }
    if (metric >= 0.25)
      return {
        style: { background: 'color-mix(in srgb, var(--color-signal-neg, #B0492C) 22%, transparent)' },
        textClass: 'text-ink-primary',
      }
    return {
      style: { background: 'color-mix(in srgb, var(--color-signal-neg, #B0492C) 38%, transparent)' },
      textClass: 'text-paper',
    }
  }

  // Fallback: realized excess
  const pct = (realizedExcess ?? 0) * 100
  if (pct > 8)
    return {
      style: { background: 'color-mix(in srgb, var(--color-signal-pos, #1D9E75) 55%, transparent)' },
      textClass: 'text-paper',
    }
  if (pct > 0)
    return {
      style: { background: 'color-mix(in srgb, var(--color-signal-pos, #1D9E75) 30%, transparent)' },
      textClass: 'text-ink-primary',
    }
  return {
    style: { background: 'color-mix(in srgb, var(--color-signal-neg, #B0492C) 30%, transparent)' },
    textClass: 'text-ink-primary',
  }
}

export function WinRateMatrix({ cells }: WinRateMatrixProps) {
  const lookup = buildLookup(cells)

  return (
    <div>
      <div className="flex items-baseline justify-between mb-3">
        <h3 className="font-serif text-[18px] text-ink-primary">
          Realized win-rate matrix · 3 tiers × 4 tenures × direction
        </h3>
      </div>
      <p className="text-[11px] text-ink-4 mb-3 leading-snug">
        Win rate = % of calls that beat the tier-anchor benchmark.
        Avg realized excess shown below each win rate. Green = higher win rate · Red = lower.
      </p>

      <div className="overflow-x-auto">
        <table className="w-full border-collapse text-[12px]">
          <thead>
            <tr>
              <th className="text-left px-[10px] py-[6px] text-[9px] font-semibold uppercase tracking-[0.14em] text-ink-4 bg-paper-soft border-b border-ink-rule">
                Tier
              </th>
              {TENURES.map((tenure) => (
                <th
                  key={tenure}
                  colSpan={2}
                  className="text-center px-1 py-[6px] text-[9px] font-semibold uppercase tracking-[0.14em] text-ink-4 bg-paper-soft border-b border-ink-rule border-l border-paper-rule"
                >
                  {tenure}
                </th>
              ))}
            </tr>
            <tr>
              <th className="bg-paper-soft border-b border-ink-rule" />
              {TENURES.map((tenure) =>
                ACTIONS.map((action) => (
                  <th
                    key={`${tenure}|${action}`}
                    className={`text-center px-1 py-[3px] text-[8px] text-ink-4 bg-paper-soft border-b border-ink-rule ${action === 'POSITIVE' ? 'border-l border-paper-rule' : ''}`}
                  >
                    {action === 'POSITIVE' ? 'POS' : 'NEG'}
                  </th>
                )),
              )}
            </tr>
          </thead>
          <tbody>
            {TIERS.map((tier) => (
              <tr key={tier}>
                <td className="px-[12px] py-[9px] text-left font-medium text-ink-primary text-[12.5px] border-b border-paper-rule">
                  {tier}
                </td>
                {TENURES.map((tenure) =>
                  ACTIONS.map((action) => {
                    const cell = lookup.get(`${tier}|${tenure}|${action}`)
                    const hitRate = cell?.hit_rate ?? null
                    const realizedExcess = cell?.avg_realized_excess ?? null
                    const n = cell?.call_count ?? 0
                    const hitRateStr = hitRate != null ? `${(hitRate * 100).toFixed(0)}%` : '—'
                    const excessStr = fmtSignedPct(realizedExcess)
                    const { style: cellBg, textClass } = cellStyle(hitRate, realizedExcess)
                    return (
                      <td
                        key={`${tenure}|${action}`}
                        className={`p-0 border-b border-paper-rule text-center font-mono ${action === 'POSITIVE' ? 'border-l border-paper-rule' : ''}`}
                      >
                        <Link
                          href={`/stocks?tier=${encodeURIComponent(tier)}&tenure=${encodeURIComponent(tenure)}&direction=${encodeURIComponent(action)}`}
                          className={`block px-1 py-2 transition-[filter] hover:brightness-90 no-underline ${textClass}`}
                          style={cellBg}
                          title={n > 0 ? `n=${n} · win rate ${hitRateStr} · avg realized ${excessStr} — click to see stocks` : 'No data'}
                        >
                          <div className="text-[13px] font-semibold leading-none">{hitRateStr}</div>
                          <div className="text-[9px] mt-[2px] opacity-75 tracking-[0.04em]">
                            {excessStr}
                          </div>
                          <div className="text-[8px] mt-[1px] opacity-60 tracking-[0.04em]">
                            n={n > 0 ? n : '—'}
                          </div>
                        </Link>
                      </td>
                    )
                  }),
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Legend */}
      <div className="mt-3 px-3 py-[10px] bg-paper-soft border border-paper-rule rounded-[2px] flex flex-wrap gap-3 items-center text-[11px] text-ink-4">
        <span className="font-medium text-ink-secondary">Win rate scale:</span>
        {[
          {
            style: { background: 'color-mix(in srgb, var(--color-signal-neg, #B0492C) 38%, transparent)' },
            label: '<25%',
          },
          {
            style: { background: 'color-mix(in srgb, var(--color-signal-neg, #B0492C) 22%, transparent)' },
            label: '25–40%',
          },
          {
            style: { background: 'color-mix(in srgb, var(--color-signal-warn, #B8860B) 20%, transparent)' },
            label: '40–50%',
          },
          {
            style: { background: 'color-mix(in srgb, var(--color-signal-pos, #1D9E75) 22%, transparent)' },
            label: '50–60%',
          },
          {
            style: { background: 'color-mix(in srgb, var(--color-signal-pos, #1D9E75) 38%, transparent)' },
            label: '60–75%',
          },
          {
            style: { background: 'color-mix(in srgb, var(--color-signal-pos, #1D9E75) 55%, transparent)' },
            label: '>75%',
          },
        ].map((s) => (
          <span key={s.label} className="inline-flex items-center gap-1.5">
            <span className="inline-block w-4 h-3.5 rounded-[1px]" style={s.style} />
            {s.label}
          </span>
        ))}
        <span className="ml-auto text-[10px] text-ink-4 font-mono">Cell shows win rate · avg realized excess · n</span>
      </div>
    </div>
  )
}
