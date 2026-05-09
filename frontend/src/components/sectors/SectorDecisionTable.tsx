'use client'
import { useState } from 'react'
import { ChevronUp, ChevronDown, AlertTriangle } from 'lucide-react'
import type { SectorDecision } from '@/lib/sectors-decision'

type Row = {
  sector_name: string
  constituent_count: number
  bottomup_ret_1m: string | null
  bottomup_ret_3m: string | null
  bottomup_ret_6m: string | null
  bottomup_rs_3m_nifty500: string | null
  participation_50: string | null
  sector_state: string
  bottomup_momentum_state: string | null
  divergence_flag: boolean
  decision: SectorDecision
}

type SortKey = 'decision' | 'bottomup_ret_1m' | 'bottomup_ret_3m' | 'bottomup_rs_3m_nifty500' | 'participation_50' | 'sector_name'

const DECISION_ORDER: Record<SectorDecision, number> = {
  'ENTER':     1,
  'ROTATE IN': 2,
  'WATCH':     3,
  'HOLD':      4,
  'PASS':      5,
  'EXIT':      6,
}

const DECISION_STYLE: Record<SectorDecision, string> = {
  'ENTER':     'bg-signal-pos/10 text-signal-pos',
  'HOLD':      'bg-teal/10 text-teal',
  'ROTATE IN': 'bg-signal-warn/10 text-signal-warn',
  'WATCH':     'bg-ink-tertiary/10 text-ink-secondary',
  'PASS':      'bg-ink-tertiary/10 text-ink-tertiary',
  'EXIT':      'bg-signal-neg/10 text-signal-neg',
}

const STATE_DOT: Record<string, string> = {
  Overweight:  'bg-signal-pos',
  Neutral:     'bg-signal-warn',
  Underweight: 'bg-signal-neg',
}

function pct(v: string | null): string {
  if (v == null) return '—'
  const n = parseFloat(v) * 100
  return `${n >= 0 ? '+' : ''}${n.toFixed(1)}%`
}

function pctColor(v: string | null): string {
  if (v == null) return 'text-ink-tertiary'
  return parseFloat(v) >= 0 ? 'text-signal-pos' : 'text-signal-neg'
}

function ParticipationBar({ value }: { value: string | null }) {
  const n = value != null ? parseFloat(value) : 0
  const pctStr = `${(n * 100).toFixed(0)}%`
  const color = n >= 0.7 ? '#22c55e' : n >= 0.5 ? '#f59e0b' : '#ef4444'
  return (
    <div className="flex items-center gap-2">
      <div className="w-16 h-1.5 bg-paper-rule rounded-full overflow-hidden">
        <div className="h-full rounded-full" style={{ width: `${n * 100}%`, background: color }} />
      </div>
      <span className="font-mono text-xs tabular-nums" style={{ color }}>{pctStr}</span>
    </div>
  )
}

export function SectorDecisionTable({ data }: { data: Row[] }) {
  const [sortKey, setSortKey] = useState<SortKey>('decision')
  const [asc, setAsc] = useState(true)

  function handleSort(key: SortKey) {
    if (sortKey === key) setAsc(a => !a)
    else { setSortKey(key); setAsc(true) }
  }

  const sorted = [...data].sort((a, b) => {
    let cmp = 0
    if (sortKey === 'decision') {
      cmp = DECISION_ORDER[a.decision] - DECISION_ORDER[b.decision]
    } else if (sortKey === 'sector_name') {
      cmp = a.sector_name.localeCompare(b.sector_name)
    } else {
      const av = a[sortKey] != null ? parseFloat(a[sortKey] as string) : -Infinity
      const bv = b[sortKey] != null ? parseFloat(b[sortKey] as string) : -Infinity
      cmp = bv - av
    }
    return asc ? cmp : -cmp
  })

  function SortIcon({ k }: { k: SortKey }) {
    if (sortKey !== k) return <ChevronUp className="w-3 h-3 opacity-20" />
    return asc
      ? <ChevronUp className="w-3 h-3 text-teal" />
      : <ChevronDown className="w-3 h-3 text-teal" />
  }

  function Th({ label, k }: { label: string; k: SortKey }) {
    return (
      <th
        className="px-3 py-2 text-left font-sans text-[10px] font-semibold uppercase tracking-wider text-ink-tertiary cursor-pointer hover:text-ink-secondary select-none whitespace-nowrap"
        onClick={() => handleSort(k)}
      >
        <span className="flex items-center gap-1">{label} <SortIcon k={k} /></span>
      </th>
    )
  }

  return (
    <div className="overflow-x-auto border border-paper-rule rounded-sm">
      <table className="w-full border-collapse">
        <thead>
          <tr className="border-b border-paper-rule bg-paper">
            <Th label="Sector"   k="sector_name" />
            <Th label="Decision" k="decision" />
            <th className="px-3 py-2 text-left font-sans text-[10px] font-semibold uppercase tracking-wider text-ink-tertiary whitespace-nowrap">
              State
            </th>
            <Th label="1M Ret"  k="bottomup_ret_1m" />
            <Th label="3M Ret"  k="bottomup_ret_3m" />
            <Th label="RS 3M"   k="bottomup_rs_3m_nifty500" />
            <Th label="Breadth" k="participation_50" />
            <th className="px-3 py-2 text-left font-sans text-[10px] font-semibold uppercase tracking-wider text-ink-tertiary">
              Momentum
            </th>
            <th className="px-3 py-2 text-center font-sans text-[10px] font-semibold uppercase tracking-wider text-ink-tertiary">
              &#9888;
            </th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((row, i) => (
            <tr
              key={row.sector_name}
              className={`border-b border-paper-rule last:border-0 hover:bg-paper-rule/20 transition-colors ${i % 2 === 0 ? '' : 'bg-paper-rule/5'}`}
            >
              <td className="px-3 py-2.5 font-sans text-xs font-medium text-ink-primary whitespace-nowrap">
                {row.sector_name}
                <span className="ml-1.5 font-sans text-[10px] text-ink-tertiary">({row.constituent_count})</span>
              </td>
              <td className="px-3 py-2.5">
                <span className={`inline-flex items-center px-1.5 py-0.5 rounded-[2px] font-sans text-[10px] font-bold uppercase tracking-wide ${DECISION_STYLE[row.decision]}`}>
                  {row.decision}
                </span>
              </td>
              <td className="px-3 py-2.5">
                <span className="flex items-center gap-1.5">
                  <span className={`inline-block w-1.5 h-1.5 rounded-full ${STATE_DOT[row.sector_state] ?? 'bg-ink-tertiary'}`} />
                  <span className="font-sans text-xs text-ink-secondary">{row.sector_state}</span>
                </span>
              </td>
              <td className={`px-3 py-2.5 font-mono text-xs tabular-nums ${pctColor(row.bottomup_ret_1m)}`}>
                {pct(row.bottomup_ret_1m)}
              </td>
              <td className={`px-3 py-2.5 font-mono text-xs tabular-nums ${pctColor(row.bottomup_ret_3m)}`}>
                {pct(row.bottomup_ret_3m)}
              </td>
              <td className={`px-3 py-2.5 font-mono text-xs tabular-nums ${pctColor(row.bottomup_rs_3m_nifty500)}`}>
                {pct(row.bottomup_rs_3m_nifty500)}
              </td>
              <td className="px-3 py-2.5">
                <ParticipationBar value={row.participation_50} />
              </td>
              <td className="px-3 py-2.5">
                {row.bottomup_momentum_state != null ? (
                  <span className={`font-sans text-xs ${row.bottomup_momentum_state === 'Improving' ? 'text-signal-pos' : 'text-signal-neg'}`}>
                    {row.bottomup_momentum_state === 'Improving' ? '↑ Improving' : '↓ Deteriorating'}
                  </span>
                ) : (
                  <span className="font-sans text-xs text-ink-tertiary">—</span>
                )}
              </td>
              <td className="px-3 py-2.5 text-center">
                {row.divergence_flag && (
                  <span title="Top-down and bottom-up signals diverge">
                    <AlertTriangle className="w-3 h-3 text-signal-warn mx-auto" />
                  </span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
