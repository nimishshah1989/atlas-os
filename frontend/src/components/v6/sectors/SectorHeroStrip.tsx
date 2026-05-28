'use client'
// frontend/src/components/v6/sectors/SectorHeroStrip.tsx
// 6-tile verdict strip for Page 04a sector deep-dive.
// Source: mv_sector_deepdive scalars + returns JSONB + rs_windows JSONB.

import type { SectorDeepdiveRow } from '@/lib/queries/v6/sectors'

// ── Helpers ───────────────────────────────────────────────────────────────────

function fmtPct(v: number | null, decimals = 1): { text: string; cls: string } {
  if (v == null) return { text: '—', cls: 'text-ink-tertiary' }
  return {
    text: `${v >= 0 ? '+' : ''}${v.toFixed(decimals)}%`,
    cls: v >= 0 ? 'text-signal-pos' : 'text-signal-neg',
  }
}

function fmtPp(v: number | null): { text: string; cls: string } {
  if (v == null) return { text: '—', cls: 'text-ink-tertiary' }
  return {
    text: `${v >= 0 ? '+' : ''}${v.toFixed(1)}pp`,
    cls: v >= 0 ? 'text-signal-pos' : 'text-signal-neg',
  }
}

// ── Tile ──────────────────────────────────────────────────────────────────────

function Tile({
  label, value, valueCls, foot,
}: {
  label: string
  value: string
  valueCls?: string
  foot?: React.ReactNode
}) {
  return (
    <div
      className="px-5 py-[18px] border-r border-paper-rule last:border-r-0"
      aria-label={`${label}: ${value}`}
    >
      <div className="font-sans text-[9px] uppercase tracking-[0.18em] text-ink-tertiary font-semibold mb-1.5">
        {label}
      </div>
      <div className={`font-mono text-[22px] font-medium leading-[1.05] ${valueCls ?? 'text-ink-primary'}`}>
        {value}
      </div>
      {foot && (
        <div className="font-sans text-[11px] text-ink-tertiary mt-1 leading-[1.4]">{foot}</div>
      )}
    </div>
  )
}

// ── Verdict stamp ─────────────────────────────────────────────────────────────

function VerdictStamp({ verdict }: { verdict: string }) {
  const cls =
    verdict === 'Overweight' || verdict === 'OW'
      ? 'bg-signal-pos text-paper'
      : verdict === 'Underweight' || verdict === 'Avoid' || verdict === 'UW'
      ? 'bg-signal-neg text-paper'
      : 'bg-signal-warn/15 text-signal-warn border border-signal-warn/30'

  const label =
    verdict === 'Overweight' ? 'OVERWEIGHT'
    : verdict === 'Underweight' ? 'UNDERWEIGHT'
    : verdict === 'Avoid' ? 'AVOID'
    : verdict === 'Neutral' ? 'NEUTRAL'
    : verdict.toUpperCase()

  return (
    <span
      className={`inline-flex font-mono text-[11px] px-[9px] py-[3px] rounded-[2px] font-semibold tracking-[0.06em] ${cls}`}
    >
      {label}
    </span>
  )
}

// ── Main component ────────────────────────────────────────────────────────────

export function SectorHeroStrip({ sector }: { sector: SectorDeepdiveRow }) {
  const rs3m = fmtPp(sector.rs_windows?.rs_3m ?? null)
  const ret12m = fmtPct(sector.returns?.ret_12m ?? null)
  const ret3m = fmtPct(sector.returns?.ret_3m ?? null)
  const pctEma20 = sector.pct_above_ema20 != null
    ? Math.round(sector.pct_above_ema20 * 100)
    : null

  return (
    <div className="bg-paper-soft border border-paper-rule rounded-[2px] mt-6 overflow-hidden">
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6">
        <Tile
          label="RS · 3M vs Nifty 500"
          value={rs3m.text}
          valueCls={rs3m.cls}
          foot={<span>Latest vs Nifty 500 broad-market.</span>}
        />
        <Tile
          label="12M abs return"
          value={ret12m.text}
          valueCls={ret12m.cls}
          foot={<span>Absolute sector return, 12-month window.</span>}
        />
        <Tile
          label="3M abs return"
          value={ret3m.text}
          valueCls={ret3m.cls}
          foot={<span>Absolute sector return, 3-month window.</span>}
        />
        <Tile
          label="Constituents"
          value={String(sector.constituent_count)}
          foot={<span>Current universe members.</span>}
        />
        <Tile
          label="Above EMA20"
          value={pctEma20 != null ? `${pctEma20}%` : '—'}
          valueCls={pctEma20 != null && pctEma20 >= 60 ? 'text-signal-pos' : pctEma20 != null && pctEma20 < 40 ? 'text-signal-neg' : 'text-signal-warn'}
          foot={<span>Stocks above 20-day moving average.</span>}
        />
        <div className="px-5 py-[18px] flex flex-col justify-center items-start gap-1">
          <div className="font-sans text-[9px] uppercase tracking-[0.18em] text-ink-tertiary font-semibold mb-1.5">
            Verdict
          </div>
          <VerdictStamp verdict={sector.verdict} />
        </div>
      </div>
    </div>
  )
}
