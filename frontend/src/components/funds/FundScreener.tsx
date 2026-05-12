// allow-large: FundScreener — 16 column data table with sort, col-toggle, lens bars, vol, and gates
'use client'
import { useState, useMemo } from 'react'
import Link from 'next/link'
import { ChevronUp, ChevronDown } from 'lucide-react'
import type { FundRow } from '@/lib/queries/funds'
import type { Period } from '@/lib/url-params'
import type { FilterChip } from '@/components/funds/FundPageClient'
import { pct, pctColor, RSPctileBar } from '@/lib/stock-formatters'
import {
  NavStateChip,
  CompositionStateChip,
  HoldingsStateChip,
  RecommendationChip,
  formatWeeksInState,
} from '@/lib/fund-formatters'
import { LensBar } from '@/components/ui/LensBar'
import { ColumnToggle, useColumnVisibility, type ColumnDef } from '@/components/ui/ColumnToggle'
import { buildSortKey } from '@/lib/screener-utils'

type Props = {
  funds: FundRow[]
  period: Period
  activeFilter: FilterChip
  onFilterChange: (f: FilterChip) => void
}

const ALL_COLS: ColumnDef[] = [
  { key: 'amc',             label: 'AMC',             defaultVisible: true },
  { key: 'category',        label: 'Category',        defaultVisible: true },
  { key: 'nav_state',       label: 'NAV State',       defaultVisible: true },
  { key: 'composition',     label: 'Comp State',      defaultVisible: true },
  { key: 'holdings',        label: 'Holdings State',  defaultVisible: true },
  { key: 'recommendation',  label: 'Recommendation',  defaultVisible: true },
  { key: 'ret',             label: 'Return',          defaultVisible: true },
  { key: 'rs_pctile',       label: 'RS Pctile',       defaultVisible: true },
  { key: 'rs_category',     label: 'RS Category',     defaultVisible: true },
  { key: 'vol',             label: 'Vol (63D)',        defaultVisible: false },
  { key: 'gates',           label: 'Gates',           defaultVisible: true },
  { key: 'comp_bar',        label: 'Comp Bar',        defaultVisible: true },
  { key: 'holdings_bar',    label: 'Holdings Bar',    defaultVisible: true },
  { key: 'weeks_in_state',  label: 'In State',         defaultVisible: true },
  { key: 'drawdown',        label: '1Y Ret',          defaultVisible: true },
  { key: 'max_drawdown',    label: 'Max DD (1Y)',      defaultVisible: false },
]

const COL_STORAGE_KEY = 'atlas-column-prefs-funds'

const RET_KEY: Record<Period, keyof FundRow>    = { '1M': 'ret_1m',         '3M': 'ret_3m',         '6M': 'ret_6m',         '1Y': 'ret_12m' }
const PCTILE_KEY: Record<Period, keyof FundRow> = { '1M': 'rs_pctile_1m',   '3M': 'rs_pctile_3m',   '6M': 'rs_pctile_6m',   '1Y': 'rs_pctile_6m' }
const RSCAT_KEY: Record<Period, keyof FundRow>  = { '1M': 'rs_1m_category', '3M': 'rs_3m_category', '6M': 'rs_6m_category', '1Y': 'rs_6m_category' }

type SortCol =
  | 'scheme_name' | 'amc' | 'category'
  | 'nav_state' | 'composition' | 'holdings' | 'recommendation'
  | 'ret' | 'rs_pctile' | 'rs_category'
  | 'vol' | 'weeks_in_state' | 'drawdown' | 'max_drawdown'

// 4 coloured dots: Perf · Sectors · Stocks · Market
function GateDots({ f }: { f: FundRow }) {
  const gates = [f.performance_gate, f.sectors_gate, f.stocks_gate, f.market_gate]
  const labels = ['Perf', 'Sectors', 'Stocks', 'Market']
  return (
    <span className="flex gap-0.5">
      {gates.map((g, i) => (
        <span
          key={labels[i]}
          title={`${labels[i]}: ${g === true ? 'Pass' : g === false ? 'Fail' : 'N/A'}`}
          className={`text-[10px] ${g === true ? 'text-signal-pos' : g === false ? 'text-signal-neg' : 'text-ink-tertiary/40'}`}
        >
          ●
        </span>
      ))}
    </span>
  )
}

function getSortValue(col: SortCol, f: FundRow, period: Period): number | string {
  // Re-shape the row so buildSortKey() can read the canonical column key it expects.
  switch (col) {
    case 'scheme_name':    return buildSortKey('scheme_name',    { scheme_name: f.scheme_name })
    case 'amc':            return buildSortKey('amc',            { amc: f.amc })
    case 'category':       return buildSortKey('category',       { category: f.category_name })
    case 'nav_state':      return buildSortKey('nav_state',      { nav_state: f.nav_state })
    case 'composition':    return buildSortKey('composition_state', { composition_state: f.composition_state })
    case 'holdings':       return buildSortKey('holdings_state',    { holdings_state: f.holdings_state })
    case 'recommendation': return buildSortKey('recommendation',    { recommendation: f.recommendation })
    case 'ret':            return buildSortKey('ret',            { ret: f[RET_KEY[period]] as string | null })
    case 'rs_pctile':      return buildSortKey('rs_pctile',      { rs_pctile: f[PCTILE_KEY[period]] as string | null })
    case 'rs_category':    return buildSortKey('rs_category',    { rs_category: (f[RSCAT_KEY[period]] as string | null) ?? '' })
    case 'vol':            return buildSortKey('ret',            { ret: f.realized_vol_63 })
    case 'weeks_in_state': return buildSortKey('weeks_in_state', { weeks_in_state: f.weeks_in_current_state })
    case 'drawdown':       return buildSortKey('drawdown',       { drawdown: f.ret_12m })
    case 'max_drawdown':   return buildSortKey('drawdown',       { drawdown: f.drawdown_ratio_252 })
  }
}

export function FundScreener({ funds, period, activeFilter, onFilterChange: _onFilterChange }: Props) {
  // filter chips live in FundPageClient; activeFilter is display-only context here
  void activeFilter
  const [sortCol, setSortCol] = useState<SortCol>('rs_pctile')
  const [sortAsc, setSortAsc] = useState(false)
  const [visibleCols, setVisibleCols] = useColumnVisibility(COL_STORAGE_KEY, ALL_COLS)

  function handleSort(k: SortCol) {
    if (sortCol === k) setSortAsc(a => !a)
    else { setSortCol(k); setSortAsc(false) }
  }

  const retKey    = RET_KEY[period]
  const pctileKey = PCTILE_KEY[period]
  const rsCatKey  = RSCAT_KEY[period]

  const sorted = useMemo(() => {
    return [...funds].sort((a, b) => {
      const av = getSortValue(sortCol, a, period)
      const bv = getSortValue(sortCol, b, period)
      let cmp = 0
      if (av == null && bv == null) cmp = 0
      else if (av == null) cmp = 1
      else if (bv == null) cmp = -1
      else if (typeof av === 'string' && typeof bv === 'string') cmp = av.localeCompare(bv)
      else cmp = (av as number) - (bv as number)
      return sortAsc ? cmp : -cmp
    })
  }, [funds, sortCol, sortAsc, period])

  // Total visible columns = always-visible Fund Name (1) + selected toggleable cols.
  const totalCols = 1 + ALL_COLS.filter(c => visibleCols.has(c.key)).length

  function SortIcon({ k }: { k: SortCol }) {
    if (sortCol !== k) return <ChevronUp className="w-3 h-3 opacity-20" />
    return sortAsc ? <ChevronUp className="w-3 h-3 text-teal" /> : <ChevronDown className="w-3 h-3 text-teal" />
  }

  function Th({ label, k, align = 'left', title }: { label: string; k: SortCol; align?: 'left' | 'right'; title?: string }) {
    const active = sortCol === k
    return (
      <th
        onClick={() => handleSort(k)}
        title={title}
        className={`px-3 py-2 font-sans text-[10px] font-semibold uppercase tracking-wider cursor-pointer hover:text-ink-secondary select-none whitespace-nowrap text-${align} ${active ? 'text-teal' : 'text-ink-tertiary'}${title ? ' cursor-help' : ''}`}
      >
        <span className={`inline-flex items-center gap-1 ${align === 'right' ? 'flex-row-reverse' : ''}`}>
          {label}
          <SortIcon k={k} />
        </span>
      </th>
    )
  }

  function PlainTh({ label, align = 'left' }: { label: string; align?: 'left' | 'right' }) {
    return (
      <th className={`px-3 py-2 font-sans text-[10px] font-semibold uppercase tracking-wider whitespace-nowrap text-${align} text-ink-tertiary`}>
        {label}
      </th>
    )
  }

  return (
    <div className="flex flex-col gap-3">
      {/* Header: count + column toggle */}
      <div className="flex items-center gap-2">
        <span className="font-sans text-xs text-ink-tertiary whitespace-nowrap">
          Showing {sorted.length} of {funds.length} funds
        </span>
        <div className="ml-auto">
          <ColumnToggle columns={ALL_COLS} visible={visibleCols} onChange={setVisibleCols} />
        </div>
      </div>

      {/* Table */}
      <div className="overflow-x-auto border border-paper-rule rounded-sm">
        <table className="w-full border-collapse">
          <thead>
            <tr className="border-b border-paper-rule bg-paper">
              <Th label="Fund Name" k="scheme_name" />
              {visibleCols.has('amc')            && <Th label="AMC"            k="amc" />}
              {visibleCols.has('category')       && <Th label="Category"       k="category" />}
              {visibleCols.has('nav_state')      && <Th label="NAV State"      k="nav_state" />}
              {visibleCols.has('composition')    && <Th label="Comp"           k="composition" />}
              {visibleCols.has('holdings')       && <Th label="Holdings"       k="holdings" />}
              {visibleCols.has('recommendation') && <Th label="Rec"            k="recommendation" />}
              {visibleCols.has('ret')            && <Th label={`Ret ${period}`} k="ret"        align="right" />}
              {visibleCols.has('rs_pctile')      && <Th label="RS Pctile"      k="rs_pctile"   align="right" />}
              {visibleCols.has('rs_category')    && <Th label="RS Cat"         k="rs_category" align="right" />}
              {visibleCols.has('vol')            && <Th label="Vol 63D"        k="vol"          align="right" />}
              {visibleCols.has('gates')          && <PlainTh label="Gates" />}
              {visibleCols.has('comp_bar')       && <PlainTh label="Comp Bar" />}
              {visibleCols.has('holdings_bar')   && <PlainTh label="Holdings Bar" />}
              {visibleCols.has('weeks_in_state') && <Th label="In State" k="weeks_in_state" align="right" title="How long this fund has been in its current NAV state (d=days, w=weeks, mo=months)" />}
              {visibleCols.has('drawdown')       && <Th label="1Y Ret"         k="drawdown"       align="right" />}
              {visibleCols.has('max_drawdown')   && <Th label="Max DD (1Y)"    k="max_drawdown"   align="right" title="Maximum drawdown over 252 trading days (1 year)" />}
            </tr>
          </thead>
          <tbody>
            {sorted.length === 0 ? (
              <tr>
                <td colSpan={totalCols} className="px-6 py-10 text-center">
                  <p className="font-sans text-sm text-ink-secondary">No funds match the current filter.</p>
                </td>
              </tr>
            ) : (
              sorted.map((f, i) => {
                const compSegments = [
                  { pct: parseFloat(f.aligned_aum_pct ?? '0'), color: 'green'   as const },
                  { pct: parseFloat(f.neutral_aum_pct ?? '0'), color: 'neutral' as const },
                  { pct: parseFloat(f.avoid_aum_pct ?? '0'),   color: 'red'     as const },
                ]
                const compNullish = f.aligned_aum_pct == null
                const holdSegments = [
                  { pct: parseFloat(f.strong_aum_pct ?? '0'),  color: 'green'   as const },
                  { pct: parseFloat(f.unknown_aum_pct ?? '0'), color: 'neutral' as const },
                  { pct: parseFloat(f.weak_aum_pct ?? '0'),    color: 'red'     as const },
                ]
                const holdNullish = f.strong_aum_pct == null

                return (
                  <tr
                    key={f.mstar_id}
                    className={`border-b border-paper-rule hover:bg-paper-rule/20 transition-colors ${i % 2 === 0 ? '' : 'bg-paper-rule/5'}`}
                  >
                    <td className="px-3 py-2.5 whitespace-nowrap">
                      <Link href={`/funds/${f.mstar_id}`} className="hover:opacity-80">
                        <div className="font-sans text-xs font-semibold text-ink-primary truncate max-w-[220px]">{f.scheme_name}</div>
                      </Link>
                    </td>
                    {visibleCols.has('amc') && (
                      <td className="px-3 py-2.5 font-sans text-xs text-ink-secondary whitespace-nowrap">{f.amc}</td>
                    )}
                    {visibleCols.has('category') && (
                      <td className="px-3 py-2.5 font-sans text-xs text-ink-secondary whitespace-nowrap">{f.category_name}</td>
                    )}
                    {visibleCols.has('nav_state') && (
                      <td className="px-3 py-2.5"><NavStateChip value={f.nav_state} /></td>
                    )}
                    {visibleCols.has('composition') && (
                      <td className="px-3 py-2.5"><CompositionStateChip value={f.composition_state} /></td>
                    )}
                    {visibleCols.has('holdings') && (
                      <td className="px-3 py-2.5"><HoldingsStateChip value={f.holdings_state} /></td>
                    )}
                    {visibleCols.has('recommendation') && (
                      <td className="px-3 py-2.5"><RecommendationChip value={f.recommendation} /></td>
                    )}
                    {visibleCols.has('ret') && (
                      <td className={`px-3 py-2.5 text-right font-mono text-xs tabular-nums ${pctColor(f[retKey] as string | null)}`}>
                        {pct(f[retKey] as string | null)}
                      </td>
                    )}
                    {visibleCols.has('rs_pctile') && (
                      <td className="px-3 py-2.5 text-right"><RSPctileBar value={f[pctileKey] as string | null} /></td>
                    )}
                    {visibleCols.has('rs_category') && (
                      <td className={`px-3 py-2.5 text-right font-mono text-xs tabular-nums ${pctColor(f[rsCatKey] as string | null)}`}>
                        {pct(f[rsCatKey] as string | null)}
                      </td>
                    )}
                    {visibleCols.has('vol') && (
                      <td className="px-3 py-2.5 text-right font-mono text-xs text-ink-secondary tabular-nums">
                        {f.realized_vol_63 != null
                          ? `${(parseFloat(f.realized_vol_63) * 100).toFixed(0)}%`
                          : '—'}
                      </td>
                    )}
                    {visibleCols.has('gates') && (
                      <td className="px-3 py-2.5">
                        <GateDots f={f} />
                      </td>
                    )}
                    {visibleCols.has('comp_bar') && (
                      <td className="px-3 py-2.5 w-24">
                        <LensBar segments={compSegments} label="Composition" nullish={compNullish} />
                      </td>
                    )}
                    {visibleCols.has('holdings_bar') && (
                      <td className="px-3 py-2.5 w-24">
                        <LensBar segments={holdSegments} label="Holdings" nullish={holdNullish} />
                      </td>
                    )}
                    {visibleCols.has('weeks_in_state') && (
                      <td className="px-3 py-2.5 text-right font-mono text-xs text-ink-secondary">{formatWeeksInState(f.weeks_in_current_state)}</td>
                    )}
                    {visibleCols.has('drawdown') && (
                      <td className={`px-3 py-2.5 text-right font-mono text-xs tabular-nums ${pctColor(f.ret_12m)}`}>
                        {pct(f.ret_12m)}
                      </td>
                    )}
                    {visibleCols.has('max_drawdown') && (
                      <td className={`px-3 py-2.5 text-right font-mono text-xs tabular-nums ${f.drawdown_ratio_252 != null ? 'text-signal-neg' : 'text-ink-tertiary'}`}>
                        {f.drawdown_ratio_252 != null ? pct(f.drawdown_ratio_252) : '—'}
                      </td>
                    )}
                  </tr>
                )
              })
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
