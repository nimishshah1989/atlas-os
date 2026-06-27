// SectorLensRead — "what the sector is saying": the 6-lens vector (sector_lens_daily).
// Each lens is the constituent-average 0–100 score, and is now CLICKABLE (native <details>,
// server-safe) to reveal HOW it's built: how many constituents lead that lens (D≥8), the
// lens breadth, and the cross-stock dispersion — the sector-level "glass box". Per-stock
// detail lives in the 2×2 + constituents table below. Native foundation_staging. Server component.
import type { SectorLensVector, SectorStock } from '@/lib/queries/v6/sector_lens'
import { LEAD_DECILE } from '@/lib/queries/v6/stock_lens'

// lens → the per-stock decile field on SectorStock (policy/catalyst have no stock decile here).
const LENSES: { key: keyof SectorLensVector; label: string; dkey: keyof SectorStock | null; breadthKey: keyof SectorLensVector | null }[] = [
  { key: 'technical', label: 'Technical', dkey: 'd_tech', breadthKey: 'breadth_technical' },
  { key: 'fundamental', label: 'Fundamental', dkey: 'd_fund', breadthKey: 'breadth_fundamental' },
  { key: 'valuation', label: 'Valuation', dkey: 'd_val', breadthKey: null },
  { key: 'catalyst', label: 'Catalyst', dkey: 'd_cat', breadthKey: null },
  { key: 'flow', label: 'Flow', dkey: 'd_flow', breadthKey: 'breadth_flow' },
  { key: 'policy', label: 'Policy', dkey: null, breadthKey: null },
]
const barColor = (v: number) => (v >= 60 ? 'bg-sig-pos' : v >= 45 ? 'bg-sig-warn' : 'bg-sig-neg')
const pct1 = (v: number | null) => (v == null ? '—' : `${(v <= 1 ? v * 100 : v).toFixed(0)}%`)

export function SectorLensRead({ vector, stocks }: { vector: SectorLensVector; stocks: SectorStock[] }) {
  const n = stocks.length
  const leaders = stocks.filter(s => s.lead >= 2).length
  const breadth = n ? (100 * leaders / n) : 0
  const scored = LENSES.map(l => ({ ...l, v: vector[l.key] as number | null })).filter(l => l.v != null) as
    (typeof LENSES[number] & { v: number })[]
  const sorted = [...scored].sort((a, b) => b.v - a.v)
  const strongest = sorted[0], weakest = sorted[sorted.length - 1]

  return (
    <section className="px-8 py-10 border-b border-edge-hair" aria-label="Sector lens read">
      <div className="mb-5">
        <h2 className="font-display text-[28px] font-normal tracking-tight text-txt-1">What the lenses say</h2>
        <p className="font-sans text-[13px] text-txt-3 max-w-[820px] leading-[1.45] mt-1">
          Each lens is the sector&apos;s constituent-average <strong className="text-txt-2">0–100 score</strong>
          (50 = neutral). <strong className="text-txt-2">Click any lens</strong> to see how it&apos;s built — how
          many constituents lead it (top-3 decile, D≥{LEAD_DECILE}), its breadth, and how tightly the stocks agree.
        </p>
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-x-10 gap-y-4">
        <div>
          {scored.map(l => {
            const leadN = l.dkey ? stocks.filter(s => ((s[l.dkey!] as number | null) ?? 0) >= LEAD_DECILE).length : null
            const breadthV = l.breadthKey ? (vector[l.breadthKey] as number | null) : null
            return (
              <details key={l.key} className="group border-b border-edge-hair last:border-0">
                <summary className="flex items-center gap-3 py-2 cursor-pointer list-none select-none -mx-2 px-2 rounded-tile hover:bg-surface-raised/50">
                  <span className="w-[92px] shrink-0 font-sans text-xs text-txt-2">{l.label}</span>
                  <span className="w-[48px] shrink-0 font-num text-xs tabular-nums text-txt-1 text-right">{l.v.toFixed(0)}<span className="text-[9px] text-txt-3">/100</span></span>
                  <span className="flex-1 h-[7px] bg-surface-inset rounded-tile overflow-hidden">
                    <span className={`block h-full rounded-tile ${barColor(l.v)}`} style={{ width: `${Math.min(100, l.v)}%` }} />
                  </span>
                  <span className="w-[12px] shrink-0 text-right font-num text-[11px] text-txt-3 transition-transform group-open:rotate-90">›</span>
                </summary>
                <div className="pb-3 pl-[92px] pr-2">
                  <p className="mb-1.5 font-num text-[9px] uppercase tracking-[0.14em] text-txt-3">How this score is built</p>
                  <div className="grid grid-cols-2 gap-x-6 gap-y-1.5">
                    {leadN != null && (
                      <Row label={`Constituents leading (D≥${LEAD_DECILE})`} value={`${leadN}/${n}`} tone={leadN > n / 2 ? 'pos' : undefined} />
                    )}
                    {breadthV != null && <Row label="Lens breadth (% participating)" value={pct1(breadthV)} />}
                    {vector.dispersion != null && <Row label="Cross-stock dispersion" value={vector.dispersion.toFixed(1)} />}
                    <Row label="Constituent average" value={`${l.v.toFixed(0)} / 100`} />
                  </div>
                  <p className="mt-1.5 font-sans text-[11px] italic text-txt-3">Per-stock {l.label.toLowerCase()} scores: the 2×2 and constituents table below.</p>
                </div>
              </details>
            )
          })}
        </div>
        <div className="flex flex-col justify-center gap-3 font-sans text-[13px] text-txt-2 leading-relaxed">
          <p>
            Strongest on <strong className="text-sig-pos">{strongest?.label}</strong> ({strongest?.v.toFixed(0)});
            weakest on <strong className="text-sig-neg">{weakest?.label}</strong> ({weakest?.v.toFixed(0)}).
          </p>
          <p>
            <strong className="text-txt-1 font-num tabular-nums">{leaders}</strong> of {n} names are multi-factor
            leaders (top-3 decile in ≥2 conviction lenses) — <strong className="text-txt-1 font-num tabular-nums">{breadth.toFixed(0)}%</strong> leadership breadth.
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

function Row({ label, value, tone }: { label: string; value: string; tone?: 'pos' }) {
  return (
    <div className="flex items-baseline justify-between gap-2 border-b border-edge-hair/60 py-0.5">
      <span className="font-sans text-[11.5px] text-txt-3">{label}</span>
      <span className={`font-num text-[12.5px] tabular-nums ${tone === 'pos' ? 'text-sig-pos' : 'text-txt-1'}`}>{value}</span>
    </div>
  )
}
