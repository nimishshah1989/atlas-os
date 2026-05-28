'use client'

// frontend/src/components/v6/etfs/EtfHeroStrip.tsx
//
// Verdict strip for the ETF deep-dive page (07a).
// 6-tile row: 12M return · tracking error · premium to NAV · ADV · AUM proxy · TER proxy.
// All NULL values render '—'. Data from EtfDeepdiveRow.

import type { EtfDeepdiveRow } from '@/lib/queries/v6/etfs'

function fmtPct(v: number | null, decimals = 1): string {
  if (v == null) return '—'
  const sign = v > 0 ? '+' : ''
  return `${sign}${(v * 100).toFixed(decimals)}%`
}

function fmtBps(v: number | null): string {
  if (v == null) return '—'
  const sign = v > 0 ? '+' : ''
  return `${sign}${v.toFixed(0)} bps`
}

function fmtAdv(v: number | null): string {
  if (v == null) return '—'
  const cr = v / 1e7
  return `₹${cr.toFixed(0)} cr`
}

function fmtTe(v: number | null): string {
  if (v == null) return '—'
  const bps = v < 1 ? v * 10000 : v
  return `${bps.toFixed(0)} bps`
}

function returnClass(v: number | null): string {
  if (v == null) return 'text-ink-primary'
  return v > 0 ? 'text-signal-pos' : v < 0 ? 'text-signal-neg' : 'text-ink-primary'
}

function Tile({
  label,
  value,
  hint,
  valueClass = 'text-ink-primary',
}: {
  label: string
  value: string
  hint: string
  valueClass?: string
}) {
  return (
    <div className="p-4 border-r border-paper-rule last:border-r-0">
      <div className="font-sans text-[9px] uppercase tracking-[0.18em] text-ink-tertiary font-semibold mb-1.5">
        {label}
      </div>
      <div className={`font-mono text-xl font-medium leading-tight ${valueClass}`}>
        {value}
      </div>
      <div className="font-sans text-[11px] text-ink-tertiary mt-1 leading-snug">
        {hint}
      </div>
    </div>
  )
}

export interface EtfHeroStripProps {
  deepdive: EtfDeepdiveRow
}

export function EtfHeroStrip({ deepdive: d }: EtfHeroStripProps) {
  const action = d.action ?? '—'
  const actionClass =
    action === 'BUY'
      ? 'bg-signal-pos text-paper'
      : action === 'AVOID'
        ? 'bg-signal-neg text-paper'
        : 'bg-signal-warn/20 text-signal-warn border border-signal-warn/40'

  return (
    <div
      className="border border-paper-rule rounded-sm bg-paper-soft overflow-hidden"
      data-testid="etf-hero-strip"
    >
      {/* Header row */}
      <div className="px-4 py-3 flex items-center gap-3 border-b border-paper-rule flex-wrap">
        <div className="font-mono font-semibold text-2xl tracking-wide text-ink-primary">
          {d.ticker}
        </div>
        <span
          className={`font-mono text-[10px] font-bold tracking-wide px-2.5 py-1 rounded-sm ${actionClass}`}
        >
          {action}
        </span>
        {d.etf_name && (
          <span className="font-serif text-base text-ink-secondary">{d.etf_name}</span>
        )}
      </div>

      {/* Meta chips */}
      <div className="px-4 py-2 flex flex-wrap gap-2 border-b border-paper-rule">
        {[
          { label: 'Category', value: d.etf_category ?? '—' },
          { label: 'AMC', value: d.fund_house ?? '—' },
          { label: 'Asset class', value: d.asset_class ?? '—' },
        ].map(({ label, value }) => (
          <span
            key={label}
            className="font-sans text-[10px] uppercase tracking-wide text-ink-tertiary font-semibold px-2 py-1 bg-paper-deep rounded-sm"
          >
            {label} <strong className="text-ink-secondary font-semibold normal-case tracking-normal">{value}</strong>
          </span>
        ))}
      </div>

      {/* 6-tile verdict strip */}
      <div className="grid grid-cols-2 sm:grid-cols-3 xl:grid-cols-6 divide-x divide-y sm:divide-y-0 divide-paper-rule">
        <Tile
          label="12M return"
          value={fmtPct(d.ret_12m)}
          hint="12-month total return"
          valueClass={returnClass(d.ret_12m)}
        />
        <Tile
          label="Tracking error · 60d"
          value={fmtTe(d.te_60d)}
          hint="vs benchmark index · 60-day window"
          valueClass={
            d.te_60d != null && (d.te_60d < 1 ? d.te_60d * 10000 : d.te_60d) < 15
              ? 'text-signal-pos'
              : 'text-signal-warn'
          }
        />
        <Tile
          label="Premium to NAV"
          value={fmtBps(d.premium_bps)}
          hint={
            d.premium_bps != null
              ? Math.abs(d.premium_bps) <= 25
                ? 'NAV-fair · within ±25bps band'
                : 'Outside ±25bps band · AP friction'
              : 'iNAV data pending'
          }
          valueClass={
            d.premium_bps == null
              ? 'text-ink-tertiary'
              : Math.abs(d.premium_bps) > 25
                ? 'text-signal-neg'
                : 'text-ink-primary'
          }
        />
        <Tile
          label="ADV · 20d avg"
          value={fmtAdv(d.adv_20d_inr)}
          hint="Average daily value traded · 20-day window"
          valueClass={
            d.adv_20d_inr != null && d.adv_20d_inr >= 3e7
              ? 'text-signal-pos'
              : 'text-signal-warn'
          }
        />
        <Tile
          label="6M return"
          value={fmtPct(d.ret_6m)}
          hint="6-month total return"
          valueClass={returnClass(d.ret_6m)}
        />
        <Tile
          label="RS state"
          value={d.rs_state ?? '—'}
          hint="Relative strength classification · from rs_pctile_3m band"
          valueClass={
            d.rs_state === 'Leader' || d.rs_state === 'Strong'
              ? 'text-signal-pos'
              : d.rs_state === 'Weak' || d.rs_state === 'Laggard'
                ? 'text-signal-neg'
                : 'text-ink-secondary'
          }
        />
      </div>
    </div>
  )
}

export default EtfHeroStrip
