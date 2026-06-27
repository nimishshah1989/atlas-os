// SectorLensRead — "what the sector is saying": the 6-lens vector (sector_lens_daily) as
// bars + the strongest/weakest lens + leadership-breadth (share of the sector's stocks that
// are multi-factor leaders). Native foundation_staging. Server component.
import type { SectorLensVector } from '@/lib/queries/v6/sector_lens'
import type { SectorStock } from '@/lib/queries/v6/sector_lens'

const LENSES: { key: keyof SectorLensVector; label: string }[] = [
  { key: 'technical', label: 'Technical' },
  { key: 'fundamental', label: 'Fundamental' },
  { key: 'valuation', label: 'Valuation' },
  { key: 'catalyst', label: 'Catalyst' },
  { key: 'flow', label: 'Flow' },
  { key: 'policy', label: 'Policy' },
]
const barColor = (v: number) => (v >= 60 ? 'bg-sig-pos' : v >= 45 ? 'bg-sig-warn' : 'bg-sig-neg')

export function SectorLensRead({ vector, stocks }: { vector: SectorLensVector; stocks: SectorStock[] }) {
  const scored = LENSES.map(l => ({ ...l, v: vector[l.key] as number | null })).filter(l => l.v != null) as { key: string; label: string; v: number }[]
  const sorted = [...scored].sort((a, b) => b.v - a.v)
  const strongest = sorted[0], weakest = sorted[sorted.length - 1]
  const leaders = stocks.filter(s => s.lead >= 2).length
  const breadth = stocks.length ? (100 * leaders / stocks.length) : 0

  return (
    <section className="px-8 py-10 border-b border-edge-hair" aria-label="Sector lens read">
      <div className="mb-5">
        <h2 className="font-display text-[28px] font-normal tracking-tight text-txt-1">What the lenses say</h2>
        <p className="font-sans text-[13px] text-txt-3 max-w-[760px] leading-[1.45] mt-1">
          Each lens is the sector&apos;s average <strong className="text-txt-2">0–100 score</strong> across its constituents
          (50 = neutral, higher = stronger) — so &ldquo;Technical 60&rdquo; means the sector&apos;s stocks average a 60/100 technical
          score. The bar fills to that score. Per-stock breakdowns are in the constituents table below.
        </p>
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-x-10 gap-y-2">
        <div className="space-y-2">
          {scored.map(l => (
            <div key={l.key} className="flex items-center gap-3">
              <span className="w-[92px] shrink-0 font-sans text-xs text-txt-2">{l.label}</span>
              <span className="w-[48px] shrink-0 font-num text-xs tabular-nums text-txt-1 text-right">{l.v.toFixed(0)}<span className="text-[9px] text-txt-3">/100</span></span>
              <span className="flex-1 h-[7px] bg-surface-inset rounded-tile overflow-hidden">
                <span className={`block h-full rounded-tile ${barColor(l.v)}`} style={{ width: `${Math.min(100, l.v)}%` }} />
              </span>
            </div>
          ))}
        </div>
        <div className="flex flex-col justify-center gap-3 font-sans text-[13px] text-txt-2 leading-relaxed">
          <p>
            Strongest on <strong className="text-sig-pos">{strongest?.label}</strong> ({strongest?.v.toFixed(0)});
            weakest on <strong className="text-sig-neg">{weakest?.label}</strong> ({weakest?.v.toFixed(0)}).
          </p>
          <p>
            <strong className="text-txt-1 font-num tabular-nums">{leaders}</strong> of {stocks.length} names are multi-factor
            leaders (top-decile in ≥2 conviction lenses) — <strong className="text-txt-1 font-num tabular-nums">{breadth.toFixed(0)}%</strong> leadership breadth.
          </p>
          {vector.dispersion != null && (
            <p className="text-txt-3 text-xs">
              Dispersion {vector.dispersion.toFixed(1)} · {vector.n_constituents} constituents scored.
            </p>
          )}
        </div>
      </div>
    </section>
  )
}
