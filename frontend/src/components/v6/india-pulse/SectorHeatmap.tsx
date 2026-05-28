'use client'
// frontend/src/components/v6/india-pulse/SectorHeatmap.tsx
//
// Section 6 — Sectoral indices heatmap.
// 11-wide grid of colored sector cells, sorted by rs_1w.
// Toggle between rs_1w / ret_1m / ret_3m (client-side state).

import { useState } from 'react'
import type { SectorHeatmapItem } from '@/lib/queries/v6/india_pulse'
import { fmtPct } from './helpers'

type Props = {
  sectors: SectorHeatmapItem[]
}

type Window = '1w' | '1m' | '3m'

function cellClass(val: number | null): string {
  if (val == null) return 'bg-paper border border-paper-rule'
  const pct = val * 100
  if (pct >= 3.0) return 'bg-[rgba(47,107,67,0.55)]'
  if (pct >= 1.5) return 'bg-[rgba(47,107,67,0.30)]'
  if (pct > 0.3) return 'bg-[rgba(47,107,67,0.15)]'
  if (pct >= -0.3) return 'bg-paper border border-paper-rule'
  if (pct >= -1.5) return 'bg-[rgba(176,73,44,0.15)]'
  if (pct >= -3.0) return 'bg-[rgba(176,73,44,0.30)]'
  return 'bg-[rgba(176,73,44,0.55)]'
}

function textClass(val: number | null): string {
  if (val == null) return 'text-ink-secondary'
  const pct = val * 100
  if (pct >= 3.0 || pct <= -3.0) return 'text-paper'
  return 'text-ink-secondary'
}

export function SectorHeatmap({ sectors }: Props) {
  // Default to '1m' because mv_india_pulse.sector_heatmap.rs_1w is currently
  // NULL across all sectors (rs_1w only populated when 5-day RS panel is fresh).
  // Switching default to '1m' ensures the heatmap renders colored cells on first paint.
  const [activeWindow, setActiveWindow] = useState<Window>('1m')

  const getValue = (s: SectorHeatmapItem): number | null => {
    switch (activeWindow) {
      case '1w': return s.rs_1w
      case '1m': return s.ret_1m
      case '3m': return s.ret_3m
    }
  }

  // Sort by the active window value
  const sorted = [...sectors].sort((a, b) => {
    const av = getValue(a) ?? 0
    const bv = getValue(b) ?? 0
    return bv - av
  })

  if (sectors.length === 0) {
    return (
      <div className="text-sm text-ink-tertiary py-4">
        No sector heatmap data available.
      </div>
    )
  }

  return (
    <>
      {/* Toggle chips */}
      <div className="flex items-center gap-3 mb-4">
        <span className="text-[10px] uppercase tracking-[0.14em] text-ink-tertiary font-semibold">Window</span>
        {(['1w', '1m', '3m'] as Window[]).map(w => (
          <button
            key={w}
            onClick={() => setActiveWindow(w)}
            className={`px-2.5 py-0.5 text-[11px] border rounded-sm font-medium transition-colors cursor-pointer ${
              activeWindow === w
                ? 'bg-accent text-paper border-accent'
                : 'bg-paper text-ink-tertiary border-paper-rule hover:text-ink-secondary'
            }`}
          >
            {w.toUpperCase()}
          </button>
        ))}
        <a
          href="/sectors"
          className="ml-3 text-[12px] text-accent font-medium hover:underline"
        >
          Open Sectors →
        </a>
      </div>

      {/* Heatmap grid */}
      <div className="grid grid-cols-11 gap-1">
        {sorted.map(s => {
          const val = getValue(s)
          return (
            <div
              key={s.sector_name}
              className={`aspect-square rounded-sm flex flex-col items-center justify-center text-center cursor-pointer hover:brightness-95 transition-all p-1 ${cellClass(val)}`}
              title={`${s.sector_name}: ${fmtPct(val)}`}
            >
              <div className={`text-[9px] font-semibold tracking-[0.04em] leading-tight ${textClass(val)}`}>
                {s.sector_name.length > 10 ? `${s.sector_name.slice(0, 9)}…` : s.sector_name}
              </div>
              <div className={`font-mono text-[12px] font-semibold mt-0.5 ${textClass(val)}`}>
                {fmtPct(val)}
              </div>
            </div>
          )
        })}
      </div>

      {/* Legend */}
      <div className="flex items-center gap-4 mt-3.5 text-[11px] text-ink-tertiary">
        <span>Colour scale:</span>
        <div className="flex gap-0.5">
          {[
            'bg-[rgba(176,73,44,0.55)]',
            'bg-[rgba(176,73,44,0.30)]',
            'bg-[rgba(176,73,44,0.15)]',
            'bg-paper border border-paper-rule',
            'bg-[rgba(47,107,67,0.15)]',
            'bg-[rgba(47,107,67,0.30)]',
            'bg-[rgba(47,107,67,0.55)]',
          ].map((cls, i) => (
            <div key={i} className={`w-3.5 h-3.5 rounded-sm ${cls}`} />
          ))}
        </div>
        <span className="font-mono text-[10px]">−3% · 0 · +3%</span>
        <span className="ml-2 text-[10px] text-ink-tertiary">
          {activeWindow === '1w' ? '1W relative strength' : activeWindow === '1m' ? '1M return' : '3M return'}
        </span>
      </div>
    </>
  )
}
