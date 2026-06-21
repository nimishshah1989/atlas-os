// frontend/src/components/v6/india-pulse/HeadlineIndices.tsx
//
// Section 1 — 8 rich headline index cards in a 4×2 grid.
// Server component — no interactivity.

import type { HeadlineIndexItem } from '@/lib/queries/v6/india_pulse'
import { fmtPct } from './helpers'

type Props = {
  indices: HeadlineIndexItem[]
}

function borderClass(ret1d: number | null): string {
  if (ret1d == null) return 'border-l-[3px] border-l-ink-tertiary'
  if (ret1d > 0.005) return 'border-l-[3px] border-l-signal-pos'
  if (ret1d < -0.005) return 'border-l-[3px] border-l-signal-neg'
  return 'border-l-[3px] border-l-signal-warn'
}

function dotColor(ret1d: number | null): string {
  if (ret1d == null) return 'bg-ink-tertiary'
  if (ret1d > 0.005) return 'bg-signal-pos'
  if (ret1d < -0.005) return 'bg-signal-neg'
  return 'bg-signal-warn'
}

function retColor(v: number | null): string {
  if (v == null) return 'text-ink-tertiary'
  if (v > 0) return 'text-signal-pos'
  if (v < 0) return 'text-signal-neg'
  return 'text-ink-secondary'
}

function fmtClose(v: number | null): string {
  if (v == null) return '—'
  return v.toLocaleString('en-IN', { maximumFractionDigits: 0 })
}

function rsLabel(index_code: string): string {
  if (index_code === 'NIFTY 500') return 'The baseline (≡)'
  return 'RS vs Nifty 500 · 3M'
}

export function HeadlineIndices({ indices }: Props) {
  if (indices.length === 0) {
    return (
      <div className="text-sm text-ink-tertiary py-6">
        No headline index data available.
      </div>
    )
  }

  return (
    <div className="grid grid-cols-4 gap-3">
      {indices.map(idx => (
        <div
          key={idx.index_code}
          className={`bg-paper border border-paper-rule rounded-sm p-3.5 hover:bg-paper-deep transition-colors cursor-pointer ${borderClass(idx.ret_1d)}`}
        >
          {/* Name + dot */}
          <div className="flex items-baseline justify-between gap-2 mb-1">
            <span className="text-[10px] uppercase tracking-[0.12em] text-ink-secondary font-bold">
              {idx.label}
            </span>
            <span className={`inline-block w-1.5 h-1.5 rounded-full shrink-0 ${dotColor(idx.ret_1d)}`} />
          </div>

          {/* Level */}
          <div className="font-mono text-[20px] font-medium text-ink-primary leading-tight">
            {fmtClose(idx.close)}
          </div>

          {/* Today return */}
          <div className={`font-mono text-[12px] font-medium mt-0.5 ${retColor(idx.ret_1d)}`}>
            {idx.ret_1d != null ? `${fmtPct(idx.ret_1d)} today` : '—'}
          </div>

          {/* Spark placeholder — intraday price series not yet in MV */}
          <div className="my-2 h-9 bg-paper-deep/50 rounded-sm" />

          {/* Window returns */}
          <div className="grid grid-cols-3 gap-1 pt-1.5 border-t border-paper-rule font-mono text-[11px]">
            {[
              { label: '1M', val: idx.ret_1m },
              { label: '3M', val: idx.ret_3m },
              { label: '6M', val: idx.ret_6m },
            ].map(w => (
              <div key={w.label} className="flex flex-col items-center">
                <span className="text-[8px] uppercase tracking-[0.12em] text-ink-4 font-semibold">
                  {w.label}
                </span>
                <span className={`font-medium mt-0.5 ${retColor(w.val)}`}>
                  {fmtPct(w.val)}
                </span>
              </div>
            ))}
          </div>

          {/* RS vs Nifty 500 */}
          <div className="mt-1.5 pt-1.5 border-t border-paper-rule flex justify-between items-center text-[10px] text-ink-tertiary">
            <span>{rsLabel(idx.index_code)}</span>
            {idx.index_code === 'NIFTY 500' ? (
              <span className="font-mono font-semibold text-ink-tertiary">—</span>
            ) : (
              <span className={`font-mono font-semibold ${retColor(idx.rs_3m_vs_nifty500)}`}>
                {idx.rs_3m_vs_nifty500 != null
                  ? fmtPct(idx.rs_3m_vs_nifty500)
                  : '—'}
              </span>
            )}
          </div>
        </div>
      ))}
    </div>
  )
}
