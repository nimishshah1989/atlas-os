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
const barColor = (v: number) => (v >= 60 ? 'bg-signal-pos' : v >= 45 ? 'bg-signal-warn' : 'bg-signal-neg')

export function SectorLensRead({ vector, stocks }: { vector: SectorLensVector; stocks: SectorStock[] }) {
  const scored = LENSES.map(l => ({ ...l, v: vector[l.key] as number | null })).filter(l => l.v != null) as { key: string; label: string; v: number }[]
  const sorted = [...scored].sort((a, b) => b.v - a.v)
  const strongest = sorted[0], weakest = sorted[sorted.length - 1]
  const leaders = stocks.filter(s => s.lead >= 2).length
  const breadth = stocks.length ? (100 * leaders / stocks.length) : 0

  return (
    <section className="px-8 py-10 border-b border-paper-rule" aria-label="Sector lens read">
      <div className="mb-5">
        <h2 className="font-serif text-[28px] font-normal tracking-tight text-ink-primary">What the lenses say</h2>
        <p className="font-sans text-[13px] text-ink-tertiary max-w-[760px] leading-[1.45] mt-1">
          The sector's six-lens vector (average across constituents) and how concentrated the leadership is.
        </p>
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-x-10 gap-y-2">
        <div className="space-y-2">
          {scored.map(l => (
            <div key={l.key} className="flex items-center gap-3">
              <span className="w-[92px] shrink-0 font-sans text-xs text-ink-secondary">{l.label}</span>
              <span className="w-[34px] shrink-0 font-mono text-xs tabular-nums text-ink-primary text-right">{l.v.toFixed(0)}</span>
              <span className="flex-1 h-[7px] bg-paper-deep rounded-[2px] overflow-hidden">
                <span className={`block h-full rounded-[2px] ${barColor(l.v)}`} style={{ width: `${Math.min(100, l.v)}%` }} />
              </span>
            </div>
          ))}
        </div>
        <div className="flex flex-col justify-center gap-3 font-sans text-[13px] text-ink-secondary leading-relaxed">
          <p>
            Strongest on <strong className="text-signal-pos">{strongest?.label}</strong> ({strongest?.v.toFixed(0)});
            weakest on <strong className="text-signal-neg">{weakest?.label}</strong> ({weakest?.v.toFixed(0)}).
          </p>
          <p>
            <strong className="text-ink-primary font-mono">{leaders}</strong> of {stocks.length} names are multi-factor
            leaders (top-decile in ≥2 conviction lenses) — <strong className="text-ink-primary font-mono">{breadth.toFixed(0)}%</strong> leadership breadth.
          </p>
          {vector.dispersion != null && (
            <p className="text-ink-tertiary text-xs">
              Dispersion {vector.dispersion.toFixed(1)} · {vector.n_constituents} constituents scored.
            </p>
          )}
        </div>
      </div>
    </section>
  )
}
