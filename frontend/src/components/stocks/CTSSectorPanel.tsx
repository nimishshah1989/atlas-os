'use client'
import { useState, useEffect } from 'react'

type SectorPivotRow = {
  sector: string
  ppc_count: number
  npc_count: number
  total_tradeable: number
  pivot_balance: string | null
  stage2_count: number
  stage2_pct: string | null
  avg_ppc_conviction: string | null
  action_alert_count: number
}

type ApiResponse = { rows: SectorPivotRow[]; as_of: string }

type Grade = '+A' | '+B' | '—' | '−B' | '−A'

const GRADE_STYLES: Record<Grade, { badge: string; desc: string }> = {
  '+A': { badge: 'bg-teal text-white',                                         desc: 'Buy · Act now' },
  '+B': { badge: 'bg-teal/10 text-teal border border-teal/40',                desc: 'Buy · Watch' },
  '—':  { badge: 'bg-paper-rule/40 text-ink-tertiary',                        desc: 'Neutral' },
  '−B': { badge: 'bg-amber-500/10 text-amber-500 border border-amber-500/40', desc: 'Sell · Watch' },
  '−A': { badge: 'bg-signal-neg text-white',                                   desc: 'Sell · Act now' },
}

function sectorGrade(row: SectorPivotRow): Grade {
  const pb = row.pivot_balance != null ? parseFloat(row.pivot_balance) : 0
  const npcDominant = row.npc_count > row.ppc_count && row.npc_count > 0
  if (pb <= -0.15 && npcDominant) return '−A'
  if (pb < -0.03)                 return '−B'
  if (row.action_alert_count > 0 && pb >= 0.10) return '+A'
  if (pb > 0.03)                  return '+B'
  return '—'
}

function BalanceBar({ pb }: { pb: string | null }) {
  const v = pb != null ? parseFloat(pb) : 0
  const pct = Math.min(Math.abs(v) * 100, 100)
  const isBull = v >= 0
  return (
    <div className="flex items-center gap-1.5 min-w-[80px]">
      <div className="relative flex-1 h-1.5 bg-paper-rule rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full ${isBull ? 'bg-signal-pos' : 'bg-signal-neg'}`}
          style={{ width: `${Math.max(pct, 3)}%` }}
        />
      </div>
      <span className={`font-mono text-[10px] tabular-nums w-10 text-right ${isBull ? 'text-signal-pos' : v < 0 ? 'text-signal-neg' : 'text-ink-tertiary'}`}>
        {v >= 0 ? '+' : ''}{(v * 100).toFixed(0)}%
      </span>
    </div>
  )
}

function ConvictionBar({ score }: { score: string | null }) {
  const v = score != null ? parseFloat(score) : null
  if (v == null) return <span className="font-mono text-[10px] text-ink-tertiary">—</span>
  const pct = Math.min(v, 100)
  const barCls = v >= 55 ? 'bg-teal' : v >= 40 ? 'bg-amber-500' : 'bg-paper-rule'
  return (
    <div className="flex items-center gap-1.5 min-w-[70px]">
      <div className="relative flex-1 h-1.5 bg-paper-rule rounded-full overflow-hidden">
        <div className={`h-full rounded-full ${barCls}`} style={{ width: `${Math.max(pct, 3)}%` }} />
      </div>
      <span className="font-mono text-[10px] tabular-nums w-6 text-right text-ink-secondary">{Math.round(v)}</span>
    </div>
  )
}

export function CTSSectorPanel() {
  const [data, setData] = useState<SectorPivotRow[] | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [expanded, setExpanded] = useState(true)

  useEffect(() => {
    fetch('/api/cts/sectors')
      .then(r => r.json() as Promise<ApiResponse>)
      .then(d => { setData(d.rows); setLoading(false) })
      .catch(e => { setError(String(e)); setLoading(false) })
  }, [])

  const actionTotal = data?.reduce((s, r) => s + r.action_alert_count, 0) ?? 0

  return (
    <div className="border border-paper-rule rounded-sm">
      <button
        type="button"
        className="w-full flex items-center justify-between px-4 py-2.5 hover:bg-paper-rule/10 transition-colors"
        onClick={() => setExpanded(e => !e)}
      >
        <div className="flex items-center gap-3">
          <span className="font-sans text-xs font-semibold text-ink-primary uppercase tracking-wide">
            CTS Sector Pulse
          </span>
          {actionTotal > 0 && (
            <span className="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded bg-teal/10 text-teal border border-teal/30 font-sans text-[10px] font-bold">
              ⚡ {actionTotal} Action{actionTotal !== 1 ? 's' : ''}
            </span>
          )}
          {loading && (
            <span className="font-sans text-[10px] text-ink-tertiary">Loading…</span>
          )}
        </div>
        <span className="font-mono text-xs text-ink-tertiary">{expanded ? '▲' : '▼'}</span>
      </button>

      {expanded && (
        <div className="border-t border-paper-rule">
          {error ? (
            <p className="px-4 py-3 font-sans text-xs text-signal-neg">{error}</p>
          ) : loading ? (
            <div className="px-4 py-3 space-y-2">
              {[...Array(6)].map((_, i) => (
                <div key={i} className="h-4 bg-paper-rule/40 rounded animate-pulse" />
              ))}
            </div>
          ) : !data || data.length === 0 ? (
            <p className="px-4 py-3 font-sans text-xs text-ink-tertiary">No sector pivot data yet. Run the nightly CTS backfill first.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full border-collapse">
                <thead>
                  <tr className="border-b border-paper-rule bg-paper">
                    <th className="px-3 py-2 font-sans text-[10px] font-semibold uppercase tracking-wider text-ink-tertiary text-left">Sector</th>
                    <th className="px-3 py-2 font-sans text-[10px] font-semibold uppercase tracking-wider text-ink-tertiary text-left" title="+A/+B = buy timing  —  −B/−A = sell timing">Timing</th>
                    <th className="px-3 py-2 font-sans text-[10px] font-semibold uppercase tracking-wider text-ink-tertiary text-right">PPC</th>
                    <th className="px-3 py-2 font-sans text-[10px] font-semibold uppercase tracking-wider text-ink-tertiary text-right">NPC</th>
                    <th className="px-3 py-2 font-sans text-[10px] font-semibold uppercase tracking-wider text-ink-tertiary text-left">Balance</th>
                    <th className="px-3 py-2 font-sans text-[10px] font-semibold uppercase tracking-wider text-ink-tertiary text-right">S2 %</th>
                    <th className="px-3 py-2 font-sans text-[10px] font-semibold uppercase tracking-wider text-ink-tertiary text-left whitespace-nowrap">Avg Conv</th>
                    <th className="px-3 py-2 font-sans text-[10px] font-semibold uppercase tracking-wider text-ink-tertiary text-right whitespace-nowrap">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {data.map((row, i) => {
                    const s2Pct = row.stage2_pct != null ? Math.round(parseFloat(row.stage2_pct) * 100) : null
                    return (
                      <tr key={row.sector} className={`border-b border-paper-rule hover:bg-paper-rule/10 ${i % 2 === 0 ? '' : 'bg-paper-rule/5'}`}>
                        <td className="px-3 py-2 font-sans text-xs text-ink-primary whitespace-nowrap">
                          {row.sector}
                        </td>
                        <td className="px-3 py-2">
                          {(() => {
                            const grade = sectorGrade(row)
                            const gs = GRADE_STYLES[grade]
                            return (
                              <div className="flex items-center gap-1.5">
                                <span className={`inline-flex items-center justify-center w-7 h-5 rounded font-mono text-[10px] font-bold ${gs.badge}`}>
                                  {grade}
                                </span>
                                <span className="font-sans text-[10px] text-ink-tertiary">{gs.desc}</span>
                              </div>
                            )
                          })()}
                        </td>
                        <td className="px-3 py-2 font-mono text-xs text-right text-signal-pos tabular-nums">
                          {row.ppc_count}
                        </td>
                        <td className="px-3 py-2 font-mono text-xs text-right text-signal-neg tabular-nums">
                          {row.npc_count}
                        </td>
                        <td className="px-3 py-2">
                          <BalanceBar pb={row.pivot_balance} />
                        </td>
                        <td className="px-3 py-2 font-mono text-xs text-right text-ink-secondary tabular-nums">
                          {s2Pct != null ? `${s2Pct}%` : '—'}
                        </td>
                        <td className="px-3 py-2">
                          <ConvictionBar score={row.avg_ppc_conviction} />
                        </td>
                        <td className="px-3 py-2 text-right">
                          {row.action_alert_count > 0 ? (
                            <span className="inline-flex items-center gap-0.5 px-1 py-0.5 rounded bg-teal/10 text-teal border border-teal/30 font-sans text-[9px] font-bold">
                              ⚡ {row.action_alert_count}
                            </span>
                          ) : (
                            <span className="font-mono text-[10px] text-ink-tertiary">—</span>
                          )}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
