'use client'
// frontend/src/components/v6/sectors/SectorHeroStrip.tsx
// 6-tile verdict strip for Page 04a sector deep-dive.
// Source: mv_sector_deepdive scalars + returns JSONB + rs_windows JSONB.

import type { SectorDeepdiveRow } from '@/lib/queries/v6/sectors'

// ── Helpers ───────────────────────────────────────────────────────────────────

function fmtPct(v: number | null, decimals = 1): { text: string; cls: string } {
  if (v == null) return { text: '—', cls: 'text-txt-3' }
  return {
    text: `${v >= 0 ? '+' : ''}${v.toFixed(decimals)}%`,
    cls: v >= 0 ? 'text-sig-pos' : 'text-sig-neg',
  }
}

function fmtPp(v: number | null): { text: string; cls: string } {
  if (v == null) return { text: '—', cls: 'text-txt-3' }
  return {
    text: `${v >= 0 ? '+' : ''}${v.toFixed(1)}pp`,
    cls: v >= 0 ? 'text-sig-pos' : 'text-sig-neg',
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
      className="px-5 py-[18px] border-r border-edge-hair last:border-r-0"
      aria-label={`${label}: ${value}`}
    >
      <div className="font-num text-[9px] uppercase tracking-[0.18em] text-txt-3 font-semibold mb-1.5">
        {label}
      </div>
      <div className={`font-num text-[22px] font-medium tabular-nums leading-[1.05] ${valueCls ?? 'text-txt-1'}`}>
        {value}
      </div>
      {foot && (
        <div className="font-sans text-[11px] text-txt-3 mt-1 leading-[1.4]">{foot}</div>
      )}
    </div>
  )
}

// ── Verdict stamp ─────────────────────────────────────────────────────────────

function VerdictStamp({ verdict }: { verdict: string }) {
  const cls =
    verdict === 'Overweight' || verdict === 'OW'
      ? 'bg-sig-pos text-surface-base'
      : verdict === 'Underweight' || verdict === 'Avoid' || verdict === 'UW'
      ? 'bg-sig-neg text-surface-base'
      : 'bg-sig-warn/15 text-sig-warn border border-sig-warn/30'

  const label =
    verdict === 'Overweight' ? 'OVERWEIGHT'
    : verdict === 'Underweight' ? 'UNDERWEIGHT'
    : verdict === 'Avoid' ? 'AVOID'
    : verdict === 'Neutral' ? 'NEUTRAL'
    : verdict.toUpperCase()

  return (
    <span
      className={`inline-flex font-num text-[11px] px-[9px] py-[3px] rounded-tile font-semibold tracking-[0.06em] ${cls}`}
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
  const pctEma20 = sector.pct_above_ema21 != null
    ? Math.round(sector.pct_above_ema21 * 100)
    : null

  return (
    <div className="bg-surface-panel border border-edge-hair rounded-panel shadow-panel mt-6 overflow-hidden">
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
          foot={<span>Cap-weighted index return, 12-month window.</span>}
        />
        <Tile
          label="3M abs return"
          value={ret3m.text}
          valueCls={ret3m.cls}
          foot={<span>Cap-weighted index return, 3-month window.</span>}
        />
        <Tile
          label="Constituents"
          value={String(sector.constituent_count)}
          foot={<span>Current universe members.</span>}
        />
        <Tile
          label="Above EMA21"
          value={pctEma20 != null ? `${pctEma20}%` : '—'}
          valueCls={pctEma20 != null && pctEma20 >= 60 ? 'text-sig-pos' : pctEma20 != null && pctEma20 < 40 ? 'text-sig-neg' : 'text-sig-warn'}
          foot={<span>Stocks above 20-day moving average.</span>}
        />
        <div className="px-5 py-[18px] flex flex-col justify-center items-start gap-1">
          <div className="font-num text-[9px] uppercase tracking-[0.18em] text-txt-3 font-semibold mb-1.5">
            Verdict
          </div>
          <VerdictStamp verdict={sector.verdict} />
        </div>
      </div>
    </div>
  )
}
