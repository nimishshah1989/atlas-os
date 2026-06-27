// HoldingsLensRead — "how the score was built" for a holdings-weighted entity (ETF / fund).
// Like a SECTOR (SectorLensRead), an ETF/fund lens is NOT a stock-style sub-component score: it's
// the holdings-WEIGHTED average of each holding's 0–100 lens score. So each lens is CLICKABLE
// (native <details>, server-safe) to reveal HOW that aggregate is built — the weighted average,
// how many holdings lead the lens (top-3 decile, D≥LEAD_DECILE), and the top holdings driving it
// (by weight, ranked among the leaders). Per-holding deciles live in the look-through table below.
// RULE #0: every number traces to a real foundation_staging field (holdings deciles + weights) —
// no synthetic fallback; an absent sub-datum renders as absence. Presentation-only server component.
import { LEAD_DECILE } from '@/lib/queries/v6/stock_lens'

// The minimal shape this read needs from a holding — shared by EtfHolding and FundHolding.
export type LensHolding = {
  symbol: string
  weight: number | null
  d_tech: number | null
  d_fund: number | null
  d_cat: number | null
  d_flow: number | null
  d_val: number | null
}

type DecileKey = 'd_tech' | 'd_fund' | 'd_cat' | 'd_flow' | 'd_val'
type VectorKey = 'v_tech' | 'v_fund' | 'v_cat' | 'v_flow' | 'v_val'

const LENSES: { vkey: VectorKey; dkey: DecileKey; label: string }[] = [
  { vkey: 'v_tech', dkey: 'd_tech', label: 'Technical' },
  { vkey: 'v_fund', dkey: 'd_fund', label: 'Fundamental' },
  { vkey: 'v_cat', dkey: 'd_cat', label: 'Catalyst' },
  { vkey: 'v_flow', dkey: 'd_flow', label: 'Flow' },
  { vkey: 'v_val', dkey: 'd_val', label: 'Valuation' },
]

const barColor = (v: number) => (v >= 60 ? 'bg-sig-pos' : v >= 45 ? 'bg-sig-warn' : 'bg-sig-neg')

type Vector = Partial<Record<VectorKey, number | null>>

export function HoldingsLensRead({
  vector,
  holdings,
  weightLabel = 'weight',
}: {
  vector: Vector
  holdings: LensHolding[]
  weightLabel?: string
}) {
  const n = holdings.length
  const scored = LENSES
    .map(l => ({ ...l, v: vector[l.vkey] ?? null }))
    .filter((l): l is typeof l & { v: number } => l.v != null)

  if (scored.length === 0) return <p className="font-sans text-[13px] italic text-txt-3">No scored holdings.</p>

  return (
    <div className="max-w-[640px]">
      {scored.map(l => {
        const leaders = holdings.filter(h => (h[l.dkey] ?? 0) >= LEAD_DECILE)
        const leadN = leaders.length
        // Top holdings driving the lens — the leaders ranked by holding weight (the real contribution).
        const top = [...leaders].sort((a, b) => (b.weight ?? 0) - (a.weight ?? 0)).slice(0, 5)
        return (
          <details key={l.vkey} className="group border-b border-edge-hair last:border-0">
            <summary className="-mx-2 flex cursor-pointer list-none select-none items-center gap-3 rounded-tile px-2 py-2 hover:bg-surface-raised/50">
              <span className="w-[96px] shrink-0 font-sans text-xs text-txt-2">{l.label}</span>
              <span className="w-[42px] shrink-0 text-right font-num text-xs tabular-nums text-txt-1">{l.v.toFixed(0)}<span className="text-[9px] text-txt-3">/100</span></span>
              <span className="h-[7px] flex-1 overflow-hidden rounded-tile bg-surface-inset">
                <span className={`block h-full rounded-tile ${barColor(l.v)}`} style={{ width: `${Math.min(100, l.v)}%` }} />
              </span>
              <span className="w-[12px] shrink-0 text-right font-num text-[11px] text-txt-3 transition-transform group-open:rotate-90">›</span>
            </summary>
            <div className="pb-3 pl-[96px] pr-2 pt-0.5">
              <p className="mb-1.5 font-num text-[9px] uppercase tracking-[0.14em] text-txt-3">How this score is built</p>
              <div className="grid grid-cols-2 gap-x-6 gap-y-1.5">
                <Row label={`Holdings-weighted average`} value={`${l.v.toFixed(0)} / 100`} />
                <Row label={`Holdings leading (D≥${LEAD_DECILE})`} value={`${leadN}/${n}`} tone={leadN > n / 2 ? 'pos' : undefined} />
              </div>
              {top.length > 0 ? (
                <>
                  <p className="mb-1 mt-2.5 font-num text-[9px] uppercase tracking-[0.14em] text-txt-3">Top leaders by {weightLabel}</p>
                  <div className="space-y-0.5">
                    {top.map(h => (
                      <div key={h.symbol} className="flex items-baseline justify-between gap-2 border-b border-edge-hair/60 py-0.5">
                        <span className="font-num text-[12.5px] font-semibold tabular-nums text-txt-1">{h.symbol}</span>
                        <span className="font-sans text-[11px] text-txt-3">D{h[l.dkey]}</span>
                        <span className="ml-auto font-num text-[12.5px] tabular-nums text-txt-2">{fmtWeight(h.weight)}</span>
                      </div>
                    ))}
                  </div>
                </>
              ) : (
                <p className="mt-2 font-sans text-[11px] italic text-txt-3">No holding leads this lens (D≥{LEAD_DECILE}).</p>
              )}
              <p className="mt-1.5 font-sans text-[11px] italic text-txt-3">Per-holding {l.label.toLowerCase()} deciles: the look-through holdings table below.</p>
            </div>
          </details>
        )
      })}
    </div>
  )
}

// Weight may be a FRACTION (ETF, 0.0617) or a PERCENT (fund, 6.17) — normalise either to a %.
function fmtWeight(w: number | null): string {
  if (w == null) return '—'
  const pct = w <= 1 ? w * 100 : w
  return `${pct.toFixed(2)}%`
}

function Row({ label, value, tone }: { label: string; value: string; tone?: 'pos' }) {
  return (
    <div className="flex items-baseline justify-between gap-2 border-b border-edge-hair/60 py-0.5">
      <span className="font-sans text-[11.5px] text-txt-3">{label}</span>
      <span className={`font-num text-[12.5px] tabular-nums ${tone === 'pos' ? 'text-sig-pos' : 'text-txt-1'}`}>{value}</span>
    </div>
  )
}
