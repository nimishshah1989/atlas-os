// StockLensCardV4 — the centerpiece of the v4 stock detail page. The 6 lenses as rows,
// each = decile (within cap cohort) + raw score + a bar, expanding (server-safe <details>)
// to its sub-components (label + value bars) + an evidence line. Co-primary header:
// Strength (avg conviction decile) + Leadership badge (# of 4 conviction lenses top-decile).
// Native foundation_staging via getStockDecile(). Server component.
// Template look/feel: SectorLensRead.tsx.
import type { StockDecile } from '@/lib/queries/v6/stock_lens'

const CAP_LABEL: Record<string, string> = { large: 'Large-cap', mid: 'Mid-cap', small: 'Small-cap', micro: 'Micro-cap' }

// Decile → color. Top-decile (8-10) green, mid (5-7) amber, low (1-4) red.
function decileColor(d: number | null): string {
  if (d == null) return 'bg-paper-rule'
  if (d >= 8) return 'bg-signal-pos'
  if (d >= 5) return 'bg-signal-warn'
  return 'bg-signal-neg'
}
function decileTextColor(d: number | null): string {
  if (d == null) return 'text-ink-tertiary'
  if (d >= 8) return 'text-signal-pos'
  if (d >= 5) return 'text-signal-warn'
  return 'text-signal-neg'
}
// Raw lens score (0-100) bar color, matching SectorLensRead.
function scoreColor(v: number): string {
  return v >= 60 ? 'bg-signal-pos' : v >= 45 ? 'bg-signal-warn' : 'bg-signal-neg'
}

// Pull the human-readable evidence strings out of the journal `evidence` JSONB for a lens.
// The shape varies by pipeline; we defensively read common containers and render whatever
// strings we find. No synthetic fallback — if nothing real is present we say so.
function evidenceFor(evidence: unknown, lensKey: string): string[] {
  if (!evidence || typeof evidence !== 'object') return []
  const e = evidence as Record<string, unknown>
  const out: string[] = []
  const collect = (val: unknown) => {
    if (typeof val === 'string') { if (val.trim()) out.push(val.trim()); return }
    if (Array.isArray(val)) { for (const v of val) collect(v); return }
    if (val && typeof val === 'object') {
      const o = val as Record<string, unknown>
      // common {label|text|reason|detail|driver} record shapes
      for (const k of ['label', 'text', 'reason', 'detail', 'driver', 'note', 'summary']) {
        if (typeof o[k] === 'string' && (o[k] as string).trim()) out.push((o[k] as string).trim())
      }
    }
  }
  // try lens-keyed sub-object first, then a few generic containers
  collect(e[lensKey])
  for (const k of ['drivers', 'reasons', 'notes', 'highlights']) {
    const c = e[k]
    if (c && typeof c === 'object' && !Array.isArray(c)) collect((c as Record<string, unknown>)[lensKey])
  }
  // de-dup, cap at 4 lines
  return Array.from(new Set(out)).slice(0, 4)
}

function LensRow({ lens, evidence }: { lens: StockDecile['lens'][number]; evidence: unknown }) {
  const decile = lens.decile
  const score = lens.score
  const subs = lens.subs.filter(s => s.v != null) as { label: string; v: number }[]
  const ev = evidenceFor(evidence, lens.key)

  return (
    <details className="group border-b border-paper-rule last:border-0">
      <summary className="flex items-center gap-3 py-3 cursor-pointer select-none list-none hover:bg-paper-deep/40 -mx-2 px-2 rounded-[2px]">
        {/* lens name */}
        <span className="w-[104px] shrink-0 font-sans text-[13px] text-ink-secondary">{lens.label}</span>
        {/* decile chip */}
        <span className={`w-[58px] shrink-0 font-mono text-[11px] tabular-nums text-right ${decileTextColor(decile)}`}>
          {decile != null ? `D${decile}` : '—'}
        </span>
        {/* raw score */}
        <span className="w-[34px] shrink-0 font-mono text-[12px] tabular-nums text-ink-primary text-right">
          {score != null ? score.toFixed(0) : '—'}
        </span>
        {/* decile bar (within cohort) */}
        <span className="flex-1 h-[7px] bg-paper-deep rounded-[2px] overflow-hidden" aria-hidden="true">
          {decile != null && (
            <span className={`block h-full rounded-[2px] ${decileColor(decile)}`} style={{ width: `${decile * 10}%` }} />
          )}
        </span>
        {/* expand affordance */}
        <span className="w-[14px] shrink-0 font-mono text-[11px] text-ink-tertiary text-right transition-transform group-open:rotate-90">›</span>
      </summary>

      {/* drill-down: sub-components + evidence */}
      <div className="pb-4 pl-[104px] pr-2 space-y-3">
        {subs.length > 0 ? (
          <div className="space-y-1.5">
            {subs.map(s => (
              <div key={s.label} className="flex items-center gap-3">
                <span className="w-[132px] shrink-0 font-sans text-[11px] text-ink-tertiary">{s.label}</span>
                <span className="w-[30px] shrink-0 font-mono text-[11px] tabular-nums text-ink-secondary text-right">{s.v.toFixed(0)}</span>
                <span className="flex-1 h-[5px] bg-paper-deep rounded-[2px] overflow-hidden">
                  <span className={`block h-full rounded-[2px] ${scoreColor(s.v)}`} style={{ width: `${Math.min(100, Math.max(0, s.v))}%` }} />
                </span>
              </div>
            ))}
          </div>
        ) : (
          <p className="font-sans text-[11px] text-ink-tertiary italic">No sub-component scores recorded for this lens.</p>
        )}
        {ev.length > 0 && (
          <div className="border-l-2 border-teal/40 pl-3">
            <p className="font-mono text-[9px] uppercase tracking-wider text-teal mb-1">Evidence</p>
            {ev.map((line, i) => (
              <p key={i} className="font-sans text-[12px] text-ink-secondary leading-[1.45]">{line}</p>
            ))}
          </div>
        )}
      </div>
    </details>
  )
}

export function StockLensCardV4({ decile }: { decile: StockDecile }) {
  const { lens, lead, strength, cap, evidence } = decile
  const capLabel = CAP_LABEL[cap] ?? cap

  return (
    <section className="px-8 py-9 border-b border-paper-rule" aria-label="Six-lens read">
      {/* Co-primary header: Strength + Leadership */}
      <div className="flex items-start justify-between gap-6 flex-wrap mb-5">
        <div>
          <h2 className="font-serif text-[26px] font-normal tracking-tight text-ink-primary">What the six lenses say</h2>
          <p className="font-sans text-[13px] text-ink-tertiary max-w-[760px] leading-[1.45] mt-1">
            Each lens scored as a <strong className="text-ink-secondary">decile within the {capLabel} cohort</strong> (D10 = top 10%)
            alongside its raw 0–100 score. Expand a lens for its sub-components and the evidence behind it.
          </p>
        </div>
        <div className="flex items-stretch gap-3 shrink-0">
          <div className="bg-paper-deep border border-paper-rule rounded-[2px] px-4 py-3 text-center min-w-[112px]">
            <div className="font-mono text-[9px] uppercase tracking-wider text-ink-tertiary mb-1">Strength</div>
            <div className={`font-mono text-[26px] leading-none tabular-nums ${decileTextColor(strength != null ? Math.round(strength) : null)}`}>
              {strength != null ? strength.toFixed(1) : '—'}
            </div>
            <div className="font-sans text-[10px] text-ink-tertiary mt-1">avg conviction decile</div>
          </div>
          <div className="bg-paper-deep border border-paper-rule rounded-[2px] px-4 py-3 text-center min-w-[112px]">
            <div className="font-mono text-[9px] uppercase tracking-wider text-ink-tertiary mb-1">Leadership</div>
            <div className={`font-mono text-[26px] leading-none tabular-nums ${lead >= 2 ? 'text-signal-pos' : lead === 1 ? 'text-signal-warn' : 'text-ink-tertiary'}`}>
              {lead}/4
            </div>
            <div className="font-sans text-[10px] text-ink-tertiary mt-1">lenses top-decile</div>
          </div>
        </div>
      </div>

      {/* Column legend */}
      <div className="flex items-center gap-3 pb-2 border-b border-paper-rule">
        <span className="w-[104px] shrink-0 font-mono text-[9px] uppercase tracking-wider text-ink-tertiary">Lens</span>
        <span className="w-[58px] shrink-0 font-mono text-[9px] uppercase tracking-wider text-ink-tertiary text-right">Decile</span>
        <span className="w-[34px] shrink-0 font-mono text-[9px] uppercase tracking-wider text-ink-tertiary text-right">Raw</span>
        <span className="flex-1 font-mono text-[9px] uppercase tracking-wider text-ink-tertiary">Within cohort</span>
        <span className="w-[14px] shrink-0" />
      </div>

      {/* The 6 lens rows */}
      <div>
        {lens.map(l => (
          <LensRow key={l.key} lens={l} evidence={evidence} />
        ))}
      </div>
    </section>
  )
}
