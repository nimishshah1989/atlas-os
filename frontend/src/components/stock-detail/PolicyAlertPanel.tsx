// PolicyAlertPanel — policy as a RAG (Red/Amber/Green) sector-policy ALERT + a
// one-line description, NOT a score (FM 2026-06-26). Pure server component, real
// data only (atlas_foundation.policy_registry). Renders nothing when no policy
// applies to the sector — no empty box, no fabricated "neutral".
import type { PolicyAlert } from '@/lib/queries/policy_alerts'

const SECTION = 'px-8 py-8 border-b border-edge-hair'

// RAG → theme-aware signal tokens (locked v4 palette). Green = tailwind, Amber =
// watch, Red = headwind. Today the registry holds tailwinds, so most are green.
const RAG: Record<PolicyAlert['rag'], { dot: string; text: string; ring: string; label: string }> = {
  green: { dot: 'bg-sig-pos', text: 'text-sig-pos', ring: 'border-sig-pos/30', label: 'Tailwind' },
  amber: { dot: 'bg-sig-warn', text: 'text-sig-warn', ring: 'border-sig-warn/30', label: 'Watch' },
  red:   { dot: 'bg-sig-neg', text: 'text-sig-neg', ring: 'border-sig-neg/30', label: 'Headwind' },
}

export function PolicyAlertPanel({ alerts, sector }: { alerts: PolicyAlert[]; sector: string | null }) {
  if (!alerts || alerts.length === 0) return null
  return (
    <section className={SECTION}>
      <div className="mb-4">
        <p className="font-num text-[9px] uppercase tracking-[0.14em] text-txt-3">Policy</p>
        <h2 className="font-display text-[22px] font-medium tracking-tight text-txt-1">
          Government policy {sector ? <span className="text-txt-2">· {sector}</span> : null}
        </h2>
        <p className="mt-1 max-w-[820px] font-sans text-[12.5px] leading-[1.5] text-txt-3">
          Active policies relevant to this sector — flagged as a Red / Amber / Green signal, not
          scored into the six-lens conviction. The lenses say what the market is doing; policy is
          context for why.
        </p>
      </div>
      <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
        {alerts.map((a) => {
          const rag = RAG[a.rag]
          return (
            <div key={a.policy_id} className={`rounded-tile border ${rag.ring} bg-surface-raised px-4 py-3`}>
              <div className="mb-1 flex items-center gap-2">
                <span className={`inline-block h-2.5 w-2.5 rounded-full ${rag.dot}`} aria-hidden />
                <span className={`font-num text-[10px] font-semibold uppercase tracking-wider ${rag.text}`}>{rag.label}</span>
                <span className="font-num text-[10px] uppercase tracking-wider text-txt-3">· {a.impact} impact</span>
              </div>
              <p className="font-sans text-[14px] font-semibold leading-snug text-txt-1">{a.policy_name}</p>
              <p className="mt-1 font-sans text-[12.5px] leading-[1.5] text-txt-2">{a.description}</p>
            </div>
          )
        })}
      </div>
    </section>
  )
}
