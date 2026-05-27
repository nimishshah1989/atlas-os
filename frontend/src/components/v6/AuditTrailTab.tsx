// frontend/src/components/v6/AuditTrailTab.tsx
//
// AuditTrailTab — placeholder for E.1 (shipped in v6.0 final).
// When E.1 lands, replace this file with the full audit trail implementation.
//
// Currently renders a read-only audit summary using the AuditTrail data from
// the getAuditTrail query (C.4). Full interactive section navigation
// (predicate table, provenance log, drift event log) lands in E.1.

'use client'

import type { AuditTrail } from '@/lib/queries/v6/audit_trail'

export interface AuditTrailTabProps {
  auditTrail: AuditTrail | null
}

function SectionCard({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="border border-paper-rule rounded-[2px] p-4">
      <h3 className="font-sans text-[10px] uppercase tracking-wider text-ink-tertiary mb-3">
        {title}
      </h3>
      {children}
    </div>
  )
}

export function AuditTrailTab({ auditTrail }: AuditTrailTabProps) {
  if (!auditTrail) {
    return (
      <div className="px-6 py-8 text-center font-sans text-sm text-ink-tertiary">
        No audit trail data available for this stock.
      </div>
    )
  }

  const { universe, cell_matches, signal_call, predicates_met, regime, provenance } = auditTrail

  return (
    <div className="px-6 py-6 flex flex-col gap-6">
      {/* Section 1 — Universe membership */}
      <SectionCard title="1. Universe membership">
        <div className="flex flex-wrap gap-4 text-sm font-sans">
          <div>
            <span className="text-ink-tertiary">In universe: </span>
            <span className={universe.in_universe ? 'text-signal-pos font-medium' : 'text-signal-neg font-medium'}>
              {universe.in_universe ? 'Yes' : 'No'}
            </span>
          </div>
          <div>
            <span className="text-ink-tertiary">Tier: </span>
            <span className="text-ink-primary">{universe.cap_tier}</span>
          </div>
          <div>
            <span className="text-ink-tertiary">Sector: </span>
            <span className="text-ink-primary">{universe.sector}</span>
          </div>
          <div>
            <span className="text-ink-tertiary">Universe total: </span>
            <span className="font-mono text-ink-primary">{universe.universe_total}</span>
          </div>
          <div>
            <span className="text-ink-tertiary">As of: </span>
            <span className="font-mono text-ink-primary">{universe.as_of_date}</span>
          </div>
        </div>
      </SectionCard>

      {/* Section 2 — Cell matches */}
      <SectionCard title="2. Cell matches today">
        {cell_matches.length === 0 ? (
          <p className="font-sans text-sm text-ink-tertiary">No cells triggered today.</p>
        ) : (
          <div className="flex flex-col gap-2">
            {cell_matches.map((cm) => (
              <div key={cm.cell_id} className="flex items-center gap-3 text-sm font-sans">
                <span
                  className={[
                    'inline-flex px-2 py-0.5 rounded-[2px] text-[10px] font-semibold uppercase',
                    cm.action === 'POSITIVE'
                      ? 'bg-signal-pos/20 text-signal-pos'
                      : 'bg-signal-neg/20 text-signal-neg',
                  ].join(' ')}
                >
                  {cm.action}
                </span>
                <span className="text-ink-primary">{cm.cell_name}</span>
                <span className="text-ink-tertiary text-[11px]">
                  IC: {(parseFloat(cm.confidence_unconditional) * 100).toFixed(2)}%
                </span>
              </div>
            ))}
          </div>
        )}
      </SectionCard>

      {/* Section 3 — Signal call */}
      <SectionCard title="3. Active signal call">
        {signal_call == null ? (
          <p className="font-sans text-sm text-ink-tertiary">No active signal call for this stock.</p>
        ) : (
          <div className="flex flex-wrap gap-4 text-sm font-sans">
            <div>
              <span className="text-ink-tertiary">Entry date: </span>
              <span className="font-mono text-ink-primary">{signal_call.entry_date}</span>
            </div>
            {signal_call.predicted_excess && (
              <div>
                <span className="text-ink-tertiary">Predicted excess: </span>
                <span className="font-mono text-signal-pos">
                  +{(parseFloat(signal_call.predicted_excess) * 100).toFixed(2)}%
                </span>
              </div>
            )}
          </div>
        )}
      </SectionCard>

      {/* Section 4 — Predicates met */}
      {predicates_met.length > 0 && (
        <SectionCard title="4. Predicates met">
          <div className="flex flex-col gap-2">
            {predicates_met.map((p, i) => (
              <div key={i} className="flex items-start gap-3 text-[12px] font-sans">
                <span
                  className={p.satisfied ? 'text-signal-pos mt-0.5 shrink-0' : 'text-signal-neg mt-0.5 shrink-0'}
                >
                  {p.satisfied ? '✓' : '✗'}
                </span>
                <div>
                  <span className="font-mono text-ink-secondary">{p.predicate_text}</span>
                  <span className="ml-2 text-ink-tertiary">= {p.actual_value}</span>
                  <p className="text-[11px] text-ink-tertiary mt-0.5">{p.translation}</p>
                </div>
              </div>
            ))}
          </div>
        </SectionCard>
      )}

      {/* Section 5 — Regime context */}
      {regime && (
        <SectionCard title="5. Regime context">
          <div className="flex flex-wrap gap-4 text-sm font-sans">
            <div>
              <span className="text-ink-tertiary">State: </span>
              <span className="text-ink-primary font-medium">{regime.state}</span>
            </div>
            <div>
              <span className="text-ink-tertiary">Deployment: </span>
              <span className="font-mono text-ink-primary">{regime.deployment_multiplier}x</span>
            </div>
            <div>
              <span className="text-ink-tertiary">Days in regime: </span>
              <span className="font-mono text-ink-primary">{regime.days_in_regime}</span>
            </div>
            <div>
              <span className="text-ink-tertiary">Cell active in regime: </span>
              <span className={regime.cell_active_in_regime ? 'text-signal-pos' : 'text-signal-warn'}>
                {regime.cell_active_in_regime ? 'Yes' : 'No'}
              </span>
            </div>
          </div>
        </SectionCard>
      )}

      {/* Section 7 — Provenance */}
      {provenance.length > 0 && (
        <SectionCard title="7. Provenance log">
          <div className="flex flex-col gap-1">
            {provenance.map((p, i) => (
              <div key={i} className="text-[11px] font-mono text-ink-tertiary flex gap-3">
                <span>{p.computed_at}</span>
                <span>{p.table_name}</span>
                <span>{p.source}</span>
              </div>
            ))}
          </div>
        </SectionCard>
      )}

      <p className="font-sans text-[11px] text-ink-tertiary italic">
        Full interactive audit trail with predicate deep-dive and ensemble cross-rule check
        coming in v6.0 final (Task E.1).
      </p>
    </div>
  )
}

export default AuditTrailTab
