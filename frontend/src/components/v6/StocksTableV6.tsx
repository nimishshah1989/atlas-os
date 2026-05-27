// frontend/src/components/v6/StocksTableV6.tsx
//
// v6 stocks table — adds the ConvictionTape column on top of v2 row shape.
// Client component for sort + chip filter interactivity.

'use client'

import { useMemo, useState } from 'react'
import { ChevronUp, ChevronDown } from 'lucide-react'
import { LinkedTicker, LinkedSector } from '@/components/ui/LinkedToken'
import { StateBadge } from '@/components/ui/StateBadge'
import { ConvictionTape } from '@/components/v6/ConvictionTape'
import { RuleCard } from '@/components/v6/RuleCard'
import { ELI5Tooltip } from '@/components/v6/ELI5Tooltip'
import type { ScreenStock, Tier, Tenure, CellRule } from '@/lib/api/v1'

type Props = {
  stocks: ScreenStock[]
  /** Map cell_id → rule list so the segment popover can show the top RuleCard. */
  cellRules?: Map<string, CellRule[]>
}

type Chip = 'all' | 'investable' | 'leader' | 'accel' | 'cell_aligned' | 'three_pos'
type SortKey = 'symbol' | 'tier' | 'sector' | 'ret_1m' | 'ret_3m' | 'rs_pctile_3m' | 'tape'

function pctSigned(v: number | null) {
  if (v == null) return { text: '—', cls: 'text-ink-tertiary' }
  const pct = v * 100
  const sign = pct >= 0 ? '+' : ''
  return {
    text: `${sign}${pct.toFixed(1)}%`,
    cls: pct >= 0 ? 'text-signal-pos' : 'text-signal-neg',
  }
}

function tapeScore(s: ScreenStock): number {
  // Composite: count of POSITIVE segments + 0.5 * sum of IC.
  let posSeg = 0
  let icSum = 0
  for (const tenure of ['1m', '3m', '6m', '12m'] as const) {
    const v = s.conviction_tape[tenure]
    if (v.direction === 'POSITIVE') posSeg += 1
    if (v.direction === 'NEGATIVE') posSeg -= 1
    if (v.ic != null) icSum += v.ic
  }
  return posSeg + icSum * 0.5
}

export function StocksTableV6({ stocks, cellRules }: Props) {
  const [sortKey, setSortKey] = useState<SortKey>('tape')
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc')
  const [chip, setChip] = useState<Chip>('all')
  const [tierFilter, setTierFilter] = useState<Tier | 'all'>('all')
  const [sectorFilter, setSectorFilter] = useState<string>('all')
  const [openRow, setOpenRow] = useState<string | null>(null)
  const [openSegment, setOpenSegment] = useState<Tenure | null>(null)

  const sectors = useMemo(() => {
    const set = new Set<string>()
    stocks.forEach(s => { if (s.sector) set.add(s.sector) })
    return ['all', ...Array.from(set).sort()]
  }, [stocks])

  const filtered = useMemo(() => {
    let rows = stocks.slice()
    if (tierFilter !== 'all') rows = rows.filter(s => s.tier === tierFilter)
    if (sectorFilter !== 'all') rows = rows.filter(s => s.sector === sectorFilter)
    switch (chip) {
      case 'investable':
        rows = rows.filter(s => s.is_investable)
        break
      case 'leader':
        rows = rows.filter(s => s.rs_state === 'Leader' || s.rs_state === 'Strong')
        break
      case 'accel':
        rows = rows.filter(s => {
          const t = s.conviction_tape['1m']
          return t.direction === 'POSITIVE' && (t.ic ?? 0) >= 0.02
        })
        break
      case 'cell_aligned':
        rows = rows.filter(s => {
          let n = 0
          for (const t of ['1m', '3m', '6m', '12m'] as const) {
            if (s.conviction_tape[t].direction === 'POSITIVE') n += 1
          }
          return n >= 2
        })
        break
      case 'three_pos':
        rows = rows.filter(s => {
          let n = 0
          for (const t of ['1m', '3m', '6m', '12m'] as const) {
            if (s.conviction_tape[t].direction === 'POSITIVE') n += 1
          }
          return n >= 3
        })
        break
    }
    rows.sort((a, b) => {
      const dir = sortDir === 'asc' ? 1 : -1
      const aNull = (v: number | string | null | undefined) => v == null || v === ''
      if (sortKey === 'tape') {
        return (tapeScore(a) - tapeScore(b)) * dir
      }
      const va = (a as unknown as Record<string, unknown>)[sortKey]
      const vb = (b as unknown as Record<string, unknown>)[sortKey]
      if (aNull(va as never)) return 1
      if (aNull(vb as never)) return -1
      if (typeof va === 'number' && typeof vb === 'number') return (va - vb) * dir
      return String(va).localeCompare(String(vb)) * dir
    })
    return rows
  }, [stocks, chip, tierFilter, sectorFilter, sortKey, sortDir])

  function toggleSort(k: SortKey) {
    if (k === sortKey) setSortDir(d => d === 'asc' ? 'desc' : 'asc')
    else { setSortKey(k); setSortDir('desc') }
  }

  function sortIcon(k: SortKey) {
    if (k !== sortKey) return null
    return sortDir === 'asc' ? <ChevronUp size={10} className="text-teal" /> : <ChevronDown size={10} className="text-teal" />
  }

  function onSegmentClick(iid: string, tenure: Tenure) {
    if (openRow === iid && openSegment === tenure) {
      setOpenRow(null); setOpenSegment(null)
    } else {
      setOpenRow(iid); setOpenSegment(tenure)
    }
  }

  function ruleFor(stock: ScreenStock, tenure: Tenure): CellRule | null {
    if (!cellRules) return null
    const verdict = stock.conviction_tape[tenure]
    if (verdict.direction === 'NEUTRAL') return null
    const cellId = `${stock.tier}-${tenure}-${verdict.direction}`
    const rules = cellRules.get(cellId)
    if (!rules || rules.length === 0) return null
    return rules[0]
  }

  return (
    <div>
      {/* Filter / chip strip */}
      <div className="px-6 py-3 border-b border-paper-rule flex items-center gap-3 flex-wrap">
        <select
          value={tierFilter}
          onChange={e => setTierFilter(e.target.value as Tier | 'all')}
          className="font-sans text-xs border border-paper-rule rounded-[2px] bg-paper px-2 py-1"
        >
          <option value="all">All tiers</option>
          <option value="Large">Large</option>
          <option value="Mid">Mid</option>
          <option value="Small">Small</option>
        </select>
        <select
          value={sectorFilter}
          onChange={e => setSectorFilter(e.target.value)}
          className="font-sans text-xs border border-paper-rule rounded-[2px] bg-paper px-2 py-1"
        >
          {sectors.map(s => <option key={s} value={s}>{s === 'all' ? 'All sectors' : s}</option>)}
        </select>
        <div className="flex items-center gap-1">
          {(['all', 'investable', 'leader', 'accel', 'cell_aligned', 'three_pos'] as Chip[]).map(c => (
            <button
              key={c}
              onClick={() => setChip(c)}
              className={`px-2.5 py-1 rounded-[2px] font-sans text-[11px] border transition-colors ${
                chip === c
                  ? 'bg-teal/10 text-teal border-teal/30'
                  : 'bg-paper text-ink-secondary border-paper-rule hover:bg-paper-rule/20'
              }`}
            >
              {c === 'all' ? 'All' :
               c === 'investable' ? 'Investable' :
               c === 'leader' ? 'Leader' :
               c === 'accel' ? 'Accel' :
               c === 'cell_aligned' ? 'Cell-aligned' :
               '≥3 POS'}
            </button>
          ))}
        </div>
        <span className="font-sans text-[11px] text-ink-tertiary ml-auto">
          {filtered.length} of {stocks.length}
        </span>
      </div>

      <div className="overflow-x-auto border-b border-paper-rule">
        <table className="w-full border-collapse">
          <thead>
            <tr className="border-b border-paper-rule bg-paper">
              <Th onClick={() => toggleSort('symbol')} icon={sortIcon('symbol')} align="left">Symbol</Th>
              <Th onClick={() => toggleSort('tier')} icon={sortIcon('tier')} align="left">Tier</Th>
              <Th onClick={() => toggleSort('sector')} icon={sortIcon('sector')} align="left">Sector</Th>
              <Th onClick={() => toggleSort('tape')} icon={sortIcon('tape')} align="left">
                <ELI5Tooltip term="ic">Conviction</ELI5Tooltip>
              </Th>
              <Th align="left">RS</Th>
              <Th onClick={() => toggleSort('ret_1m')} icon={sortIcon('ret_1m')} align="right">1M</Th>
              <Th onClick={() => toggleSort('ret_3m')} icon={sortIcon('ret_3m')} align="right">3M</Th>
              <Th onClick={() => toggleSort('rs_pctile_3m')} icon={sortIcon('rs_pctile_3m')} align="right">RS%</Th>
              <Th align="left">Actions</Th>
            </tr>
          </thead>
          <tbody>
            {filtered.length === 0 ? (
              <tr>
                <td colSpan={9} className="px-6 py-10 text-center">
                  <p className="font-sans text-sm text-ink-secondary mb-2">
                    No stocks match the current filter.
                  </p>
                  <button
                    onClick={() => { setChip('all'); setTierFilter('all'); setSectorFilter('all') }}
                    className="font-sans text-xs text-teal hover:underline"
                  >
                    Clear filters
                  </button>
                </td>
              </tr>
            ) : filtered.map((s, i) => {
              const r1 = pctSigned(s.ret_1m)
              const r3 = pctSigned(s.ret_3m)
              const expanded = openRow === s.iid
              const segRule = expanded && openSegment ? ruleFor(s, openSegment) : null
              return (
                <>
                  <tr
                    key={s.iid}
                    className={`border-b border-paper-rule hover:bg-paper-rule/20 transition-colors ${i % 2 === 0 ? '' : 'bg-paper-rule/5'}`}
                  >
                    <td className="px-3 py-2.5 whitespace-nowrap">
                      <LinkedTicker symbol={s.symbol} />
                    </td>
                    <td className="px-3 py-2.5 whitespace-nowrap">
                      <span className="font-sans text-[11px] text-ink-secondary">{s.tier}</span>
                    </td>
                    <td className="px-3 py-2.5 whitespace-nowrap">
                      <LinkedSector sector={s.sector} />
                    </td>
                    <td className="px-3 py-2.5 whitespace-nowrap">
                      <ConvictionTape
                        tape={s.conviction_tape}
                        compact
                        selected={expanded ? openSegment : null}
                        onSegmentClick={t => onSegmentClick(s.iid, t)}
                      />
                    </td>
                    <td className="px-3 py-2.5 whitespace-nowrap">
                      {s.rs_state ? <StateBadge state={s.rs_state} size="sm" /> : <span className="font-mono text-xs text-ink-tertiary">—</span>}
                    </td>
                    <td className={`px-3 py-2.5 font-mono text-xs tabular-nums text-right whitespace-nowrap ${r1.cls}`}>{r1.text}</td>
                    <td className={`px-3 py-2.5 font-mono text-xs tabular-nums text-right whitespace-nowrap ${r3.cls}`}>{r3.text}</td>
                    <td className="px-3 py-2.5 font-mono text-xs tabular-nums text-right whitespace-nowrap text-ink-secondary">
                      {s.rs_pctile_3m != null ? Math.round(s.rs_pctile_3m * 100) : '—'}
                    </td>
                    <td className="px-3 py-2.5 whitespace-nowrap">
                      <a
                        href={`/v6/stocks/${encodeURIComponent(s.iid)}`}
                        className="font-sans text-[11px] text-teal hover:underline"
                      >
                        Deep dive →
                      </a>
                    </td>
                  </tr>
                  {expanded && (
                    <tr key={`${s.iid}-drill`} className="bg-paper-rule/10 border-b border-paper-rule">
                      <td colSpan={9} className="px-6 py-4">
                        {segRule ? (
                          <div className="max-w-3xl">
                            <div className="font-sans text-[10px] uppercase tracking-wider text-ink-tertiary mb-2">
                              {openSegment} {s.conviction_tape[openSegment!].direction} — top rule
                            </div>
                            <RuleCard rule={segRule} cellId={`${s.tier}-${openSegment}-${s.conviction_tape[openSegment!].direction}`} />
                          </div>
                        ) : (
                          <p className="font-sans text-sm text-ink-secondary">
                            No rule detail loaded for this segment yet. The backend will return
                            the firing rule per (tier, tenure, direction) on the live endpoint.
                          </p>
                        )}
                      </td>
                    </tr>
                  )}
                </>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function Th({ children, onClick, icon, align }: { children: React.ReactNode; onClick?: () => void; icon?: React.ReactNode; align: 'left' | 'right' }) {
  const justify = align === 'right' ? 'justify-end' : 'justify-start'
  return (
    <th
      onClick={onClick}
      className={`px-3 py-2 font-sans text-[10px] font-semibold uppercase tracking-wider text-ink-tertiary ${onClick ? 'cursor-pointer hover:text-ink-secondary' : ''} select-none whitespace-nowrap text-${align}`}
    >
      <span className={`inline-flex items-center gap-1 ${justify}`}>
        {children}
        {icon}
      </span>
    </th>
  )
}
