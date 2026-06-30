// frontend/src/components/v6/SectorLadder.tsx
//
// 30-row ranked ladder. Columns: rank · Δ-arrow · sector · state · breadth bar
// · vol regime · RS% · 1M · 3M · click→/sectors/[name].
// Density follows atlas-v6-design-language.md §8 table contract.

import Link from 'next/link'
import { TrendingUp, TrendingDown, Minus } from 'lucide-react'
import { StateBadge } from '@/components/ui/StateBadge'
import { LinkedSector } from '@/components/ui/LinkedToken'
import type { ScreenSector } from '@/lib/api/v1'

type Props = {
  sectors: ScreenSector[]
}

function changeArrow(change: number) {
  if (change > 0) return <TrendingUp size={12} strokeWidth={1.5} className="text-signal-pos" aria-label="up" />
  if (change < 0) return <TrendingDown size={12} strokeWidth={1.5} className="text-signal-neg" aria-label="down" />
  return <Minus size={12} strokeWidth={1.5} className="text-ink-tertiary" aria-label="flat" />
}

function pctSigned(v: number | null): { text: string; cls: string } {
  if (v == null || !Number.isFinite(v)) return { text: '—', cls: 'text-ink-tertiary' }
  const pct = v * 100
  const sign = pct >= 0 ? '+' : ''
  return {
    text: `${sign}${pct.toFixed(1)}%`,
    cls: pct >= 0 ? 'text-signal-pos' : 'text-signal-neg',
  }
}

function BreadthBar({ value }: { value: number | null }) {
  if (value == null) return <span className="font-mono text-xs text-ink-tertiary">—</span>
  const pct = Math.max(0, Math.min(1, value))
  const fillColor = pct >= 0.55 ? 'bg-signal-pos' : pct >= 0.35 ? 'bg-teal' : pct >= 0.20 ? 'bg-signal-warn' : 'bg-signal-neg'
  return (
    <span className="inline-flex items-center gap-2 w-full">
      <span className="relative inline-block h-1.5 w-16 bg-paper-rule/40 rounded-[1px] overflow-hidden">
        <span
          className={`absolute top-0 left-0 h-full ${fillColor}`}
          style={{ width: `${pct * 100}%` }}
        />
      </span>
      <span className="font-mono text-[11px] tabular-nums text-ink-secondary">{Math.round(pct * 100)}%</span>
    </span>
  )
}

function VolPill({ regime }: { regime: string }) {
  const cls =
    regime === 'Low' ? 'text-signal-pos bg-signal-pos/10 border-signal-pos/20' :
    regime === 'Normal' ? 'text-ink-secondary bg-paper-rule/20 border-paper-rule' :
    regime === 'Elevated' ? 'text-signal-warn bg-signal-warn/10 border-signal-warn/20' :
    regime === 'High' ? 'text-signal-neg bg-signal-neg/10 border-signal-neg/20' :
    'text-ink-tertiary'
  return (
    <span className={`inline-flex items-center font-sans font-medium border rounded-[2px] tabular-nums text-[10px] px-1.5 py-0.5 ${cls}`}>
      {regime}
    </span>
  )
}

export function SectorLadder({ sectors }: Props) {
  return (
    <div className="overflow-x-auto border border-paper-rule rounded-[2px]">
      <table className="tbl-centered w-full border-collapse">
        <thead>
          <tr className="border-b border-paper-rule bg-paper">
            <th className="px-3 py-2 font-sans text-[10px] font-semibold uppercase tracking-wider text-ink-tertiary text-right">#</th>
            <th className="px-3 py-2 font-sans text-[10px] font-semibold uppercase tracking-wider text-ink-tertiary text-center">Δ</th>
            <th className="px-3 py-2 font-sans text-[10px] font-semibold uppercase tracking-wider text-ink-tertiary text-left">Sector</th>
            <th className="px-3 py-2 font-sans text-[10px] font-semibold uppercase tracking-wider text-ink-tertiary text-left">State</th>
            <th className="px-3 py-2 font-sans text-[10px] font-semibold uppercase tracking-wider text-ink-tertiary text-left">Breadth</th>
            <th className="px-3 py-2 font-sans text-[10px] font-semibold uppercase tracking-wider text-ink-tertiary text-left">Vol</th>
            <th className="px-3 py-2 font-sans text-[10px] font-semibold uppercase tracking-wider text-ink-tertiary text-right">RS %</th>
            <th className="px-3 py-2 font-sans text-[10px] font-semibold uppercase tracking-wider text-ink-tertiary text-right">1M</th>
            <th className="px-3 py-2 font-sans text-[10px] font-semibold uppercase tracking-wider text-ink-tertiary text-right">3M</th>
            <th className="px-3 py-2 font-sans text-[10px] font-semibold uppercase tracking-wider text-ink-tertiary text-right">RRG</th>
          </tr>
        </thead>
        <tbody>
          {sectors.map((s, i) => {
            const r1 = pctSigned(s.ret_1m)
            const r3 = pctSigned(s.ret_3m)
            return (
              <tr
                key={s.sector_iid}
                className={`border-b border-paper-rule hover:bg-paper-rule/20 transition-colors ${i % 2 === 0 ? '' : 'bg-paper-rule/5'}`}
              >
                <td className="px-3 py-2.5 font-mono text-xs tabular-nums text-ink-secondary text-right whitespace-nowrap">{s.rank}</td>
                <td className="px-3 py-2.5 text-center whitespace-nowrap">{changeArrow(s.rank_change)}</td>
                <td className="px-3 py-2.5 whitespace-nowrap">
                  <LinkedSector sector={s.sector_name} />
                </td>
                <td className="px-3 py-2.5 whitespace-nowrap">
                  <StateBadge state={s.sector_state} size="sm" />
                </td>
                <td className="px-3 py-2.5 whitespace-nowrap">
                  <Link href={`/stocks?sector=${encodeURIComponent(s.sector_name)}`} className="hover:opacity-80">
                    <BreadthBar value={s.breadth_pct_stage_2} />
                  </Link>
                </td>
                <td className="px-3 py-2.5 whitespace-nowrap">
                  <VolPill regime={s.vol_regime} />
                </td>
                <td className="px-3 py-2.5 font-mono text-xs tabular-nums text-ink-primary text-right whitespace-nowrap">
                  {s.rs_pct_cross_sector != null ? Math.round(s.rs_pct_cross_sector * 100) : '—'}
                </td>
                <td className={`px-3 py-2.5 font-mono text-xs tabular-nums text-right whitespace-nowrap ${r1.cls}`}>
                  {r1.text}
                </td>
                <td className={`px-3 py-2.5 font-mono text-xs tabular-nums text-right whitespace-nowrap ${r3.cls}`}>
                  {r3.text}
                </td>
                <td className="px-3 py-2.5 font-sans text-[11px] text-ink-secondary text-right whitespace-nowrap">
                  {s.rrg_quadrant ?? '—'}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
