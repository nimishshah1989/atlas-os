'use client'
import { useState, useRef, useEffect } from 'react'
import { ChevronUp, ChevronDown, AlertTriangle, Info } from 'lucide-react'
import type { SectorDecision } from '@/lib/sectors-decision'
import { getTopPicksAction } from '@/app/sectors/actions'
import type { TopPickRow } from '@/lib/queries/sector-deep-dive'

type Row = {
  sector_name: string
  constituent_count: number
  bottomup_ret_1w: string | null
  bottomup_ret_1m: string | null
  bottomup_ret_3m: string | null
  bottomup_ret_6m: string | null
  bottomup_rs_3m_nifty500: string | null
  rs_momentum: string | null
  participation_50: string | null
  leadership_concentration: string | null
  sector_state: string
  bottomup_momentum_state: string | null
  divergence_flag: boolean
  decision: SectorDecision
  days_in_state?: number
}

type SortKey = 'decision' | 'bottomup_ret_1w' | 'bottomup_ret_1m' | 'bottomup_ret_3m' | 'bottomup_ret_6m' | 'bottomup_rs_3m_nifty500' | 'rs_momentum' | 'participation_50' | 'leadership_concentration' | 'sector_name' | 'days_in_state'

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
  Avoid:       'bg-signal-neg',
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

function ColTip({ text }: { text: string }) {
  const [pos, setPos] = useState<{ x: number; y: number } | null>(null)
  const btnRef = useRef<HTMLButtonElement>(null)
  return (
    <span className="inline-flex items-center">
      <button
        ref={btnRef}
        type="button"
        onMouseEnter={() => {
          const r = btnRef.current?.getBoundingClientRect()
          if (r) setPos({ x: r.left + r.width / 2, y: r.top - 6 })
        }}
        onMouseLeave={() => setPos(null)}
        onFocus={() => {
          const r = btnRef.current?.getBoundingClientRect()
          if (r) setPos({ x: r.left + r.width / 2, y: r.top - 6 })
        }}
        onBlur={() => setPos(null)}
        className="ml-1 text-ink-tertiary/60 hover:text-ink-secondary transition-colors"
        aria-label="Column info"
      >
        <Info className="w-2.5 h-2.5" />
      </button>
      {pos && (
        <span
          role="tooltip"
          className="fixed z-[9999] w-56 px-2.5 py-2 bg-paper border border-paper-rule rounded-sm shadow-md font-sans text-[11px] text-ink-secondary leading-relaxed normal-case tracking-normal font-normal pointer-events-none whitespace-normal -translate-x-1/2 -translate-y-full"
          style={{ left: pos.x, top: pos.y }}
        >
          {text}
        </span>
      )}
    </span>
  )
}

function ConcentrationCell({ value }: { value: string | null }) {
  if (value == null) return <span className="font-mono text-xs text-ink-tertiary">—</span>
  const n = parseFloat(value)
  const pctStr = `${(n * 100).toFixed(0)}%`
  // Higher = worse (narrower leadership)
  const color = n >= 0.6 ? '#B0492C' : n >= 0.4 ? '#B8860B' : '#2F6B43'
  return (
    <div className="flex items-center gap-2">
      <div className="w-12 h-1.5 bg-paper-rule rounded-full overflow-hidden">
        <div className="h-full rounded-full" style={{ width: `${Math.min(100, n * 100)}%`, background: color }} />
      </div>
      <span className="font-mono text-xs tabular-nums" style={{ color }}>{pctStr}</span>
    </div>
  )
}

function TopPicksPopover({
  sectorName,
  visible,
}: {
  sectorName: string
  visible: boolean
}) {
  const [picks, setPicks] = useState<TopPickRow[]>([])
  const [loading, setLoading] = useState(false)
  const [loaded, setLoaded] = useState('')

  useEffect(() => {
    if (!visible || loaded === sectorName) return
    setLoading(true)
    getTopPicksAction(sectorName).then(result => {
      setPicks(result)
      setLoaded(sectorName)
      setLoading(false)
    })
  }, [visible, sectorName, loaded])

  if (!visible) return null

  return (
    <div className="absolute z-20 left-0 top-full mt-1 w-64 bg-paper border border-paper-rule rounded-sm shadow-lg p-3">
      <p className="font-sans text-[10px] text-ink-tertiary uppercase tracking-wider mb-2">
        Top investable picks
      </p>
      {loading ? (
        <div className="space-y-1.5">
          {[1, 2, 3].map(i => (
            <div key={i} className="h-4 bg-paper-rule/30 animate-pulse rounded" />
          ))}
        </div>
      ) : picks.length === 0 ? (
        <p className="font-sans text-xs text-ink-tertiary">No investable stocks in this sector.</p>
      ) : (
        <table className="w-full">
          <tbody>
            {picks.map(p => (
              <tr key={p.symbol}>
                <td className="font-mono text-xs text-ink-primary py-0.5">{p.symbol}</td>
                <td className="font-sans text-[10px] text-ink-tertiary py-0.5 pl-2 truncate max-w-[100px]">
                  {p.company_name}
                </td>
                <td className="font-mono text-[10px] text-ink-secondary py-0.5 pl-2">
                  {p.rs_state ?? '—'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}

export function SectorDecisionTable({ data, onSelect }: { data: Row[]; onSelect: (name: string) => void }) {
  const [sortKey, setSortKey] = useState<SortKey>('decision')
  const [asc, setAsc] = useState(true)
  const [hoveredSector, setHoveredSector] = useState<string | null>(null)
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  function handleEnterHover(name: string) {
    if (debounceRef.current) clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(() => setHoveredSector(name), 300)
  }
  function handleEnterLeave() {
    if (debounceRef.current) clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(() => setHoveredSector(null), 150)
  }

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
    } else if (sortKey === 'days_in_state') {
      const av = a.days_in_state ?? null
      const bv = b.days_in_state ?? null
      if (av == null && bv == null) cmp = 0
      else if (av == null) cmp = 1
      else if (bv == null) cmp = -1
      else cmp = av - bv
    } else {
      const av = a[sortKey] != null ? parseFloat(a[sortKey] as string) : null
      const bv = b[sortKey] != null ? parseFloat(b[sortKey] as string) : null
      if (av == null && bv == null) cmp = 0
      else if (av == null) cmp = 1
      else if (bv == null) cmp = -1
      else cmp = av - bv
    }
    return asc ? cmp : -cmp
  })

  function SortIcon({ k }: { k: SortKey }) {
    if (sortKey !== k) return <ChevronUp className="w-3 h-3 opacity-20" />
    return asc
      ? <ChevronUp className="w-3 h-3 text-teal" />
      : <ChevronDown className="w-3 h-3 text-teal" />
  }

  function Th({ label, k, tip }: { label: string; k: SortKey; tip?: string }) {
    return (
      <th
        className="px-3 py-2 text-left font-sans text-[10px] font-semibold uppercase tracking-wider text-ink-tertiary cursor-pointer hover:text-ink-secondary select-none whitespace-nowrap"
        onClick={() => handleSort(k)}
      >
        <span className="flex items-center gap-0.5">
          {label}
          {tip && <ColTip text={tip} />}
          {' '}<SortIcon k={k} />
        </span>
      </th>
    )
  }

  return (
    <div className="overflow-x-auto border border-paper-rule rounded-sm">
      <table className="w-full border-collapse">
        <thead>
          <tr className="border-b border-paper-rule bg-paper">
            <Th label="Sector"   k="sector_name" />
            <Th label="Decision" k="decision"
              tip="ENTER = strong buy setup (Overweight + improving momentum). ROTATE IN = sector is turning, not yet confirmed. HOLD = stay positioned. WATCH = on radar, not actionable. PASS = avoid. EXIT = close positions — state has broken down." />
            <th className="px-3 py-2 text-left font-sans text-[10px] font-semibold uppercase tracking-wider text-ink-tertiary whitespace-nowrap">
              <span className="flex items-center gap-0.5">
                State
                <ColTip text="Overweight = majority of stocks in this sector are outperforming + breadth is expanding. Neutral = mixed signals. Underweight = broad underperformance. Avoid = severe weakness — capital preservation mode." />
              </span>
            </th>
            <Th label="1W Ret"  k="bottomup_ret_1w" />
            <Th label="1M Ret"  k="bottomup_ret_1m" />
            <Th label="3M Ret"  k="bottomup_ret_3m" />
            <Th label="6M Ret"  k="bottomup_ret_6m" />
            <Th label="RS 3M"   k="bottomup_rs_3m_nifty500"
              tip="3-month relative strength vs Nifty 500 — aggregate of all stocks in the sector. +5% means sector stocks on average outperformed Nifty 500 by 5pp over 3 months. Negative = lagging the index." />
            <Th label="RS Mom"  k="rs_momentum"
              tip="Change in 3-month RS over the last 20 trading days. Positive = RS is rising (sector gaining vs index). Negative = RS is falling. Magnitude reads as decimal points of RS — 0.040 ≈ a 4-percentage-point improvement in relative strength over 20 days." />
            <Th label="Breadth" k="participation_50"
              tip="% of stocks in the sector currently trading ABOVE their 50-day EMA. 100% = every stock is in a medium-term uptrend. 50% = half and half. Below 30% signals broad deterioration — even if the sector index looks fine, most stocks are weak." />
            <Th label="Concen." k="leadership_concentration"
              tip="Share of the sector's positive RS attributable to just the top 1–2 stocks. 5% = leadership is broad (good). 80% = 1 or 2 names are carrying the whole sector (fragile — if they crack, the sector cracks). Green below 40%, amber 40–60%, red above 60%." />
            <Th label="Days"    k="days_in_state"
              tip="Consecutive days the sector has held its current state. Longer streaks suggest a settled regime; recent flips deserve closer inspection." />
            <th className="px-3 py-2 text-left font-sans text-[10px] font-semibold uppercase tracking-wider text-ink-tertiary">
              <span className="flex items-center gap-0.5">
                Momentum
                <ColTip text="Direction of change in the sector's RS over the last few weeks. Improving = RS is rising (stocks gaining vs index). Deteriorating = RS is falling (stocks losing ground vs index). Stable = no meaningful change." />
              </span>
            </th>
            <th className="px-3 py-2 text-center font-sans text-[10px] font-semibold uppercase tracking-wider text-ink-tertiary"
                title="Top-down / bottom-up divergence flag">
              &#9888;
            </th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((row, i) => (
            <tr
              key={row.sector_name}
              className={`border-b border-paper-rule last:border-0 hover:bg-paper-rule/20 transition-colors cursor-pointer ${i % 2 === 0 ? '' : 'bg-paper-rule/5'}`}
              onClick={() => onSelect(row.sector_name)}
            >
              <td className="px-3 py-2.5 font-sans text-xs font-medium text-ink-primary whitespace-nowrap">
                {row.sector_name}
                <span className="ml-1.5 font-sans text-[10px] text-ink-tertiary">({row.constituent_count})</span>
              </td>
              <td className="px-3 py-2.5">
                {row.decision === 'ENTER' ? (
                  <div
                    className="relative inline-block"
                    onMouseEnter={() => handleEnterHover(row.sector_name)}
                    onMouseLeave={handleEnterLeave}
                    onClick={(e) => e.stopPropagation()}
                  >
                    <span className={`inline-flex items-center px-1.5 py-0.5 rounded-[2px] font-sans text-[10px] font-bold uppercase tracking-wide ${DECISION_STYLE[row.decision]}`}>
                      {row.decision}
                    </span>
                    <TopPicksPopover
                      sectorName={row.sector_name}
                      visible={hoveredSector === row.sector_name}
                    />
                  </div>
                ) : (
                  <span className={`inline-flex items-center px-1.5 py-0.5 rounded-[2px] font-sans text-[10px] font-bold uppercase tracking-wide ${DECISION_STYLE[row.decision]}`}>
                    {row.decision}
                  </span>
                )}
              </td>
              <td className="px-3 py-2.5">
                <span className="flex items-center gap-1.5">
                  <span className={`inline-block w-1.5 h-1.5 rounded-full ${STATE_DOT[row.sector_state] ?? 'bg-ink-tertiary'}`} />
                  <span className="font-sans text-xs text-ink-secondary">{row.sector_state}</span>
                </span>
              </td>
              <td className={`px-3 py-2.5 font-mono text-xs tabular-nums ${pctColor(row.bottomup_ret_1w)}`}>
                {pct(row.bottomup_ret_1w)}
              </td>
              <td className={`px-3 py-2.5 font-mono text-xs tabular-nums ${pctColor(row.bottomup_ret_1m)}`}>
                {pct(row.bottomup_ret_1m)}
              </td>
              <td className={`px-3 py-2.5 font-mono text-xs tabular-nums ${pctColor(row.bottomup_ret_3m)}`}>
                {pct(row.bottomup_ret_3m)}
              </td>
              <td className={`px-3 py-2.5 font-mono text-xs tabular-nums ${pctColor(row.bottomup_ret_6m)}`}>
                {pct(row.bottomup_ret_6m)}
              </td>
              <td className={`px-3 py-2.5 font-mono text-xs tabular-nums ${pctColor(row.bottomup_rs_3m_nifty500)}`}>
                {pct(row.bottomup_rs_3m_nifty500)}
              </td>
              <td className="px-3 py-2 text-right font-mono text-xs tabular-nums text-ink-secondary">
                {row.rs_momentum != null
                  ? (parseFloat(row.rs_momentum) >= 0 ? '+' : '') + parseFloat(row.rs_momentum).toFixed(3)
                  : '—'}
              </td>
              <td className="px-3 py-2.5">
                <ParticipationBar value={row.participation_50} />
              </td>
              <td className="px-3 py-2.5">
                <ConcentrationCell value={row.leadership_concentration} />
              </td>
              <td className="px-3 py-2 text-right font-mono text-xs tabular-nums text-ink-tertiary">
                {row.days_in_state != null ? `${row.days_in_state}d` : '—'}
              </td>
              <td className="px-3 py-2.5">
                {row.bottomup_momentum_state === 'Improving' ? (
                  <span className="font-sans text-xs text-signal-pos">&#8593; Improving</span>
                ) : row.bottomup_momentum_state === 'Deteriorating' ? (
                  <span className="font-sans text-xs text-signal-neg">&#8595; Deteriorating</span>
                ) : (
                  <span className="font-sans text-xs text-ink-tertiary">&#8212;</span>
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
