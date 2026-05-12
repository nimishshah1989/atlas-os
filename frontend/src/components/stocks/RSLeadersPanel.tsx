import Link from 'next/link'
import { TrendingUp, ArrowUpRight, ArrowDownRight } from 'lucide-react'
import type { RSLeaderRow, BreakoutCandidateRow } from '@/lib/queries/leaders'
import { pct, pctColor, RSPctileBar, RSStateChip, MomentumChip } from '@/lib/stock-formatters'
import { SectorBadge } from './SectorBadge'

function StateChangeArrow({ newState }: { newState: string | null }) {
  const positive = newState === 'Leader' || newState === 'Strong'
  return positive ? (
    <ArrowUpRight className="w-3 h-3 text-signal-pos inline" />
  ) : (
    <ArrowDownRight className="w-3 h-3 text-signal-neg inline" />
  )
}

function LeadersTable({ leaders }: { leaders: RSLeaderRow[] }) {
  if (leaders.length === 0) {
    return (
      <p className="font-sans text-xs text-ink-tertiary py-3">
        No RS Leaders or Strong stocks in the current universe.
      </p>
    )
  }
  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse">
        <thead>
          <tr className="border-b border-paper-rule">
            <th className="pb-1.5 w-6 text-left font-sans text-[10px] font-semibold uppercase tracking-wider text-ink-tertiary">#</th>
            <th className="pb-1.5 text-left font-sans text-[10px] font-semibold uppercase tracking-wider text-ink-tertiary">Symbol</th>
            <th className="pb-1.5 text-left font-sans text-[10px] font-semibold uppercase tracking-wider text-ink-tertiary hidden sm:table-cell">Sector</th>
            <th className="pb-1.5 text-left font-sans text-[10px] font-semibold uppercase tracking-wider text-ink-tertiary">RS State</th>
            <th className="pb-1.5 text-left font-sans text-[10px] font-semibold uppercase tracking-wider text-ink-tertiary hidden md:table-cell">Momentum</th>
            <th className="pb-1.5 text-right font-sans text-[10px] font-semibold uppercase tracking-wider text-ink-tertiary">RS Pctile</th>
            <th className="pb-1.5 text-right font-sans text-[10px] font-semibold uppercase tracking-wider text-ink-tertiary hidden lg:table-cell">6M Ret</th>
          </tr>
        </thead>
        <tbody>
          {leaders.map((r, i) => (
            <tr key={r.instrument_id} className="border-b border-paper-rule last:border-0 hover:bg-paper-rule/10">
              <td className="py-1.5 font-mono text-xs text-ink-tertiary tabular-nums">{i + 1}</td>
              <td className="py-1.5 pr-3">
                <Link href={`/stocks/${encodeURIComponent(r.symbol)}`} className="hover:opacity-80">
                  <div className="font-sans text-xs font-semibold text-ink-primary">{r.symbol}</div>
                  <div className="font-sans text-[10px] text-ink-tertiary truncate max-w-[140px]">{r.company_name}</div>
                </Link>
              </td>
              <td className="py-1.5 pr-3 hidden sm:table-cell">
                <SectorBadge sector={r.sector ?? ''} />
              </td>
              <td className="py-1.5 pr-3">
                <RSStateChip value={r.rs_state} />
              </td>
              <td className="py-1.5 pr-3 hidden md:table-cell">
                <MomentumChip value={r.momentum_state} />
              </td>
              <td className="py-1.5 text-right">
                <RSPctileBar value={r.rs_pctile_3m} />
              </td>
              <td className={`py-1.5 text-right font-mono text-xs tabular-nums hidden lg:table-cell ${pctColor(r.ret_6m)}`}>
                {pct(r.ret_6m)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function BreakoutsTable({ candidates, label, positive }: { candidates: BreakoutCandidateRow[]; label: string; positive: boolean }) {
  if (candidates.length === 0) return null
  return (
    <div>
      <div className="flex items-center gap-1.5 mb-2">
        <StateChangeArrow newState={positive ? 'Leader' : 'Weak'} />
        <span className={`font-sans text-[11px] font-semibold uppercase tracking-wider ${positive ? 'text-signal-pos' : 'text-signal-neg'}`}>
          {label}
        </span>
        <span className="font-sans text-[11px] text-ink-tertiary">({candidates.length})</span>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full border-collapse">
          <thead>
            <tr className="border-b border-paper-rule">
              <th className="pb-1.5 text-left font-sans text-[10px] font-semibold uppercase tracking-wider text-ink-tertiary">Symbol</th>
              <th className="pb-1.5 text-left font-sans text-[10px] font-semibold uppercase tracking-wider text-ink-tertiary hidden sm:table-cell">Sector</th>
              <th className="pb-1.5 text-left font-sans text-[10px] font-semibold uppercase tracking-wider text-ink-tertiary">Transition</th>
              <th className="pb-1.5 text-right font-sans text-[10px] font-semibold uppercase tracking-wider text-ink-tertiary">RS Pctile</th>
            </tr>
          </thead>
          <tbody>
            {candidates.map((r) => (
              <tr key={r.instrument_id} className="border-b border-paper-rule last:border-0 hover:bg-paper-rule/10">
                <td className="py-1.5 pr-3">
                  <Link href={`/stocks/${encodeURIComponent(r.symbol)}`} className="hover:opacity-80">
                    <div className="font-sans text-xs font-semibold text-ink-primary">{r.symbol}</div>
                    <div className="font-sans text-[10px] text-ink-tertiary truncate max-w-[140px]">{r.company_name}</div>
                  </Link>
                </td>
                <td className="py-1.5 pr-3 hidden sm:table-cell">
                  <SectorBadge sector={r.sector ?? ''} />
                </td>
                <td className="py-1.5 pr-3">
                  <span className="font-mono text-[10px] text-ink-tertiary">{r.prior_rs_state ?? '—'}</span>
                  <span className="font-mono text-[10px] text-ink-tertiary mx-1">→</span>
                  <RSStateChip value={r.new_rs_state} />
                </td>
                <td className="py-1.5 text-right">
                  <RSPctileBar value={r.rs_pctile_3m} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

interface RSLeadersPanelProps {
  leaders: RSLeaderRow[]
  breakouts: BreakoutCandidateRow[]
  deterioration: BreakoutCandidateRow[]
}

export function RSLeadersPanel({ leaders, breakouts, deterioration }: RSLeadersPanelProps) {
  const asOf = leaders[0]?.date
    ? new Date(leaders[0].date).toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' })
    : null

  return (
    <div className="space-y-4">
      {/* RS Leaders table */}
      <div className="border border-paper-rule rounded-sm">
        <div className="px-4 py-3 border-b border-paper-rule flex items-center gap-2">
          <TrendingUp className="w-3.5 h-3.5 text-teal" />
          <span className="font-sans text-xs font-semibold text-ink-primary uppercase tracking-wide">
            RS Leaders &amp; Strong
          </span>
          <span className="font-sans text-[11px] text-ink-tertiary">
            ranked by 3M RS Pctile
          </span>
          {leaders.length > 0 && (
            <span className="ml-auto font-sans text-[11px] text-ink-tertiary">
              {leaders.length} stocks
              {asOf && ` · as of ${asOf}`}
            </span>
          )}
        </div>
        <div className="px-4 py-3">
          <LeadersTable leaders={leaders} />
        </div>
      </div>

      {/* State transitions */}
      {(breakouts.length > 0 || deterioration.length > 0) && (
        <div className="border border-paper-rule rounded-sm">
          <div className="px-4 py-3 border-b border-paper-rule">
            <span className="font-sans text-xs font-semibold text-ink-primary uppercase tracking-wide">
              State Transitions Today
            </span>
          </div>
          <div className="px-4 py-3 space-y-4">
            {breakouts.length > 0 && (
              <BreakoutsTable candidates={breakouts} label="Entering Leader/Strong" positive={true} />
            )}
            {deterioration.length > 0 && (
              <BreakoutsTable candidates={deterioration} label="Exiting Leader/Strong" positive={false} />
            )}
          </div>
        </div>
      )}
    </div>
  )
}
