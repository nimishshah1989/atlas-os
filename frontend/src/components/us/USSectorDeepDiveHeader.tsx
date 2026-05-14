import Link from 'next/link'
import { ChevronRight } from 'lucide-react'
import type { USSectorRow } from '@/lib/queries/us-sectors'

function deriveSectorState(pctile: number): 'Overweight' | 'Neutral' | 'Underweight' | 'Avoid' {
  if (pctile >= 0.60) return 'Overweight'
  if (pctile >= 0.42) return 'Neutral'
  if (pctile >= 0.28) return 'Underweight'
  return 'Avoid'
}

function deriveSectorDecision(rs: number, partRs: number, mom: number): string {
  if (rs >= 0.62 && partRs >= 35 && mom >= 0) return 'ENTER'
  if (rs >= 0.55 || (rs >= 0.48 && mom > 0.03)) return 'WATCH'
  if (rs >= 0.42 && mom >= -0.02) return 'HOLD'
  if (rs >= 0.30) return 'PASS'
  return 'EXIT'
}

const STATE_COLORS = {
  Overweight:  { bg: 'bg-teal/10',   text: 'text-teal',        dot: 'bg-teal' },
  Neutral:     { bg: 'bg-amber-50',  text: 'text-amber-700',   dot: 'bg-amber-500' },
  Underweight: { bg: 'bg-orange-50', text: 'text-orange-700',  dot: 'bg-orange-400' },
  Avoid:       { bg: 'bg-red-50',    text: 'text-red-700',     dot: 'bg-red-500' },
}

const DECISION_COLORS: Record<string, string> = {
  ENTER: 'bg-teal text-white',
  WATCH: 'bg-teal/10 text-teal',
  HOLD:  'bg-paper-rule/40 text-ink-secondary',
  PASS:  'bg-orange-50 text-orange-700',
  EXIT:  'bg-red-50 text-red-700',
}

function fmtPct(v: string | null): string {
  if (v == null) return '—'
  const n = parseFloat(v) * 100
  return isNaN(n) ? '—' : `${n >= 0 ? '+' : ''}${n.toFixed(1)}%`
}

export function USSectorDeepDiveHeader({
  sector,
  sectorName,
}: {
  sector: USSectorRow
  sectorName: string
}) {
  const rsPctile = parseFloat(sector.avg_rs_pctile_3m_vt ?? '0') || 0
  const partRs = parseFloat(sector.participation_rs ?? '0') || 0
  const mom = parseFloat(sector.rs_momentum ?? '0') || 0
  const state = deriveSectorState(rsPctile)
  const decision = deriveSectorDecision(rsPctile, partRs, mom)
  const sc = STATE_COLORS[state]

  return (
    <div className="sticky top-14 bg-paper border-b border-paper-rule z-30">
      <div className="px-6 py-4">
        <nav className="flex items-center gap-1 font-sans text-xs text-ink-tertiary mb-3" aria-label="Breadcrumb">
          <Link href="/us" className="hover:text-ink-secondary transition-colors">US Pulse</Link>
          <ChevronRight className="w-3 h-3" />
          <Link href="/us?tab=Sectors" className="hover:text-ink-secondary transition-colors">Sectors</Link>
          <ChevronRight className="w-3 h-3" />
          <span className="text-ink-secondary">{sectorName}</span>
        </nav>

        <div className="flex items-end justify-between flex-wrap gap-4">
          <div className="flex items-end gap-3 flex-wrap">
            <h1 className="font-serif text-2xl lg:text-3xl font-semibold text-ink-primary leading-none">
              {sectorName}
            </h1>
            <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-sm font-sans text-[11px] font-medium ${sc.bg} ${sc.text}`}>
              <span className={`w-1.5 h-1.5 rounded-full ${sc.dot}`} />
              {state}
            </span>
            <span className={`inline-block px-2 py-0.5 rounded-sm font-sans text-[11px] font-semibold ${DECISION_COLORS[decision] ?? 'bg-paper-rule/20 text-ink-secondary'}`}>
              {decision}
            </span>
          </div>

          <div className="flex items-center gap-5 font-sans text-xs text-ink-tertiary">
            <span>
              RS Pctile: <span className="font-mono font-semibold text-ink-primary">{(rsPctile * 100).toFixed(0)}</span>
            </span>
            <span>
              Participation: <span className="font-mono font-semibold text-ink-primary">{partRs.toFixed(0)}%</span>
            </span>
            <span>
              3M Ret: <span className={`font-mono font-semibold ${parseFloat(sector.avg_ret_3m ?? '0') >= 0 ? 'text-signal-pos' : 'text-signal-neg'}`}>
                {fmtPct(sector.avg_ret_3m)}
              </span>
            </span>
            <span>
              {sector.live_count} stocks
            </span>
            {sector.data_as_of && (
              <span className="text-ink-tertiary/60 text-[10px]">
                Data as of {sector.data_as_of}
              </span>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
