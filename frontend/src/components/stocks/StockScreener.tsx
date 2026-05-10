// allow-large: Sprint 2 screener — sector filter, col toggle, gate dots, expandable rows
'use client'
import { Fragment, useState, useMemo, useEffect } from 'react'
import Link from 'next/link'
import { ChevronUp, ChevronDown } from 'lucide-react'
import type { StockRowWithSector } from '@/lib/queries/stocks'
import {
  pct, pctColor, RSPctileBar,
  RSStateChip, MomentumChip, RiskChip, VolumeChip,
} from '@/lib/stock-formatters'
import { SectorBadge } from './SectorBadge'
import { ColumnToggle, useColumnVisibility, type ColumnDef } from '@/components/ui/ColumnToggle'
import { StateJourneyCompact } from '@/components/ui/StateJourneyCompact'

const RS_ORDER = ['Leader', 'Strong', 'Consolidating', 'Emerging', 'Average', 'Weak', 'Laggard']
const MOM_ORDER = ['Accelerating', 'Improving', 'Flat', 'Deteriorating', 'Collapsing']
const RISK_ORDER = ['Low', 'Normal', 'Elevated', 'High', 'Below Trend']
const VOL_ORDER = ['Accumulation', 'Steady-Buying', 'Neutral', 'Distribution', 'Heavy Distribution']

type SortKey =
  | 'symbol' | 'sector' | 'rs_pctile_3m' | 'cap_rank'
  | 'ret_1m' | 'ret_3m' | 'ret_6m'
  | 'rs_state' | 'momentum_state' | 'risk_state' | 'volume_state'

type FilterChip = 'all' | 'n50' | 'n100' | 'n500' | 'investable' | 'leader' | 'accel'

const CHIPS: { key: FilterChip; label: string }[] = [
  { key: 'all',        label: 'All' },
  { key: 'n50',        label: 'Nifty 50' },
  { key: 'n100',       label: 'Nifty 100' },
  { key: 'n500',       label: 'Nifty 500' },
  { key: 'investable', label: 'Investable' },
  { key: 'leader',     label: 'Leader/Strong' },
  { key: 'accel',      label: 'Accelerating' },
]

// Optional columns. 1W, 6M, 12M visible by default.
const OPTIONAL_COLS: ColumnDef[] = [
  { key: 'ret_1d',          label: '1D',          defaultVisible: false },
  { key: 'ret_1w',          label: '1W',          defaultVisible: true },
  { key: 'ret_6m',          label: '6M',          defaultVisible: true },
  { key: 'ret_12m',         label: '12M',         defaultVisible: true },
  { key: 'rs_pctile_1w',   label: 'RS 1W',       defaultVisible: false },
  { key: 'rs_pctile_1m',   label: 'RS 1M',       defaultVisible: false },
  { key: 'extension_pct',  label: 'Ext %',       defaultVisible: false },
  { key: 'ema_20_ratio',   label: 'EMA20 %',    defaultVisible: false },
  { key: 'vol_63',         label: 'Vol (63D)',   defaultVisible: false },
  { key: 'vol_ratio_63',   label: 'Vol Ratio',   defaultVisible: false },
  { key: 'max_drawdown_252', label: 'Max DD',    defaultVisible: false },
  { key: 'drawdown',       label: 'Drawdown',    defaultVisible: false },
  { key: 'effort_ratio_63', label: 'Effort',     defaultVisible: false },
  { key: 'volume_expansion', label: 'Vol Exp',   defaultVisible: false },
  { key: 'ma_30w_slope_4w', label: '30W Slope',  defaultVisible: false },
  { key: 'days_in_state',  label: 'Days',        defaultVisible: false },
  { key: 'alpha_3m',       label: 'α 3M',        defaultVisible: false },
  { key: 'alpha_6m',       label: 'α 6M',        defaultVisible: false },
]

const COL_STORAGE_KEY = 'atlas-stock-screener-cols'

// Always-visible columns: Symbol, Cap, Sector, Gates, RS State, Mom, Risk, Vol, 1M, 3M, RS Pctile = 11
const ALWAYS_VISIBLE_COL_COUNT = 11

function stateRank(order: string[], val: string | null): number {
  if (!val) return order.length
  const i = order.indexOf(val)
  return i === -1 ? order.length : i
}

function capRank(s: StockRowWithSector): number {
  if (s.in_nifty_50) return 1
  if (s.in_nifty_100) return 2
  if (s.in_nifty_500) return 3
  return 4
}

// Safely read an optional field that may not exist on the row type.
function optField(row: StockRowWithSector, key: string): unknown {
  return (row as unknown as Record<string, unknown>)[key]
}

function optStr(row: StockRowWithSector, key: string): string | null {
  const v = optField(row, key)
  if (v == null) return null
  return typeof v === 'string' ? v : String(v)
}

function optBool(row: StockRowWithSector, key: string): boolean | null {
  const v = optField(row, key)
  if (v === true || v === false) return v
  return null
}

function optNum(row: StockRowWithSector, key: string): number | null {
  const v = optField(row, key)
  if (v == null) return null
  if (typeof v === 'number') return v
  if (typeof v === 'string') {
    const n = parseFloat(v)
    return Number.isFinite(n) ? n : null
  }
  return null
}

const GATE_LEGEND = [
  { key: 'H', field: 'history_gate_pass',   label: 'History',   desc: 'Stock has ≥6M of price history in our universe' },
  { key: 'L', field: 'liquidity_gate_pass', label: 'Liquidity', desc: 'Avg daily value traded meets minimum threshold' },
  { key: 'W', field: 'weinstein_gate_pass', label: 'Weinstein', desc: 'Price is in Weinstein Stage 2 (above rising 30W MA)' },
  { key: 'S', field: 'strength_gate',       label: 'Strength',  desc: 'RS State is Leader, Strong, or Emerging' },
  { key: 'D', field: 'direction_gate',      label: 'Direction', desc: 'Momentum is Accelerating or Improving' },
  { key: 'R', field: 'risk_gate',           label: 'Risk',      desc: 'Risk state is Low or Normal (not Elevated/High/Below Trend)' },
  { key: 'V', field: 'volume_gate',         label: 'Volume',    desc: 'Volume state is Accumulation or Steady-Buying' },
  { key: 'G', field: 'sector_gate',         label: 'Sector',    desc: 'Sector is not in avoid list (sector momentum is healthy)' },
  { key: 'M', field: 'market_gate',         label: 'Market',    desc: 'Market regime is Risk-On or Cautious (not Risk-Off)' },
]

function GateDot({ value }: { value: boolean | null }) {
  const color = value === true
    ? 'bg-teal'
    : value === false ? 'bg-signal-neg' : 'bg-paper-rule'
  return <span className={`w-1.5 h-1.5 rounded-full ${color} shrink-0`} />
}

function GateDots({ row }: { row: StockRowWithSector }) {
  const vals = GATE_LEGEND.map(g => optBool(row, g.field))
  const passCount = vals.filter(v => v === true).length
  const tooltipText = GATE_LEGEND.map((g, i) =>
    `${g.key}=${g.label}: ${vals[i] === true ? '✓' : vals[i] === false ? '✗' : '?'} — ${g.desc}`
  ).join('\n')
  return (
    <span
      className="inline-flex items-center gap-0.5"
      title={tooltipText}
    >
      {vals.map((v, i) => <GateDot key={i} value={v} />)}
      <span className="ml-1 font-mono text-[10px] text-ink-tertiary tabular-nums">{passCount}/9</span>
    </span>
  )
}

export function StockScreener({
  stocks,
  maFilter,
}: {
  stocks: StockRowWithSector[]
  maFilter?: 'above_30w_ma' | 'above_50d_ma' | 'above_200d_ma' | null
}) {
  const [sortKey, setSortKey] = useState<SortKey>('cap_rank')
  const [asc, setAsc] = useState(true)
  const [chip, setChip] = useState<FilterChip>('all')
  const [search, setSearch] = useState('')
  const [sectorFilter, setSectorFilter] = useState<string>('All Sectors')
  const [expandedSymbol, setExpandedSymbol] = useState<string | null>(null)
  const [visibleCols, setVisibleCols] = useColumnVisibility(COL_STORAGE_KEY, OPTIONAL_COLS)
  const [page, setPage] = useState(1)
  const PAGE_SIZE = 50

  // Sorted, deduped sector list for the dropdown.
  const sectorOptions = useMemo(() => {
    const set = new Set<string>()
    for (const s of stocks) {
      if (s.sector) set.add(s.sector)
    }
    return ['All Sectors', ...[...set].sort((a, b) => a.localeCompare(b))]
  }, [stocks])

  function handleSort(key: SortKey) {
    if (sortKey === key) setAsc(a => !a)
    else { setSortKey(key); setAsc(false) }
  }

  function clearFilters() {
    setChip('all')
    setSearch('')
    setSectorFilter('All Sectors')
  }

  function toggleExpanded(symbol: string) {
    setExpandedSymbol(prev => prev === symbol ? null : symbol)
  }

  const filtered = useMemo(() => {
    let result = stocks

    // MA breadth filter from parent shell
    if (maFilter === 'above_30w_ma') result = result.filter(s => s.above_30w_ma === true)
    else if (maFilter === 'above_50d_ma') result = result.filter(s => optBool(s, 'above_50d_ma') === true)
    else if (maFilter === 'above_200d_ma') result = result.filter(s => optBool(s, 'above_200d_ma') === true)

    if (chip === 'n50') result = result.filter(s => s.in_nifty_50)
    else if (chip === 'n100') result = result.filter(s => s.in_nifty_100)
    else if (chip === 'n500') result = result.filter(s => s.in_nifty_500)
    else if (chip === 'investable') result = result.filter(s => s.is_investable)
    else if (chip === 'leader') result = result.filter(
      s => s.rs_state === 'Leader' || s.rs_state === 'Strong'
    )
    else if (chip === 'accel') result = result.filter(
      s => s.momentum_state === 'Accelerating' || s.momentum_state === 'Improving'
    )

    if (sectorFilter !== 'All Sectors') {
      result = result.filter(s => s.sector === sectorFilter)
    }

    if (search.trim()) {
      const q = search.trim().toLowerCase()
      result = result.filter(
        s => s.symbol.toLowerCase().includes(q) || s.company_name.toLowerCase().includes(q)
      )
    }

    return [...result].sort((a, b) => {
      // Nulls always last regardless of sort direction.
      function numVal(row: StockRowWithSector, key: string): number | null {
        const v = (row as unknown as Record<string, unknown>)[key]
        if (v == null) return null
        const n = typeof v === 'string' ? parseFloat(v) : typeof v === 'number' ? v : NaN
        return Number.isFinite(n) ? n : null
      }

      // Push stocks with no metric data (ret_1m is null) to the bottom always.
      const aHasData = a.ret_1m != null
      const bHasData = b.ret_1m != null
      if (!aHasData || !bHasData) {
        if (aHasData === bHasData) return a.symbol.localeCompare(b.symbol)
        return aHasData ? -1 : 1
      }

      if (sortKey === 'symbol') {
        const cmp = a.symbol.localeCompare(b.symbol)
        return asc ? cmp : -cmp
      }
      if (sortKey === 'sector') {
        const cmp = a.sector.localeCompare(b.sector)
        return asc ? cmp : -cmp
      }
      if (sortKey === 'rs_state') {
        const cmp = stateRank(RS_ORDER, a.rs_state) - stateRank(RS_ORDER, b.rs_state)
        return asc ? cmp : -cmp
      }
      if (sortKey === 'momentum_state') {
        const cmp = stateRank(MOM_ORDER, a.momentum_state) - stateRank(MOM_ORDER, b.momentum_state)
        return asc ? cmp : -cmp
      }
      if (sortKey === 'risk_state') {
        const cmp = stateRank(RISK_ORDER, a.risk_state) - stateRank(RISK_ORDER, b.risk_state)
        return asc ? cmp : -cmp
      }
      if (sortKey === 'volume_state') {
        const cmp = stateRank(VOL_ORDER, a.volume_state) - stateRank(VOL_ORDER, b.volume_state)
        return asc ? cmp : -cmp
      }
      if (sortKey === 'cap_rank') {
        const cmp = capRank(a) - capRank(b)
        return asc ? cmp : -cmp
      }
      // Numeric sort — nulls always last regardless of direction
      const av = numVal(a, sortKey)
      const bv = numVal(b, sortKey)
      if (av == null && bv == null) return 0
      if (av == null) return 1   // null a → always after non-null b
      if (bv == null) return -1  // null b → always after non-null a
      const cmp = av - bv
      return asc ? cmp : -cmp
    })
  }, [stocks, chip, sectorFilter, search, sortKey, asc, maFilter])

  useEffect(() => {
    setPage(1)
  }, [chip, sectorFilter, search, sortKey, asc, maFilter])

  const pagedRows = useMemo(
    () => filtered.slice(0, page * PAGE_SIZE),
    [filtered, page, PAGE_SIZE]
  )
  const hasMore = pagedRows.length < filtered.length

  // Total visible columns = always-visible + optional columns currently selected.
  const optionalVisibleCount = OPTIONAL_COLS.filter(c => visibleCols.has(c.key)).length
  const totalCols = ALWAYS_VISIBLE_COL_COUNT + optionalVisibleCount

  function SortIcon({ k }: { k: SortKey }) {
    if (sortKey !== k) return <ChevronUp className="w-3 h-3 opacity-20" />
    return asc ? <ChevronUp className="w-3 h-3 text-teal" /> : <ChevronDown className="w-3 h-3 text-teal" />
  }

  function Th({
    label, k, align = 'left',
  }: { label: string; k: SortKey; align?: 'left' | 'right' }) {
    const active = sortKey === k
    return (
      <th
        onClick={() => handleSort(k)}
        className={`px-3 py-2 font-sans text-[10px] font-semibold uppercase tracking-wider cursor-pointer hover:text-ink-secondary select-none whitespace-nowrap text-${align} ${active ? 'text-teal' : 'text-ink-tertiary'}`}
      >
        <span className={`inline-flex items-center gap-1 ${align === 'right' ? 'flex-row-reverse' : ''}`}>
          {label}
          <SortIcon k={k} />
        </span>
      </th>
    )
  }

  // Plain (non-sortable) header for optional columns and Gates column.
  function PlainTh({ label, align = 'left' }: { label: string; align?: 'left' | 'right' }) {
    return (
      <th
        className={`px-3 py-2 font-sans text-[10px] font-semibold uppercase tracking-wider whitespace-nowrap text-${align} text-ink-tertiary`}
      >
        {label}
      </th>
    )
  }

  return (
    <div className="flex flex-col gap-3">
      {/* Controls */}
      <div className="flex flex-wrap items-center gap-2">
        <input
          type="search"
          placeholder="Search symbol or company..."
          value={search}
          onChange={e => setSearch(e.target.value)}
          className="px-3 py-1.5 border border-paper-rule rounded-sm font-sans text-sm text-ink-primary bg-paper placeholder:text-ink-tertiary focus:outline-none focus:ring-1 focus:ring-teal/50 w-56"
        />
        <select
          value={sectorFilter}
          onChange={e => setSectorFilter(e.target.value)}
          aria-label="Filter by sector"
          className="px-2 py-1.5 border border-paper-rule rounded-sm font-sans text-sm text-ink-primary bg-paper focus:outline-none focus:ring-1 focus:ring-teal/50"
        >
          {sectorOptions.map(s => (
            <option key={s} value={s}>{s}</option>
          ))}
        </select>
        <div className="flex flex-wrap gap-1.5">
          {CHIPS.map(c => (
            <button
              key={c.key}
              type="button"
              aria-pressed={chip === c.key}
              onClick={() => setChip(c.key)}
              className={`px-2.5 py-1 min-h-[44px] rounded-sm font-sans text-xs font-medium transition-colors ${
                chip === c.key
                  ? 'bg-teal text-paper'
                  : 'bg-paper-rule/20 text-ink-secondary hover:bg-paper-rule/40'
              }`}
            >
              {c.label}
            </button>
          ))}
        </div>
        <div className="ml-auto flex items-center gap-2">
          <span className="font-sans text-xs text-ink-tertiary whitespace-nowrap">
            {pagedRows.length} of {filtered.length} shown ({stocks.length} total)
          </span>
          <ColumnToggle columns={OPTIONAL_COLS} visible={visibleCols} onChange={setVisibleCols} />
        </div>
      </div>

      {/* Table */}
      <div className="overflow-x-auto border border-paper-rule rounded-sm">
        <table className="w-full border-collapse">
          <thead>
            <tr className="border-b border-paper-rule bg-paper">
              <Th label="Symbol" k="symbol" />
              <Th label="Cap" k="cap_rank" />
              <Th label="Sector" k="sector" />
              <th className="px-3 py-2 font-sans text-[10px] font-semibold uppercase tracking-wider whitespace-nowrap text-ink-tertiary">
                <span className="inline-flex items-center gap-1">
                  Gates
                  <span
                    className="cursor-help opacity-50 hover:opacity-100 text-[9px]"
                    title={GATE_LEGEND.map(g => `${g.key}=${g.label}: ${g.desc}`).join('\n')}
                  >
                    ⓘ
                  </span>
                </span>
              </th>
              <Th label="RS State" k="rs_state" />
              <Th label="Mom" k="momentum_state" />
              <Th label="Risk" k="risk_state" />
              <Th label="Vol" k="volume_state" />
              {visibleCols.has('ret_1d') && <PlainTh label="1D" align="right" />}
              {visibleCols.has('ret_1w') && <PlainTh label="1W" align="right" />}
              <Th label="1M" k="ret_1m" align="right" />
              <Th label="3M" k="ret_3m" align="right" />
              {visibleCols.has('ret_6m') && <Th label="6M" k="ret_6m" align="right" />}
              {visibleCols.has('ret_12m') && <PlainTh label="12M" align="right" />}
              {visibleCols.has('rs_pctile_1w') && <PlainTh label="RS 1W" align="right" />}
              {visibleCols.has('rs_pctile_1m') && <PlainTh label="RS 1M" align="right" />}
              {visibleCols.has('extension_pct') && <PlainTh label="Ext %" align="right" />}
              {visibleCols.has('ema_20_ratio') && <PlainTh label="EMA20 %" align="right" />}
              {visibleCols.has('vol_63') && <PlainTh label="Vol 63D" align="right" />}
              {visibleCols.has('vol_ratio_63') && <PlainTh label="Vol Ratio" align="right" />}
              {visibleCols.has('max_drawdown_252') && <PlainTh label="Max DD" align="right" />}
              {visibleCols.has('drawdown') && <PlainTh label="Drawdown" align="right" />}
              {visibleCols.has('effort_ratio_63') && <PlainTh label="Effort" align="right" />}
              {visibleCols.has('volume_expansion') && <PlainTh label="Vol Exp" align="right" />}
              {visibleCols.has('ma_30w_slope_4w') && <PlainTh label="30W Slope" align="right" />}
              {visibleCols.has('days_in_state') && <PlainTh label="Days" align="right" />}
              {visibleCols.has('alpha_3m') && <PlainTh label="α 3M" align="right" />}
              {visibleCols.has('alpha_6m') && <PlainTh label="α 6M" align="right" />}
              <Th label="RS Pctile" k="rs_pctile_3m" align="right" />
            </tr>
          </thead>
          <tbody>
            {filtered.length === 0 ? (
              <tr>
                <td colSpan={totalCols} className="px-6 py-10 text-center">
                  <p className="font-sans text-sm text-ink-secondary mb-2">
                    No stocks match the current filter.
                  </p>
                  <button onClick={clearFilters} className="font-sans text-xs text-teal hover:underline">
                    Clear filters
                  </button>
                </td>
              </tr>
            ) : (
              pagedRows.map((row, i) => {
                const isExpanded = expandedSymbol === row.symbol
                const ret1d = optStr(row, 'ret_1d')
                const ret1w = optStr(row, 'ret_1w')
                const ret6m = optStr(row, 'ret_6m')
                const ret12m = optStr(row, 'ret_12m')
                const rsPctile1w = optStr(row, 'rs_pctile_1w')
                const rsPctile1m = optStr(row, 'rs_pctile_1m')
                const extPct = optStr(row, 'extension_pct')
                const ema20Ratio = optStr(row, 'ema_20_ratio')
                const vol63 = optStr(row, 'vol_63')
                const volRatio63 = optStr(row, 'vol_ratio_63')
                const maxDrawdown252 = optStr(row, 'max_drawdown_252')
                const drawdown = optStr(row, 'drawdown')
                const effortRatio63 = optStr(row, 'effort_ratio_63')
                const volumeExpansion = optStr(row, 'volume_expansion')
                const ma30wSlope4w = optStr(row, 'ma_30w_slope_4w')
                const daysInState = optNum(row, 'days_in_state')
                const alpha3m = optStr(row, 'alpha_3m')
                const alpha6m = optStr(row, 'alpha_6m')

                return (
                  <Fragment key={row.instrument_id}>
                    <tr
                      onClick={() => toggleExpanded(row.symbol)}
                      className={`border-b border-paper-rule hover:bg-paper-rule/20 transition-colors cursor-pointer ${i % 2 === 0 ? '' : 'bg-paper-rule/5'} ${isExpanded ? 'bg-paper-rule/30' : ''}`}
                    >
                      <td className="px-3 py-2.5 whitespace-nowrap">
                        <Link
                          href={`/stocks/${encodeURIComponent(row.symbol)}`}
                          onClick={e => e.stopPropagation()}
                          className="hover:opacity-80"
                        >
                          <div className="font-sans text-xs font-semibold text-ink-primary">{row.symbol}</div>
                          <div className="font-sans text-[10px] text-ink-tertiary truncate max-w-[160px]" title={row.company_name}>
                            {row.company_name}
                          </div>
                        </Link>
                      </td>
                      <td className="px-3 py-2.5 whitespace-nowrap">
                        <span className="font-mono text-[10px] text-ink-tertiary">
                          {row.in_nifty_50 ? 'N50' : row.in_nifty_100 ? 'N100' : row.in_nifty_500 ? 'N500' : 'Other'}
                        </span>
                      </td>
                      <td className="px-3 py-2.5">
                        <SectorBadge sector={row.sector} />
                      </td>
                      <td className="px-3 py-2.5">
                        <GateDots row={row} />
                      </td>
                      <td className="px-3 py-2.5">
                        <RSStateChip value={row.rs_state} />
                      </td>
                      <td className="px-3 py-2.5">
                        <MomentumChip value={row.momentum_state} />
                      </td>
                      <td className="px-3 py-2.5">
                        <RiskChip value={row.risk_state} />
                      </td>
                      <td className="px-3 py-2.5">
                        <VolumeChip value={row.volume_state} />
                      </td>
                      {visibleCols.has('ret_1d') && (
                        <td className={`px-3 py-2.5 text-right font-mono text-xs tabular-nums ${pctColor(ret1d)}`}>
                          {pct(ret1d)}
                        </td>
                      )}
                      {visibleCols.has('ret_1w') && (
                        <td className={`px-3 py-2.5 text-right font-mono text-xs tabular-nums ${pctColor(ret1w)}`}>
                          {pct(ret1w)}
                        </td>
                      )}
                      <td className={`px-3 py-2.5 text-right font-mono text-xs tabular-nums ${pctColor(row.ret_1m)}`}>
                        {pct(row.ret_1m)}
                      </td>
                      <td className={`px-3 py-2.5 text-right font-mono text-xs tabular-nums ${pctColor(row.ret_3m)}`}>
                        {pct(row.ret_3m)}
                      </td>
                      {visibleCols.has('ret_6m') && (
                        <td className={`px-3 py-2.5 text-right font-mono text-xs tabular-nums ${pctColor(ret6m)}`}>
                          {pct(ret6m)}
                        </td>
                      )}
                      {visibleCols.has('ret_12m') && (
                        <td className={`px-3 py-2.5 text-right font-mono text-xs tabular-nums ${pctColor(ret12m)}`}>
                          {pct(ret12m)}
                        </td>
                      )}
                      {visibleCols.has('rs_pctile_1w') && (
                        <td className="px-3 py-2.5 text-right font-mono text-xs tabular-nums text-ink-secondary">
                          {rsPctile1w != null ? `${Math.round(parseFloat(rsPctile1w) * 100)}%` : '—'}
                        </td>
                      )}
                      {visibleCols.has('rs_pctile_1m') && (
                        <td className="px-3 py-2.5 text-right font-mono text-xs tabular-nums text-ink-secondary">
                          {rsPctile1m != null ? `${Math.round(parseFloat(rsPctile1m) * 100)}%` : '—'}
                        </td>
                      )}
                      {visibleCols.has('extension_pct') && (
                        <td className={`px-3 py-2.5 text-right font-mono text-xs tabular-nums ${pctColor(extPct)}`}>
                          {pct(extPct)}
                        </td>
                      )}
                      {visibleCols.has('ema_20_ratio') && (
                        <td className={`px-3 py-2.5 text-right font-mono text-xs tabular-nums ${ema20Ratio != null ? (parseFloat(ema20Ratio) >= 1.0 ? 'text-signal-pos' : 'text-signal-neg') : 'text-ink-tertiary'}`}>
                          {ema20Ratio != null ? `${(parseFloat(ema20Ratio) - 1) >= 0 ? '+' : ''}${((parseFloat(ema20Ratio) - 1) * 100).toFixed(2)}%` : '—'}
                        </td>
                      )}
                      {visibleCols.has('vol_63') && (
                        <td className="px-3 py-2.5 text-right font-mono text-xs tabular-nums text-ink-secondary">
                          {pct(vol63)}
                        </td>
                      )}
                      {visibleCols.has('vol_ratio_63') && (
                        <td className="px-3 py-2.5 text-right font-mono text-xs tabular-nums text-ink-secondary">
                          {volRatio63 != null ? parseFloat(volRatio63).toFixed(2) : '—'}
                        </td>
                      )}
                      {visibleCols.has('max_drawdown_252') && (
                        <td className={`px-3 py-2.5 text-right font-mono text-xs tabular-nums ${pctColor(maxDrawdown252)}`}>
                          {pct(maxDrawdown252)}
                        </td>
                      )}
                      {visibleCols.has('drawdown') && (
                        <td className={`px-3 py-2.5 text-right font-mono text-xs tabular-nums ${pctColor(drawdown)}`}>
                          {pct(drawdown)}
                        </td>
                      )}
                      {visibleCols.has('effort_ratio_63') && (
                        <td className="px-3 py-2.5 text-right font-mono text-xs tabular-nums text-ink-secondary">
                          {effortRatio63 != null ? parseFloat(effortRatio63).toFixed(2) : '—'}
                        </td>
                      )}
                      {visibleCols.has('volume_expansion') && (
                        <td className={`px-3 py-2.5 text-right font-mono text-xs tabular-nums ${pctColor(volumeExpansion)}`}>
                          {volumeExpansion != null ? parseFloat(volumeExpansion).toFixed(2) : '—'}
                        </td>
                      )}
                      {visibleCols.has('ma_30w_slope_4w') && (
                        <td className={`px-3 py-2.5 text-right font-mono text-xs tabular-nums ${pctColor(ma30wSlope4w)}`}>
                          {ma30wSlope4w != null ? `${(parseFloat(ma30wSlope4w) * 100).toFixed(2)}%` : '—'}
                        </td>
                      )}
                      {visibleCols.has('days_in_state') && (
                        <td className="px-3 py-2.5 text-right font-mono text-xs tabular-nums text-ink-secondary">
                          {daysInState != null ? daysInState : '—'}
                        </td>
                      )}
                      {visibleCols.has('alpha_3m') && (
                        <td className={`px-3 py-2.5 text-right font-mono text-xs tabular-nums ${pctColor(alpha3m)}`}>
                          {pct(alpha3m)}
                        </td>
                      )}
                      {visibleCols.has('alpha_6m') && (
                        <td className={`px-3 py-2.5 text-right font-mono text-xs tabular-nums ${pctColor(alpha6m)}`}>
                          {pct(alpha6m)}
                        </td>
                      )}
                      <td className="px-3 py-2.5 text-right">
                        <RSPctileBar value={row.rs_pctile_3m} />
                      </td>
                    </tr>
                    {isExpanded && (
                      <tr className="border-b border-paper-rule bg-paper-rule/10">
                        <td colSpan={totalCols} className="px-4 py-3">
                          <div className="flex items-start justify-between gap-4">
                            <div className="flex-1 min-w-0">
                              <StateJourneyCompact symbol={row.symbol} />
                            </div>
                            <Link
                              href={`/stocks/${encodeURIComponent(row.symbol)}`}
                              onClick={e => e.stopPropagation()}
                              className="font-sans text-xs text-teal hover:underline whitespace-nowrap shrink-0"
                            >
                              Deep dive →
                            </Link>
                          </div>
                        </td>
                      </tr>
                    )}
                  </Fragment>
                )
              })
            )}
          </tbody>
        </table>
      </div>
      {hasMore && (
        <div className="text-center py-2">
          <button
            type="button"
            onClick={() => setPage(p => p + 1)}
            className="font-sans text-xs text-teal hover:underline"
          >
            Load {Math.min(PAGE_SIZE, filtered.length - pagedRows.length)} more
            <span className="ml-1 text-ink-tertiary">
              ({filtered.length - pagedRows.length} remaining)
            </span>
          </button>
        </div>
      )}
    </div>
  )
}
