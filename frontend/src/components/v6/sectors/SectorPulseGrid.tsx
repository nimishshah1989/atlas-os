'use client'
// frontend/src/components/v6/sectors/SectorPulseGrid.tsx
//
// Market-pulse relative-return grid — Page 04 Sectors (top of page).
// Colored sector tiles showing each NSE sector index's RELATIVE return vs a
// selectable base index (Nifty 50 / Nifty 500) over a selectable window
// (1d / 1w / 1m / 3m / 6m / 12m).
//
// Mirrors the reference "Key Indices Signal Overview" view on
// marketpulse.jslwealth.in/pulse. Data is index-level (atlas_index_metrics_daily),
// not the bottom-up sector aggregates used by the heatmap below it.
//
// Both toggles are component-local (NOT the shared TenureToggle, which is locked
// to 1m/3m/6m/12m and feeds queries that assume those four windows).

import { useState } from 'react'
import Link from 'next/link'
import type {
  SectorIndexRsPayload,
  SectorIndexRet,
  BaseKey,
  RsWindow,
  WindowRet,
} from '@/lib/queries/v6/sector_index_rs'
import { fmtPct } from '../india-pulse/helpers'

type Props = { data: SectorIndexRsPayload }

const WINDOWS: { key: RsWindow; label: string }[] = [
  { key: '1d', label: '1D' },
  { key: '1w', label: '1W' },
  { key: '1m', label: '1M' },
  { key: '3m', label: '3M' },
  { key: '6m', label: '6M' },
  { key: '12m', label: '12M' },
]

const BASES: { key: BaseKey; label: string }[] = [
  { key: 'NIFTY 50', label: 'Nifty 50' },
  { key: 'NIFTY 500', label: 'Nifty 500' },
]

const WINDOW_FIELD: Record<RsWindow, keyof WindowRet> = {
  '1d': 'ret_1d',
  '1w': 'ret_1w',
  '1m': 'ret_1m',
  '3m': 'ret_3m',
  '6m': 'ret_6m',
  '12m': 'ret_12m',
}

/**
 * Relative return (decimal fraction) of a sector index vs the base index for a
 * window. Returns null when either side is missing.
 * Exported for unit testing.
 */
export function relValue(
  sector: SectorIndexRet,
  base: WindowRet,
  window: RsWindow,
): number | null {
  const field = WINDOW_FIELD[window]
  const s = sector.ret[field]
  const b = base[field]
  if (s == null || b == null) return null
  return s - b
}

// RAG heat tint on the percentage-point spread (val is a decimal fraction).
// Tint opacity steps with magnitude; colour-mix keeps it theme-aware.
function cellStyle(val: number | null): React.CSSProperties {
  if (val == null) return {}
  const pp = val * 100
  const sig = pp >= 0 ? 'var(--color-sig-pos)' : 'var(--color-sig-neg)'
  const a = Math.abs(pp) >= 3.0 ? 55 : Math.abs(pp) >= 1.5 ? 30 : Math.abs(pp) > 0.3 ? 15 : 0
  if (a === 0) return {}
  return { background: `color-mix(in srgb, ${sig} ${a}%, transparent)` }
}

// Null / near-flat tiles get an explicit hairline so they read as cells.
function cellClass(val: number | null): string {
  const pp = val == null ? 0 : val * 100
  return Math.abs(pp) <= 0.3 ? 'border border-edge-hair' : ''
}

function Toggle<T extends string>({
  options, active, onChange, label,
}: {
  options: { key: T; label: string }[]
  active: T
  onChange: (v: T) => void
  label: string
}) {
  return (
    <div className="flex items-center gap-2">
      <span className="text-[10px] uppercase tracking-[0.14em] text-txt-3 font-semibold">{label}</span>
      <div className="flex gap-1">
        {options.map((o) => (
          <button
            key={o.key}
            onClick={() => onChange(o.key)}
            className={`px-2.5 py-0.5 text-[11px] rounded-tile font-medium transition-colors cursor-pointer ${
              active === o.key
                ? 'border border-brand bg-brand-soft text-brand'
                : 'bg-surface-raised border border-edge-rule text-txt-3 hover:border-edge-strong hover:text-txt-2'
            }`}
            aria-pressed={active === o.key}
          >
            {o.label}
          </button>
        ))}
      </div>
    </div>
  )
}

export function SectorPulseGrid({ data }: Props) {
  const [window, setWindow] = useState<RsWindow>('1m')
  const [base, setBase] = useState<BaseKey>('NIFTY 50')

  if (data.sectors.length === 0) {
    return null
  }

  const baseRet = data.bases[base]
  const baseLabel = BASES.find((b) => b.key === base)?.label ?? base

  const rows = data.sectors
    .map((s) => ({ sector: s, val: relValue(s, baseRet, window) }))
    .sort((a, b) => (b.val ?? -Infinity) - (a.val ?? -Infinity))

  const bull = rows.filter((r) => (r.val ?? 0) > 0.003).length
  const bear = rows.filter((r) => (r.val ?? 0) < -0.003).length

  return (
    <section aria-label="Sector relative-return pulse">
      <div className="flex items-baseline justify-between flex-wrap gap-3 mb-3">
        <p className="font-sans text-[12px] text-txt-3">
          Relative to <span className="text-txt-2 font-medium">{baseLabel}</span> · {WINDOWS.find((w) => w.key === window)?.label} window.
        </p>
        <div className="flex items-center gap-5 flex-wrap">
          <Toggle label="Base" options={BASES} active={base} onChange={setBase} />
          <Toggle label="Window" options={WINDOWS} active={window} onChange={setWindow} />
        </div>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-4 md:grid-cols-6 gap-1.5">
        {rows.map(({ sector, val }) => (
          <Link
            key={sector.sector_name}
            href={`/sectors/${encodeURIComponent(sector.sector_name)}`}
            className={`rounded-tile flex flex-col items-center justify-center text-center cursor-pointer hover:brightness-95 hover:ring-2 hover:ring-brand/40 transition-all px-2 py-3 ${cellClass(val)}`}
            style={cellStyle(val)}
            title={`${sector.sector_name} (${sector.nse_index_code}): ${fmtPct(val)} vs ${baseLabel} — open sector`}
          >
            <div className="text-[10px] font-semibold tracking-[0.03em] leading-tight text-txt-2">
              {sector.sector_name}
            </div>
            <div className="font-num text-[13px] font-semibold tabular-nums mt-1 text-txt-1">
              {fmtPct(val)}
            </div>
          </Link>
        ))}
      </div>

      <div className="flex items-center gap-4 mt-3 text-[11px] text-txt-3">
        <span className="flex items-center gap-1.5">
          <span className="inline-block w-2 h-2 rounded-full bg-sig-pos" /> Outperform: {bull}
        </span>
        <span className="flex items-center gap-1.5">
          <span className="inline-block w-2 h-2 rounded-full bg-sig-neg" /> Underperform: {bear}
        </span>
        <span className="ml-2 font-num text-[10px] tabular-nums">−3pp · 0 · +3pp colour scale</span>
      </div>
    </section>
  )
}

export default SectorPulseGrid
