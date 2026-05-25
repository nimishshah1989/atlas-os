'use client'

// frontend/src/components/v6/SectorBreadthPanel.tsx
// Design lock: design-application.md §7.4
// Concentration thresholds (verbatim from §7.4):
//   top3 < 40%  → "Broad participation"  (signal-pos)
//   40–65%      → "Distributed"          (signal-warn)
//   > 65%       → "Narrow leadership ⚠"  (signal-neg)
// NOTE: top3_concentration_pct is "0.00" in v6.0 — no market_cap column yet.

import type { SectorBreadth } from '@/lib/queries/v6/sector_breadth'

export interface SectorBreadthPanelProps {
  breadth: SectorBreadth
  className?: string
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function parsePct(s: string): number {
  const n = parseFloat(s)
  return Number.isFinite(n) ? n : 0
}

function displayPct(s: string): string {
  return `${parsePct(s).toFixed(1)}%`
}

type ConcentrationTier = 'broad' | 'distributed' | 'narrow'

function getConcentrationTier(top3Pct: string): ConcentrationTier {
  const n = parsePct(top3Pct)
  if (n < 40) return 'broad'
  if (n <= 65) return 'distributed'
  return 'narrow'
}

const CONCENTRATION_CONFIG: Record<ConcentrationTier, { label: string; cls: string; badgeCls: string }> = {
  broad:       { label: 'Broad participation',  cls: 'signal-pos', badgeCls: 'bg-signal-pos/15 text-signal-pos border border-signal-pos/30' },
  distributed: { label: 'Distributed',          cls: 'signal-warn', badgeCls: 'bg-signal-warn/15 text-signal-warn border border-signal-warn/30' },
  narrow:      { label: 'Narrow leadership ⚠',  cls: 'signal-neg', badgeCls: 'bg-signal-neg/15 text-signal-neg border border-signal-neg/30' },
}

function getDispersionLabel(sigmaStr: string): string {
  const sigma = parsePct(sigmaStr)
  if (sigma < 10) return 'consensus'
  if (sigma <= 20) return 'moderate'
  return "stockpicker's"
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function GaugeBar({ pctStr, label }: { pctStr: string; label: string }) {
  const filled = Math.max(0, Math.min(100, parsePct(pctStr)))
  return (
    <div
      className="flex items-center gap-3"
      aria-label={`${label}: ${displayPct(pctStr)} of constituents above`}
    >
      <span className="w-[100px] shrink-0 font-sans text-[11px] text-ink-secondary">{label}</span>
      <span className="w-[42px] shrink-0 font-mono text-[12px] tabular-nums text-ink-primary text-right">
        {displayPct(pctStr)}
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

// ---------------------------------------------------------------------------
// SectorBreadthPanel
// ---------------------------------------------------------------------------

export function SectorBreadthPanel({ breadth, className = '' }: SectorBreadthPanelProps) {
  const tier = getConcentrationTier(breadth.top3_concentration_pct)
  const { label, cls, badgeCls } = CONCENTRATION_CONFIG[tier]
  const dispersionLabel = getDispersionLabel(breadth.dispersion_sigma)

  return (
    <section
      className={['border border-paper-rule rounded-[2px] bg-paper p-4 space-y-4', className]
        .filter(Boolean).join(' ')}
      aria-label={`Sector breadth panel for ${breadth.sector}`}
    >
      <div className="flex items-baseline justify-between gap-2">
        <h3 className="font-sans text-[13px] font-semibold text-ink-primary">{breadth.sector}</h3>
        <span className="font-sans text-[11px] text-ink-tertiary shrink-0">{breadth.as_of_date}</span>
      </div>

      <p className="font-sans text-[11px] text-ink-secondary -mt-2">
        {breadth.n_stocks} constituents
      </p>

      <div className="space-y-2" aria-label="EMA breadth gauges">
        <GaugeBar pctStr={breadth.pct_above_sma20} label="Above EMA20" />
        <GaugeBar pctStr={breadth.pct_above_sma50} label="Above EMA50" />
        <GaugeBar pctStr={breadth.pct_above_sma200} label="Above EMA200" />
      </div>

      <div className="flex items-center gap-2">
        <span className="font-sans text-[11px] text-ink-secondary shrink-0">Concentration:</span>
        <span
          className={`inline-flex items-center font-sans text-[11px] font-semibold px-2 py-0.5 rounded-[2px] ${badgeCls} ${cls}`}
          aria-label={`Concentration: ${label}`}
        >
          {label}
        </span>
      </div>

      <div
        className="flex items-center gap-2"
        aria-label={`Sector dispersion sigma: ${displayPct(breadth.dispersion_sigma)}, ${dispersionLabel}`}
      >
        <span className="font-sans text-[11px] text-ink-secondary shrink-0">Sector dispersion σ:</span>
        <span className="font-mono text-[12px] tabular-nums text-ink-primary">
          {displayPct(breadth.dispersion_sigma)}
        </span>
        <span className="font-sans text-[11px] text-ink-tertiary">{dispersionLabel}</span>
      </div>
    </section>
  )
}

export default SectorBreadthPanel
