// allow-large: Sprint 2 ETF screener — col toggle, gate badge, expandable rows
'use client'
import { Fragment, useState, useMemo } from 'react'
import Link from 'next/link'
import { ChevronUp, ChevronDown } from 'lucide-react'
import type { ETFRow } from '@/lib/queries/etfs'
import {
  pct, pctColor, PosSizeBar, RSPctileBar,
  RSStateChip, MomentumChip, RiskChip,
} from '@/lib/stock-formatters'
import { ColumnToggle, useColumnVisibility, type ColumnDef } from '@/components/ui/ColumnToggle'
import { StateJourneyCompact } from '@/components/ui/StateJourneyCompact'

const RS_ORDER = ['Leader', 'Strong', 'Consolidating', 'Emerging', 'Average', 'Weak', 'Laggard']
const MOM_ORDER = ['Accelerating', 'Improving', 'Flat', 'Deteriorating', 'Collapsing']
const RISK_ORDER = ['Low', 'Normal', 'Elevated', 'High', 'Below Trend']

function stateRank(order: string[], val: string | null): number {
  if (!val) return order.length
  const i = order.indexOf(val)
  return i === -1 ? order.length : i
}

type SortKey =
  | 'ticker' | 'theme' | 'rs_pctile_3m'
  | 'ret_1m' | 'ret_3m' | 'ret_12m' | 'position_size_pct'
  | 'rs_state' | 'momentum_state' | 'risk_state'

type FilterChip = 'all' | 'broad' | 'sectoral' | 'investable'

const CHIPS: { key: FilterChip; label: string }[] = [
  { key: 'all',        label: 'All' },
  { key: 'broad',      label: 'Broad' },
  { key: 'sectoral',   label: 'Sectoral' },
  { key: 'investable', label: 'Investable' },
]

const THEME_STYLE: Record<string, string> = {
  Broad:     'bg-teal/10 text-teal',
  Sectoral:  'bg-signal-pos/10 text-signal-pos',
  Thematic:  'bg-signal-warn/10 text-signal-warn',
}

// Optional columns — all default to hidden.
const OPTIONAL_COLS: ColumnDef[] = [
  { key: 'ret_1w',           label: '1W Return',    defaultVisible: false },
  { key: 'ret_12m',          label: '12M Return',   defaultVisible: false },
  { key: 'ret_6m',           label: '6M Return',    defaultVisible: false },
  { key: 'vol_63',           label: 'Vol 63D',      defaultVisible: false },
  { key: 'drawdown',         label: 'Drawdown',     defaultVisible: false },
  { key: 'volume_expansion', label: 'Vol Expansion', defaultVisible: false },
  { key: 'ema_quality',      label: 'EMA Quality',  defaultVisible: false },
  { key: 'days_in_state',    label: 'Days (RS)',    defaultVisible: false },
]

const COL_STORAGE_KEY = 'atlas-etf-screener-cols'

// Always-visible columns:
//   Ticker, Theme, Gates, RS State, Mom, Risk, 1M, 3M, RS Pctile, Deploy %  = 10
const ALWAYS_VISIBLE_COL_COUNT = 10

function TriggerBadges({ row }: { row: ETFRow }) {
  if (!row.breakout_trigger && !row.transition_trigger) return null
  return (
    <div className="flex gap-0.5 mt-0.5">
      {row.breakout_trigger && (
        <span className="inline-flex items-center px-1 py-0 rounded-[2px] font-sans text-[9px] font-bold bg-teal/15 text-teal">BRK</span>
      )}
      {row.transition_trigger && (
        <span className="inline-flex items-center px-1 py-0 rounded-[2px] font-sans text-[9px] font-bold bg-signal-pos/15 text-signal-pos">TRN</span>
      )}
    </div>
  )
}

function ThemeBadge({ theme }: { theme: string }) {
  const style = THEME_STYLE[theme] ?? 'bg-ink-tertiary/10 text-ink-secondary'
  return (
    <span className={`inline-flex items-center px-1.5 py-0.5 rounded-[2px] font-sans text-[10px] font-semibold whitespace-nowrap ${style}`}>
      {theme}
    </span>
  )
}

const GATE_DEFS: { label: string; title: string; key: keyof ETFRow }[] = [
  { label: 'H',  title: 'History gate — ETF has ≥52 weeks of price history',                  key: 'history_gate_pass' },
  { label: 'L',  title: 'Liquidity gate — average daily volume above minimum threshold',       key: 'liquidity_gate_pass' },
  { label: 'W',  title: 'Weinstein gate — price above 30-week (150-day) moving average',       key: 'weinstein_gate_pass' },
  { label: 'S',  title: 'Strength gate — RS state is Leader or Strong (top 30th percentile)', key: 'strength_gate' },
  { label: 'D',  title: 'Direction gate — momentum is Accelerating or Improving',              key: 'direction_gate' },
  { label: 'Ri', title: 'Risk gate — extension <40% above 200-day MA and volatility normal',  key: 'risk_gate' },
]

function GateBadge({ row }: { row: ETFRow }) {
  const passing = GATE_DEFS.filter(g => row[g.key] === true).length
  return (
    <div className="flex items-center gap-0.5">
      <span className={`font-mono text-[9px] mr-0.5 ${passing >= 5 ? 'text-signal-pos' : passing >= 4 ? 'text-signal-warn' : 'text-ink-tertiary'}`}>
        {passing}/6
      </span>
      {GATE_DEFS.map(g => {
        const pass = row[g.key]
        return (
          <span
            key={g.label}
            title={g.title}
            className={`inline-flex items-center justify-center px-0.5 py-0.5 rounded-[2px] font-mono text-[8px] font-bold cursor-help ${
              pass === true
                ? 'bg-teal/15 text-teal'
                : pass === false
                ? 'bg-signal-neg/10 text-signal-neg'
                : 'bg-paper-rule/20 text-ink-tertiary'
            }`}
          >
            {g.label}
          </span>
        )
      })}
    </div>
  )
}

export function ETFScreener({ etfs }: { etfs: ETFRow[] }) {
  const [sortKey, setSortKey] = useState<SortKey>('rs_pctile_3m')
  const [asc, setAsc] = useState(false)
  const [chip, setChip] = useState<FilterChip>('all')
  const [search, setSearch] = useState('')
  const [expandedTicker, setExpandedTicker] = useState<string | null>(null)
  const [visibleCols, setVisibleCols] = useColumnVisibility(COL_STORAGE_KEY, OPTIONAL_COLS)

  function handleSort(key: SortKey) {
    if (sortKey === key) setAsc(a => !a)
    else { setSortKey(key); setAsc(false) }
  }

  function toggleExpanded(ticker: string) {
    setExpandedTicker(prev => prev === ticker ? null : ticker)
  }

  const filtered = useMemo(() => {
    let result = etfs

    if (chip === 'broad')         result = result.filter(e => e.theme === 'Broad')
    else if (chip === 'sectoral') result = result.filter(e => e.theme === 'Sectoral')
    else if (chip === 'investable') result = result.filter(e => e.is_investable)

    if (search.trim()) {
      const q = search.trim().toLowerCase()
      result = result.filter(
        e => e.ticker.toLowerCase().includes(q) || (e.etf_name ?? '').toLowerCase().includes(q)
      )
    }

    return [...result].sort((a, b) => {
      let cmp = 0
      if (sortKey === 'ticker') cmp = a.ticker.localeCompare(b.ticker)
      else if (sortKey === 'theme') cmp = a.theme.localeCompare(b.theme)
      else if (sortKey === 'rs_state') cmp = stateRank(RS_ORDER, a.rs_state) - stateRank(RS_ORDER, b.rs_state)
      else if (sortKey === 'momentum_state') cmp = stateRank(MOM_ORDER, a.momentum_state) - stateRank(MOM_ORDER, b.momentum_state)
      else if (sortKey === 'risk_state') cmp = stateRank(RISK_ORDER, a.risk_state) - stateRank(RISK_ORDER, b.risk_state)
      else {
        const av = a[sortKey as keyof ETFRow] != null ? parseFloat(a[sortKey as keyof ETFRow] as string) : null
        const bv = b[sortKey as keyof ETFRow] != null ? parseFloat(b[sortKey as keyof ETFRow] as string) : null
        if (av == null && bv == null) cmp = 0
        else if (av == null) cmp = 1
        else if (bv == null) cmp = -1
        else cmp = av - bv
      }
      return asc ? cmp : -cmp
    })
  }, [etfs, chip, search, sortKey, asc])

  // Total visible columns = always-visible + optional currently selected.
  const optionalVisibleCount = OPTIONAL_COLS.filter(c => visibleCols.has(c.key)).length
  const totalCols = ALWAYS_VISIBLE_COL_COUNT + optionalVisibleCount

  function SortIcon({ k }: { k: SortKey }) {
    if (sortKey !== k) return <ChevronUp className="w-3 h-3 opacity-20" />
    return asc ? <ChevronUp className="w-3 h-3 text-teal" /> : <ChevronDown className="w-3 h-3 text-teal" />
  }

  function Th({ label, k, align = 'left' }: { label: string; k: SortKey; align?: 'left' | 'right' }) {
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

  // Plain (non-sortable) header for optional and Gates columns.
  function PlainTh({ label, align = 'left', title }: { label: string; align?: 'left' | 'right'; title?: string }) {
    return (
      <th
        title={title}
        className={`px-3 py-2 font-sans text-[10px] font-semibold uppercase tracking-wider whitespace-nowrap text-${align} text-ink-tertiary${title ? ' cursor-help' : ''}`}
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
          placeholder="Search ticker or name..."
          value={search}
          onChange={e => setSearch(e.target.value)}
          className="px-3 py-1.5 border border-paper-rule rounded-sm font-sans text-sm text-ink-primary bg-paper placeholder:text-ink-tertiary focus:outline-none focus:ring-1 focus:ring-teal/50 w-56"
        />
        <div className="flex flex-wrap gap-1.5">
          {CHIPS.map(c => (
            <button
              key={c.key}
              type="button"
              aria-pressed={chip === c.key}
              onClick={() => setChip(c.key)}
              className={`px-2.5 py-1 rounded-sm font-sans text-xs font-medium transition-colors ${
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
            Showing {filtered.length} of {etfs.length} ETFs
          </span>
          <ColumnToggle columns={OPTIONAL_COLS} visible={visibleCols} onChange={setVisibleCols} />
        </div>
      </div>

      {/* Table */}
      <div className="overflow-x-auto border border-paper-rule rounded-sm">
        <table className="w-full border-collapse">
          <thead>
            <tr className="border-b border-paper-rule bg-paper">
              <Th label="Ticker" k="ticker" />
              <Th label="Theme" k="theme" />
              <PlainTh label="Gates" />
              <Th label="RS State" k="rs_state" />
              <Th label="Mom" k="momentum_state" />
              <Th label="Risk" k="risk_state" />
              {visibleCols.has('ret_1w') && <PlainTh label="1W" align="right" />}
              {visibleCols.has('ret_12m') && <Th label="12M" k="ret_12m" align="right" />}
              {visibleCols.has('ret_6m') && <PlainTh label="6M" align="right" />}
              {visibleCols.has('vol_63') && <PlainTh label="Vol 63D" align="right" />}
              {visibleCols.has('drawdown') && <PlainTh label="Drawdown" align="right" />}
              {visibleCols.has('volume_expansion') && <PlainTh label="Vol Exp" align="right" title="Volume expansion: current vol vs 63-day avg. ≥1.5x = institutional accumulation" />}
              {visibleCols.has('ema_quality') && <PlainTh label="EMA Quality" align="right" title="Whether the 10-day EMA is at a 20-day high — short-term upward momentum signal" />}
              {visibleCols.has('days_in_state') && <PlainTh label="Days (RS)" align="right" />}
              <Th label="1M" k="ret_1m" align="right" />
              <Th label="3M" k="ret_3m" align="right" />
              <Th label="RS Pctile" k="rs_pctile_3m" align="right" />
              <Th label="Deploy %" k="position_size_pct" align="right" />
            </tr>
          </thead>
          <tbody>
            {filtered.length === 0 ? (
              <tr>
                <td colSpan={totalCols} className="px-6 py-10 text-center">
                  <p className="font-sans text-sm text-ink-secondary">No ETFs match the current filter.</p>
                </td>
              </tr>
            ) : (
              filtered.map((row, i) => {
                const isExpanded = expandedTicker === row.ticker
                const volExpRaw = row.volume_expansion != null ? parseFloat(row.volume_expansion) : null
                return (
                  <Fragment key={row.ticker}>
                    <tr
                      onClick={() => toggleExpanded(row.ticker)}
                      className={`border-b border-paper-rule hover:bg-paper-rule/20 transition-colors cursor-pointer ${i % 2 === 0 ? '' : 'bg-paper-rule/5'} ${isExpanded ? 'bg-paper-rule/30' : ''}`}
                    >
                      <td className="px-3 py-2.5 whitespace-nowrap">
                        <Link
                          href={`/etfs/${encodeURIComponent(row.ticker)}`}
                          onClick={e => e.stopPropagation()}
                          className="hover:opacity-80"
                        >
                          <div className="font-sans text-xs font-semibold text-ink-primary">{row.ticker}</div>
                          <div className="font-sans text-[10px] text-ink-tertiary truncate max-w-[200px]" title={row.etf_name ?? ''}>
                            {row.etf_name ?? '—'}
                          </div>
                          <TriggerBadges row={row} />
                        </Link>
                      </td>
                      <td className="px-3 py-2.5">
                        <ThemeBadge theme={row.theme} />
                      </td>
                      <td className="px-3 py-2.5">
                        <GateBadge row={row} />
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
                      {visibleCols.has('ret_1w') && (
                        <td className={`px-3 py-2.5 text-right font-mono text-xs tabular-nums ${pctColor(row.ret_1w)}`}>
                          {pct(row.ret_1w)}
                        </td>
                      )}
                      {visibleCols.has('ret_12m') && (
                        <td className={`px-3 py-2.5 text-right font-mono text-xs tabular-nums ${pctColor(row.ret_12m)}`}>
                          {pct(row.ret_12m)}
                        </td>
                      )}
                      {visibleCols.has('ret_6m') && (
                        <td className={`px-3 py-2.5 text-right font-mono text-xs tabular-nums ${pctColor(row.ret_6m)}`}>
                          {pct(row.ret_6m)}
                        </td>
                      )}
                      {visibleCols.has('vol_63') && (
                        <td className="px-3 py-2.5 text-right font-mono text-xs tabular-nums text-ink-secondary">
                          {pct(row.vol_63)}
                        </td>
                      )}
                      {visibleCols.has('drawdown') && (
                        <td className={`px-3 py-2.5 text-right font-mono text-xs tabular-nums ${pctColor(row.drawdown)}`}>
                          {pct(row.drawdown)}
                        </td>
                      )}
                      {visibleCols.has('volume_expansion') && (
                        <td className={`px-3 py-2.5 text-right font-mono text-xs tabular-nums ${
                          volExpRaw == null ? 'text-ink-tertiary'
                          : volExpRaw >= 1.5 ? 'text-signal-pos'
                          : volExpRaw < 0.7 ? 'text-signal-neg'
                          : 'text-ink-secondary'
                        }`}>
                          {volExpRaw != null ? `${volExpRaw.toFixed(1)}x` : '—'}
                        </td>
                      )}
                      {visibleCols.has('ema_quality') && (
                        <td className={`px-3 py-2.5 text-right font-sans text-[10px] ${row.ema_10_at_20d_high ? 'text-signal-pos' : 'text-ink-tertiary'}`}>
                          {row.ema_10_at_20d_high == null ? '—' : row.ema_10_at_20d_high ? 'High ✓' : 'Normal'}
                        </td>
                      )}
                      {visibleCols.has('days_in_state') && (
                        <td className="px-3 py-2.5 text-right font-mono text-xs tabular-nums text-ink-secondary">
                          {row.days_in_state != null ? row.days_in_state : '—'}
                        </td>
                      )}
                      <td className={`px-3 py-2.5 text-right font-mono text-xs tabular-nums ${pctColor(row.ret_1m)}`}>
                        {pct(row.ret_1m)}
                      </td>
                      <td className={`px-3 py-2.5 text-right font-mono text-xs tabular-nums ${pctColor(row.ret_3m)}`}>
                        {pct(row.ret_3m)}
                      </td>
                      <td className="px-3 py-2.5 text-right">
                        <RSPctileBar value={row.rs_pctile_3m} />
                      </td>
                      <td className="px-3 py-2.5 text-right">
                        <div className="flex justify-end">
                          <PosSizeBar value={row.position_size_pct} />
                        </div>
                      </td>
                    </tr>
                    {isExpanded && (
                      <tr className="border-b border-paper-rule bg-paper-rule/10">
                        <td colSpan={totalCols} className="px-4 py-3">
                          <StateJourneyCompact ticker={row.ticker} />
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
    </div>
  )
}
