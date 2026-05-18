'use client'
// allow-large: single table component with conditional column rendering; all logic is cohesive
import { Fragment, useState, useMemo, useEffect, useRef } from 'react'
import Link from 'next/link'
import { ChevronUp, ChevronDown } from 'lucide-react'
import type { StockRowWithSector } from '@/lib/queries/stocks'
import type { ComponentValidation } from '@/lib/queries/component_validation'
import {
  pct, pctColor, RSPctileBar,
} from '@/lib/stock-formatters'
import { SectorBadge } from './SectorBadge'
import { useColumnVisibility } from '@/components/ui/ColumnToggle'
import { WithinStateRankCell } from './WithinStateRankCell'
import { ValidatedBadge } from '@/components/ui/ValidatedBadge'
import {
  RS_ORDER, MOM_ORDER, RISK_ORDER, VOL_ORDER,
  OPTIONAL_COLS, COL_STORAGE_KEY, ALWAYS_VISIBLE_COL_COUNT,
  stateRank, capRank, optBool, optStr, optNum,
  buildStockGrade, buildGradeTooltip,
  COL_TOOLTIPS, isMarketOpen,
  type SortKey, type FilterChip,
} from './screener-utils'
import { ScreenerFilterPanel } from './ScreenerFilterPanel'

export function StockScreener({
  stocks,
  maFilter,
  validations = [],
}: {
  stocks: StockRowWithSector[]
  maFilter?: 'above_30w_ma' | 'above_50d_ma' | 'above_200d_ma' | null
  validations?: ComponentValidation[]
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

  const [livePrices, setLivePrices] = useState<Record<string, string>>({})
  const livePriceIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

  useEffect(() => {
    if (!visibleCols.has('live_price') || !isMarketOpen()) return
    const fetchPrices = async () => {
      try {
        const res = await fetch('/api/intraday?endpoint=prices')
        if (!res.ok) return
        const json = await res.json() as { data: Record<string, string> }
        setLivePrices(json.data ?? {})
      } catch { /* non-critical — shows '—' on error */ }
    }
    void fetchPrices()
    livePriceIntervalRef.current = setInterval(() => void fetchPrices(), 30_000)
    return () => { if (livePriceIntervalRef.current) { clearInterval(livePriceIntervalRef.current); livePriceIntervalRef.current = null } }
  }, [visibleCols])

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
  function PlainTh({ label, align = 'left', tooltip }: { label: string; align?: 'left' | 'right'; tooltip?: string }) {
    return (
      <th
        className={`px-3 py-2 font-sans text-[10px] font-semibold uppercase tracking-wider whitespace-nowrap text-${align} text-ink-tertiary`}
      >
        <span className="inline-flex items-center gap-1">
          {label}
          {tooltip && (
            <span className="cursor-help opacity-50 hover:opacity-100 text-[9px]" title={tooltip}>ⓘ</span>
          )}
        </span>
      </th>
    )
  }

  function formatLivePrice(instrumentId: string): string {
    const raw = livePrices[instrumentId]
    if (!raw) return '—'
    return '₹' + Number(raw).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  }

  return (
    <div className="flex flex-col gap-3">
      <ScreenerFilterPanel
        search={search}
        sectorFilter={sectorFilter}
        chip={chip}
        sectorOptions={sectorOptions}
        pagedRows={pagedRows}
        filtered={filtered}
        stocks={stocks}
        visibleCols={visibleCols}
        onSearch={setSearch}
        onSectorFilter={setSectorFilter}
        onChip={setChip}
        onVisibleColsChange={setVisibleCols}
        onClearFilters={clearFilters}
      />

      {/* Table */}
      <div className="overflow-x-auto border border-paper-rule rounded-sm">
        <table className="w-full border-collapse">
          <thead>
            <tr className="border-b border-paper-rule bg-paper">
              <Th label="Symbol" k="symbol" />
              <Th label="Cap" k="cap_rank" />
              <Th label="Sector" k="sector" />
              <Th label="RS State" k="rs_state" />
              <Th label="Risk" k="risk_state" />
              {visibleCols.has('conviction') && (
                <PlainTh label="Conviction" tooltip={COL_TOOLTIPS.conviction} />
              )}
              {visibleCols.has('quality') && (
                <PlainTh label="Grade" tooltip={COL_TOOLTIPS.quality} />
              )}
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
              {visibleCols.has('live_price') && <PlainTh label="Live ₹" align="right" tooltip="Current intraday close price — refreshes every 30 s during market hours (09:15–15:35 IST)" />}
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
                      <td
                        className="px-3 py-2.5"
                        data-validator-id={`stock.rs_state:${row.instrument_id}`}
                        data-validator-raw={row.rs_state ?? ''}
                      >
                        <ValidatedBadge
                          label={row.rs_state ?? '—'}
                          validation={validations.find(v => v.component_name === 'rs' && v.badge === row.rs_state) ?? undefined}
                        />
                      </td>
                      <td className="px-3 py-2.5">
                        <ValidatedBadge
                          label={row.risk_state ?? '—'}
                          validation={validations.find(v => v.component_name === 'risk' && v.badge === row.risk_state) ?? undefined}
                        />
                      </td>
                      {visibleCols.has('conviction') && (
                        <td className="px-3 py-2.5">
                          <WithinStateRankCell value={typeof (row as Record<string, unknown>).within_state_rank === 'number' ? (row as Record<string, unknown>).within_state_rank as number : null} />
                        </td>
                      )}
                      {visibleCols.has('quality') && (() => {
                        const g = buildStockGrade(row)
                        return (
                          <td className="px-3 py-2.5" title={buildGradeTooltip(row)}>
                            <span
                              className="inline-flex items-center justify-center w-5 h-5 rounded font-mono text-[11px] font-bold text-white"
                              style={{ background: g.color }}
                            >
                              {g.grade}
                            </span>
                          </td>
                        )
                      })()}
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
                      <td
                        className={`px-3 py-2.5 text-right font-mono text-xs tabular-nums ${pctColor(row.ret_1m)}`}
                        data-validator-id={`stock.ret_1m:${row.instrument_id}`}
                        data-validator-raw={row.ret_1m ?? ''}
                      >
                        {pct(row.ret_1m)}
                      </td>
                      <td
                        className={`px-3 py-2.5 text-right font-mono text-xs tabular-nums ${pctColor(row.ret_3m)}`}
                        data-validator-id={`stock.ret_3m:${row.instrument_id}`}
                        data-validator-raw={row.ret_3m ?? ''}
                      >
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
                      {visibleCols.has('live_price') && (
                        <td className="px-3 py-2.5 text-right font-mono text-xs tabular-nums text-ink-primary">
                          {formatLivePrice(row.instrument_id)}
                        </td>
                      )}
                      <td
                        className="px-3 py-2.5 text-right"
                        data-validator-id={`stock.rs_pctile_3m:${row.instrument_id}`}
                        data-validator-raw={row.rs_pctile_3m ?? ''}
                      >
                        <RSPctileBar value={row.rs_pctile_3m} />
                      </td>
                    </tr>
                    {isExpanded && (
                      <tr className="border-b border-paper-rule bg-paper-rule/10">
                        <td colSpan={totalCols} className="px-4 py-3">
                          <div className="flex items-start justify-end gap-4">
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
