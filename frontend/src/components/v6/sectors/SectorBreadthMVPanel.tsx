'use client'
// frontend/src/components/v6/sectors/SectorBreadthMVPanel.tsx
// Breadth panel derived from atlas.mv_sector_breadth JSONB.
// Renders EMA gauge bars, breadth-by-window, top/bottom movers per sector.
// Data shape: SectorBreadthMVRow[] from getSectorBreadthMV().

import type { SectorBreadthMVRow } from '@/lib/queries/v6/sectors'

// ── Helpers ───────────────────────────────────────────────────────────────────

function fmtPct(v: number | null): string {
  if (v == null) return '—'
  return `${v.toFixed(1)}%`
}

// ── Gauge bar ────────────────────────────────────────────────────────────────

function GaugeBar({ label, value }: { label: string; value: number | null }) {
  const filled = value != null ? Math.max(0, Math.min(100, value * 100)) : 0
  return (
    <div
      className="flex items-center gap-3"
      aria-label={`${label}: ${fmtPct(value != null ? value * 100 : null)} of constituents above`}
    >
      <span className="w-[110px] shrink-0 font-sans text-[11px] text-ink-secondary">{label}</span>
      <span className="w-[44px] shrink-0 font-mono text-[12px] tabular-nums text-ink-primary text-right">
        {value != null ? fmtPct(value * 100) : '—'}
      </span>
      <span className="flex-1 h-[6px] bg-paper-deep rounded-[2px] overflow-hidden" aria-hidden="true">
        <span
          className="h-full bg-signal-pos rounded-[2px] transition-[width] duration-300"
          style={{ width: `${filled}%` }}
        />
      </span>
    </div>
  )
}

// ── Single sector breadth card ─────────────────────────────────────────────────

function BreadthCard({ row }: { row: SectorBreadthMVRow }) {
  return (
    <div className="bg-paper border border-ink-rule rounded-[2px] p-4">
      <div className="flex items-baseline justify-between mb-3">
        <span className="font-sans text-[13px] font-semibold text-ink-primary">{row.sector_name}</span>
        <span className="font-mono text-[10px] text-ink-4">{row.constituent_count} stocks</span>
      </div>

      <div className="space-y-2 mb-4" aria-label="EMA breadth gauges">
        <GaugeBar label="Above EMA21" value={row.pct_above_ema21} />
        <GaugeBar label="Above EMA50" value={row.pct_above_ema50} />
        <GaugeBar label="Above EMA200" value={row.pct_above_ema200} />
      </div>

      {/* Top movers snippet */}
      {row.top_movers.length > 0 && (
        <div className="pt-3 border-t border-ink-rule">
          <div className="text-[10px] uppercase tracking-[0.14em] text-ink-4 font-semibold mb-1">
            Top movers
          </div>
          <div className="flex flex-wrap gap-x-3 gap-y-0.5">
            {row.top_movers.slice(0, 3).map((m) => (
              <span key={m.symbol} className="font-mono text-[10px] text-signal-pos">
                {m.symbol} +{m.ret_pct.toFixed(1)}%
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

// ── Main panel ────────────────────────────────────────────────────────────────

export function SectorBreadthMVPanel({ rows }: { rows: SectorBreadthMVRow[] }) {
  if (rows.length === 0) {
    return (
      <div className="py-6 text-center font-sans text-sm text-ink-4">
        Breadth data unavailable.
      </div>
    )
  }

  // Sort by pct_above_ema21 desc (broadest participation first)
  const sorted = [...rows].sort(
    (a, b) => (b.pct_above_ema21 ?? -1) - (a.pct_above_ema21 ?? -1),
  )

  return (
    <div
      className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4"
      aria-label="Sector breadth grid"
      data-testid="sector-breadth-mv-panel"
    >
      {sorted.map((row) => (
        <BreadthCard key={row.sector_name} row={row} />
      ))}
    </div>
  )
}
