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

// Color scale on percentage-point spread (val is a decimal fraction).
function cellClass(val: number | null): string {
  if (val == null) return 'bg-paper border border-paper-rule'
  const pp = val * 100
  if (pp >= 3.0) return 'bg-[rgba(47,107,67,0.55)]'
  if (pp >= 1.5) return 'bg-[rgba(47,107,67,0.30)]'
  if (pp > 0.3) return 'bg-[rgba(47,107,67,0.15)]'
  if (pp >= -0.3) return 'bg-paper border border-paper-rule'
  if (pp >= -1.5) return 'bg-[rgba(176,73,44,0.15)]'
  if (pp >= -3.0) return 'bg-[rgba(176,73,44,0.30)]'
  return 'bg-[rgba(176,73,44,0.55)]'
}

function textClass(val: number | null): string {
  if (val == null) return 'text-ink-secondary'
  const pp = val * 100
  if (pp >= 3.0 || pp <= -3.0) return 'text-paper'
  return 'text-ink-secondary'
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
      <span className="text-[10px] uppercase tracking-[0.14em] text-ink-tertiary font-semibold">{label}</span>
      <div className="flex gap-1">
        {options.map((o) => (
          <button
            key={o.key}
            onClick={() => onChange(o.key)}
            className={`px-2.5 py-0.5 text-[11px] border rounded-sm font-medium transition-colors cursor-pointer ${
              active === o.key
                ? 'bg-accent text-paper border-accent'
                : 'bg-paper text-ink-tertiary border-paper-rule hover:text-ink-secondary'
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
    <section className="mt-7" aria-label="Sector relative-return pulse">
      <div className="flex items-baseline justify-between flex-wrap gap-3 mb-3">
        <div>
          <h2 className="font-serif text-[22px] font-normal tracking-tight text-ink-primary">
            Sector pulse · relative to {baseLabel}
          </h2>
          <p className="font-sans text-[12px] text-ink-tertiary mt-0.5">
            Each sector index&apos;s return minus {baseLabel} over the selected window. Click a tile to open the sector.
          </p>
        </div>
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
            className={`rounded-sm flex flex-col items-center justify-center text-center cursor-pointer hover:brightness-95 hover:ring-2 hover:ring-accent/40 transition-all px-2 py-3 ${cellClass(val)}`}
            title={`${sector.sector_name} (${sector.nse_index_code}): ${fmtPct(val)} vs ${baseLabel} — open sector`}
          >
            <div className={`text-[10px] font-semibold tracking-[0.03em] leading-tight ${textClass(val)}`}>
              {sector.sector_name}
            </div>
            <div className={`font-mono text-[13px] font-semibold mt-1 ${textClass(val)}`}>
              {fmtPct(val)}
            </div>
          </Link>
        ))}
      </div>

      <div className="flex items-center gap-4 mt-3 text-[11px] text-ink-tertiary">
        <span className="flex items-center gap-1.5">
          <span className="inline-block w-2 h-2 rounded-full bg-signal-pos" /> Outperform: {bull}
        </span>
        <span className="flex items-center gap-1.5">
          <span className="inline-block w-2 h-2 rounded-full bg-signal-neg" /> Underperform: {bear}
        </span>
        <span className="ml-2 font-mono text-[10px]">−3pp · 0 · +3pp colour scale</span>
      </div>
    </section>
  )
}

export default SectorPulseGrid
