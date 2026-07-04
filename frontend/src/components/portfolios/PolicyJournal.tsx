'use client'
// PolicyJournal — the learning log of a system-generated portfolio. Every weekly
// walk-forward cycle writes an 'evaluation' (all candidates + verdict) and, on a
// promotion, a 'change'. This renders each entry with its train/validation windows,
// the champion baseline, and the adopted policy — the glass-box audit of what the
// expert agent decided and why. Everything is stored evidence, nothing computed here.
import { useState } from 'react'
import type { PolicyJournalEntry } from '@/lib/queries/portfolios'

const policyLabel = (p: Record<string, unknown> | null | undefined): string => {
  if (!p) return '—'
  const parts = [`EMA ${p.fast}/${p.slow}`]
  if (p.confirm_200) parts.push('>200')
  if (p.rs_min != null) parts.push(`RS≥${(Number(p.rs_min) * 100).toFixed(0)}%`)
  if (p.min_composite != null) parts.push(`comp≥${p.min_composite}`)
  if (p.regime_gate) parts.push('regime-gated')
  return parts.join(' · ')
}

type Finalist = { params: Record<string, unknown>; val?: { excess?: number; port_maxdd_pct?: number; bench_maxdd_pct?: number } }

function EntryRow({ e }: { e: PolicyJournalEntry }) {
  const [open, setOpen] = useState(false)
  const ev = e.evidence as {
    windows?: { train?: string[]; val?: string[] }
    champion?: { val?: { excess?: number } }
    candidates_scored?: number
    finalists?: Finalist[]
  }
  const win = ev.windows
  const isChange = e.kind === 'change'
  return (
    <div className="border-b border-edge-hair py-2.5">
      <button onClick={() => setOpen((o) => !o)} className="flex w-full items-center gap-2 text-left">
        <span className={`shrink-0 rounded-tile border px-2 py-0.5 font-sans text-[10px] font-semibold uppercase tracking-wider ${
          isChange ? 'border-sig-pos/30 bg-sig-pos/10 text-sig-pos' : 'border-edge-rule bg-surface-raised text-txt-3'
        }`}>
          {isChange ? 'Policy change' : 'Evaluation'}
        </span>
        <span className="font-num text-[11px] tabular-nums text-txt-3">{e.ts.slice(0, 16).replace('T', ' ')}</span>
        <span className="flex-1 truncate font-sans text-[12px] text-txt-2">
          {isChange ? (
            <>{policyLabel(e.oldParams)} <span className="text-txt-3">→</span> <strong className="text-txt-1">{policyLabel(e.newParams)}</strong></>
          ) : (
            <>Scored {ev.candidates_scored ?? 0} candidates · champion held</>
          )}
        </span>
        <span className="shrink-0 font-num text-[10px] text-txt-3">{open ? '▾' : '▸'}</span>
      </button>
      {open && (
        <div className="mt-2 space-y-1.5 pl-2 font-sans text-[11.5px] text-txt-2">
          {win && (
            <p className="text-txt-3">
              Train {win.train?.[0]} → {win.train?.[1]} · validated out-of-sample {win.val?.[0]} → {win.val?.[1]}
            </p>
          )}
          {ev.champion?.val?.excess != null && (
            <p>Champion validation excess vs NIFTY 500: <strong className={ev.champion.val.excess >= 0 ? 'text-sig-pos' : 'text-sig-neg'}>{ev.champion.val.excess >= 0 ? '+' : ''}{ev.champion.val.excess.toFixed(1)}pp</strong></p>
          )}
          {ev.finalists && ev.finalists.length > 0 && (
            <div className="overflow-x-auto">
              <table className="min-w-[420px]">
                <thead>
                  <tr className="text-txt-3">
                    <th className="py-1 pr-3 text-left font-num text-[9px] uppercase tracking-wider">Candidate</th>
                    <th className="py-1 pr-3 text-right font-num text-[9px] uppercase tracking-wider">Val excess</th>
                    <th className="py-1 text-right font-num text-[9px] uppercase tracking-wider">MaxDD vs N500</th>
                  </tr>
                </thead>
                <tbody>
                  {ev.finalists.map((f, i) => (
                    <tr key={i} className="border-t border-edge-hair/50">
                      <td className="py-1 pr-3 font-num text-[11px] text-txt-1">{policyLabel(f.params)}</td>
                      <td className={`py-1 pr-3 text-right font-num text-[11px] tabular-nums ${(f.val?.excess ?? 0) >= 0 ? 'text-sig-pos' : 'text-sig-neg'}`}>
                        {f.val?.excess != null ? `${f.val.excess >= 0 ? '+' : ''}${f.val.excess.toFixed(1)}pp` : '—'}
                      </td>
                      <td className="py-1 text-right font-num text-[11px] tabular-nums text-txt-3">
                        {f.val?.port_maxdd_pct != null ? `${f.val.port_maxdd_pct.toFixed(0)}% / ${f.val.bench_maxdd_pct?.toFixed(0)}%` : '—'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

export function PolicyJournal({ entries }: { entries: PolicyJournalEntry[] }) {
  if (entries.length === 0)
    return <p className="font-sans text-[13px] italic text-txt-3">No policy cycles yet — the weekly walk-forward run writes here.</p>
  return <div>{entries.map((e, i) => <EntryRow key={i} e={e} />)}</div>
}
