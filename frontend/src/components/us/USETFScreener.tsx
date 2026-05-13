// allow-large: ETF screener requires full column set and toggle logic
'use client'
import { useState, useMemo, useRef, useEffect, useCallback } from 'react'
import { ChevronUp, ChevronDown, SlidersHorizontal, X } from 'lucide-react'
import type { USETFRow } from '@/lib/queries/us-etfs'

const RS_STATE_COLORS: Record<string, string> = {
  Leader:        'bg-teal text-white',
  Strong:        'bg-teal/20 text-teal',
  Consolidating: 'bg-amber-50 text-amber-700',
  Emerging:      'bg-lime-50 text-lime-700',
  Average:       'bg-paper-rule/40 text-ink-secondary',
  Weak:          'bg-orange-50 text-orange-700',
  Laggard:       'bg-red-50 text-red-700',
}
const MOM_STATE_COLORS: Record<string, string> = {
  Accelerating:  'bg-teal text-white',
  Improving:     'bg-teal/10 text-teal',
  Flat:          'bg-paper-rule/40 text-ink-secondary',
  Deteriorating: 'bg-orange-50 text-orange-700',
  Collapsing:    'bg-red-100 text-red-700',
}
const RISK_STATE_COLORS: Record<string, string> = {
  Low:           'bg-teal/20 text-teal',
  Normal:        'bg-paper-rule/40 text-ink-secondary',
  Elevated:      'bg-amber-50 text-amber-700',
  High:          'bg-orange-50 text-orange-700',
  'Below Trend': 'bg-blue-50 text-blue-700',
}
const VOL_STATE_COLORS: Record<string, string> = {
  Accumulation:         'bg-teal text-white',
  'Steady-Buying':      'bg-teal/20 text-teal',
  Neutral:              'bg-paper-rule/40 text-ink-secondary',
  Distribution:         'bg-orange-50 text-orange-700',
  'Heavy Distribution': 'bg-red-100 text-red-700',
}
const RS_ORDER  = ['Leader', 'Strong', 'Consolidating', 'Emerging', 'Average', 'Weak', 'Laggard']
const MOM_ORDER = ['Accelerating', 'Improving', 'Flat', 'Deteriorating', 'Collapsing']
const fmtPct = (v: string | null, decimals = 1): string => {
  if (!v) return '—'
  const n = parseFloat(v) * 100
  if (!Number.isFinite(n)) return '—'
  return (n >= 0 ? '+' : '') + n.toFixed(decimals) + '%'
}
const fmtPctColor = (v: string | null): string =>
  !v ? 'text-ink-tertiary' : parseFloat(v) >= 0 ? 'text-signal-pos' : 'text-signal-neg'
const fmtRatio = (v: string | null, suffix = 'x', decimals = 2): string => {
  if (!v) return '—'
  const n = parseFloat(v)
  return Number.isFinite(n) ? n.toFixed(decimals) + suffix : '—'
}
const fmtVol = (v: string | null): string => {
  if (!v) return '—'
  const n = parseFloat(v)
  if (!Number.isFinite(n)) return '—'
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + 'M'
  if (n >= 1_000)     return (n / 1_000).toFixed(0) + 'K'
  return n.toFixed(0)
}
const fmtVolPct = (v: string | null): string => {
  if (!v) return '—'
  const n = parseFloat(v) * 100
  return Number.isFinite(n) ? n.toFixed(1) + '%' : '—'
}
const fmtPctile = (v: string | null): string => {
  if (!v) return '—'
  const n = parseFloat(v)
  return Number.isFinite(n) ? Math.round(n * 100) + '%' : '—'
}
const fmtBool = (v: boolean | null): string =>
  v == null ? '—' : v ? '✓' : '✗'
function numVal(v: string | null): number | null {
  if (!v) return null
  const n = parseFloat(v)
  return Number.isFinite(n) ? n : null
}
function stateRank(order: string[], val: string | null): number {
  if (!val) return order.length
  const i = order.indexOf(val)
  return i === -1 ? order.length : i
}
function RSPctileBar({ value }: { value: string | null }) {
  const pct   = value != null ? parseFloat(value) : null
  const width  = pct != null ? Math.round(pct * 100) : 0
  const barColor = pct == null ? 'bg-ink-tertiary/20'
    : pct >= 0.7 ? 'bg-signal-pos'
    : pct >= 0.4 ? 'bg-teal'
    : 'bg-signal-neg/60'
  return (
    <div className="flex items-center gap-1.5 justify-end">
      <span className="font-mono text-xs tabular-nums text-ink-secondary w-8 text-right">
        {pct != null ? Math.round(pct * 100) + '%' : '—'}
      </span>
      <div className="w-12 h-1.5 bg-ink-tertiary/15 rounded-full overflow-hidden">
        <div className={`h-full rounded-full ${barColor}`} style={{ width: `${width}%` }} />
      </div>
    </div>
  )
}
function StateChip({ value, colors }: { value: string | null; colors: Record<string, string> }) {
  if (!value) return <span className="text-ink-tertiary text-xs">{'—'}</span>
  return (
    <span className={`inline-flex items-center px-1.5 py-0.5 rounded-[2px] font-sans text-[10px] font-semibold whitespace-nowrap ${colors[value] ?? 'bg-ink-tertiary/10 text-ink-secondary'}`}>
      {value}
    </span>
  )
}
type CategoryTab = 'All' | 'Sector' | 'Broad' | 'Factor' | 'Commodity'
const TABS: CategoryTab[] = ['All', 'Sector', 'Broad', 'Factor', 'Commodity']
function categoryTab(etf: USETFRow): CategoryTab {
  const cat = (etf.etf_category ?? '').toLowerCase()
  if (cat.includes('sector'))    return 'Sector'
  if (cat.includes('broad') || etf.is_benchmark) return 'Broad'
  if (cat.includes('factor'))    return 'Factor'
  if (cat.includes('commodity') || cat.includes('gold') || cat.includes('metal')) return 'Commodity'
  return 'Broad'
}
type OptColKey =
  | 'ret_1d' | 'ret_1w' | 'ret_6m' | 'ret_12m' | 'ret_12m_1m'
  | 'vol_ratio_63'
  | 'rs_pctile_1m_vt' | 'rs_pctile_6m_vt' | 'rs_pctile_12m_vt'
  | 'rs_pctile_1m_acwi' | 'rs_pctile_3m_acwi' | 'rs_pctile_6m_acwi' | 'rs_pctile_12m_acwi'
  | 'rs_pctile_1m_eem'  | 'rs_pctile_3m_eem'  | 'rs_pctile_6m_eem'  | 'rs_pctile_12m_eem'
  | 'rs_pctile_1m_gold' | 'rs_pctile_3m_gold' | 'rs_pctile_6m_gold' | 'rs_pctile_12m_gold'
  | 'consensus'
  | 'above_30w_ma' | 'ema_10_ratio' | 'ema_20_ratio' | 'extension_pct'
  | 'realized_vol_63' | 'max_drawdown_252' | 'atr_21'
  | 'avg_volume_20' | 'volume_expansion' | 'effort_ratio_63'
  | 'weinstein_gate_pass' | 'history_gate_pass' | 'liquidity_gate_pass'
const OPT_COLS: { key: OptColKey; label: string }[] = [
  { key: 'ret_1d',               label: '1D Ret' },
  { key: 'ret_1w',               label: '1W Ret' },
  { key: 'ret_6m',               label: '6M Ret' },
  { key: 'ret_12m',              label: '12M Ret' },
  { key: 'ret_12m_1m',          label: '12-1M Mom' },
  { key: 'vol_ratio_63',        label: 'Vol Ratio' },
  { key: 'rs_pctile_1m_vt',    label: 'RS 1M (VT)' },
  { key: 'rs_pctile_6m_vt',    label: 'RS 6M (VT)' },
  { key: 'rs_pctile_12m_vt',   label: 'RS 12M (VT)' },
  { key: 'rs_pctile_1m_acwi',  label: 'ACWI 1M' },
  { key: 'rs_pctile_3m_acwi',  label: 'ACWI 3M' },
  { key: 'rs_pctile_6m_acwi',  label: 'ACWI 6M' },
  { key: 'rs_pctile_12m_acwi', label: 'ACWI 12M' },
  { key: 'rs_pctile_1m_eem',   label: 'EEM 1M' },
  { key: 'rs_pctile_3m_eem',   label: 'EEM 3M' },
  { key: 'rs_pctile_6m_eem',   label: 'EEM 6M' },
  { key: 'rs_pctile_12m_eem',  label: 'EEM 12M' },
  { key: 'rs_pctile_1m_gold',  label: 'Gold 1M' },
  { key: 'rs_pctile_3m_gold',  label: 'Gold 3M' },
  { key: 'rs_pctile_6m_gold',  label: 'Gold 6M' },
  { key: 'rs_pctile_12m_gold', label: 'Gold 12M' },
  { key: 'consensus',           label: 'Consensus' },
  { key: 'above_30w_ma',       label: '30W MA' },
  { key: 'ema_10_ratio',       label: 'EMA10' },
  { key: 'ema_20_ratio',       label: 'EMA20' },
  { key: 'extension_pct',      label: 'Extension %' },
  { key: 'realized_vol_63',    label: 'Vol 63D' },
  { key: 'max_drawdown_252',   label: 'Max DD' },
  { key: 'atr_21',             label: 'ATR 21' },
  { key: 'avg_volume_20',      label: 'Avg Vol 20D' },
  { key: 'volume_expansion',   label: 'Vol Exp' },
  { key: 'effort_ratio_63',    label: 'Effort' },
  { key: 'weinstein_gate_pass', label: 'Weinstein' },
  { key: 'history_gate_pass',  label: 'History Gate' },
  { key: 'liquidity_gate_pass', label: 'Liquidity Gate' },
]
const LS_KEY = 'us-etf-screener-cols'
const DEFAULT_OPT_COLS: OptColKey[] = ['ret_1d', 'ret_1w', 'ret_6m', 'above_30w_ma', 'realized_vol_63']
function loadSavedCols(): OptColKey[] {
  if (typeof window === 'undefined') return DEFAULT_OPT_COLS
  try {
    const raw = localStorage.getItem(LS_KEY)
    if (!raw) return DEFAULT_OPT_COLS
    const parsed = JSON.parse(raw) as OptColKey[]
    return Array.isArray(parsed) ? parsed : DEFAULT_OPT_COLS
  } catch { return DEFAULT_OPT_COLS }
}
type SortCol =
  | 'ticker' | 'etf_category' | 'linked_sector' | 'rs_state' | 'momentum_state'
  | 'rs_pctile_3m_vt' | 'ret_1m' | 'ret_3m'
  | 'ret_1d' | 'ret_1w' | 'ret_6m' | 'ret_12m' | 'ret_12m_1m'
  | 'vol_ratio_63'
  | 'rs_pctile_1m_vt'   | 'rs_pctile_6m_vt'   | 'rs_pctile_12m_vt'
  | 'rs_pctile_1m_acwi' | 'rs_pctile_3m_acwi' | 'rs_pctile_6m_acwi' | 'rs_pctile_12m_acwi'
  | 'rs_pctile_1m_eem'  | 'rs_pctile_3m_eem'  | 'rs_pctile_6m_eem'  | 'rs_pctile_12m_eem'
  | 'rs_pctile_1m_gold' | 'rs_pctile_3m_gold' | 'rs_pctile_6m_gold' | 'rs_pctile_12m_gold'
  | 'realized_vol_63' | 'max_drawdown_252' | 'atr_21'
  | 'avg_volume_20' | 'volume_expansion' | 'effort_ratio_63'
  | 'ema_10_ratio' | 'ema_20_ratio' | 'extension_pct'
export function USETFScreener({ etfs }: { etfs: USETFRow[] }) {
  const [activeTab, setActiveTab]     = useState<CategoryTab>('All')
  const [search, setSearch]           = useState('')
  const [leaderOnly, setLeaderOnly]   = useState(false)
  const [sortCol, setSortCol]         = useState<SortCol>('rs_pctile_3m_vt')
  const [sortDir, setSortDir]         = useState<'asc' | 'desc'>('desc')
  const [visibleCols, setVisibleCols] = useState<OptColKey[]>(DEFAULT_OPT_COLS)
  const [colsOpen, setColsOpen]       = useState(false)
  const [page, setPage]               = useState(1)
  const colsRef                       = useRef<HTMLDivElement>(null)
  useEffect(() => { setVisibleCols(loadSavedCols()) }, [])
  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (colsRef.current && !colsRef.current.contains(e.target as Node)) setColsOpen(false)
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [])
  function toggleCol(key: OptColKey) {
    setVisibleCols(prev => {
      const next = prev.includes(key) ? prev.filter(k => k !== key) : [...prev, key]
      try { localStorage.setItem(LS_KEY, JSON.stringify(next)) } catch { /* ignore */ }
      return next
    })
  }
  function handleSort(col: SortCol) {
    if (sortCol === col) setSortDir(d => d === 'asc' ? 'desc' : 'asc')
    else { setSortCol(col); setSortDir('desc'); setPage(1) }
  }
  const isVisible = useCallback((k: OptColKey) => visibleCols.includes(k), [visibleCols])
  const tabCounts = useMemo(() => {
    const counts: Partial<Record<CategoryTab, number>> = { All: etfs.length }
    for (const e of etfs) {
      const tab = categoryTab(e)
      counts[tab] = (counts[tab] ?? 0) + 1
    }
    return counts
  }, [etfs])
  const filtered = useMemo(() => {
    let rows = etfs
    if (search.trim()) {
      const q = search.trim().toUpperCase()
      rows = rows.filter(r => r.ticker.includes(q))
    }
    if (activeTab !== 'All') rows = rows.filter(e => categoryTab(e) === activeTab)
    if (leaderOnly) rows = rows.filter(r => r.rs_state === 'Leader' || r.rs_state === 'Strong')
    return [...rows].sort((a, b) => {
      const dir = sortDir === 'asc' ? 1 : -1
      if (sortCol === 'ticker')       return dir * a.ticker.localeCompare(b.ticker)
      if (sortCol === 'etf_category') return dir * (a.etf_category ?? '').localeCompare(b.etf_category ?? '')
      if (sortCol === 'linked_sector') return dir * (a.linked_sector ?? '').localeCompare(b.linked_sector ?? '')
      if (sortCol === 'rs_state')     return dir * (stateRank(RS_ORDER, a.rs_state) - stateRank(RS_ORDER, b.rs_state))
      if (sortCol === 'momentum_state') return dir * (stateRank(MOM_ORDER, a.momentum_state) - stateRank(MOM_ORDER, b.momentum_state))
      type G = (r: USETFRow) => string | null
      const cols: Record<string, G> = {
        rs_pctile_3m_vt:    r => r.rs_pctile_3m_vt,
        rs_pctile_1m_vt:    r => r.rs_pctile_1m_vt,
        rs_pctile_6m_vt:    r => r.rs_pctile_6m_vt,
        rs_pctile_12m_vt:   r => r.rs_pctile_12m_vt,
        rs_pctile_1m_acwi:  r => r.rs_pctile_1m_acwi,
        rs_pctile_3m_acwi:  r => r.rs_pctile_3m_acwi,
        rs_pctile_6m_acwi:  r => r.rs_pctile_6m_acwi,
        rs_pctile_12m_acwi: r => r.rs_pctile_12m_acwi,
        rs_pctile_1m_eem:   r => r.rs_pctile_1m_eem,
        rs_pctile_3m_eem:   r => r.rs_pctile_3m_eem,
        rs_pctile_6m_eem:   r => r.rs_pctile_6m_eem,
        rs_pctile_12m_eem:  r => r.rs_pctile_12m_eem,
        rs_pctile_1m_gold:  r => r.rs_pctile_1m_gold,
        rs_pctile_3m_gold:  r => r.rs_pctile_3m_gold,
        rs_pctile_6m_gold:  r => r.rs_pctile_6m_gold,
        rs_pctile_12m_gold: r => r.rs_pctile_12m_gold,
        ret_1d:             r => r.ret_1d,
        ret_1m:             r => r.ret_1m,
        ret_1w:             r => r.ret_1w,
        ret_3m:             r => r.ret_3m,
        ret_6m:             r => r.ret_6m,
        ret_12m:            r => r.ret_12m,
        ret_12m_1m:         r => r.ret_12m_1m,
        vol_ratio_63:       r => r.vol_ratio_63,
        realized_vol_63:    r => r.realized_vol_63,
        max_drawdown_252:   r => r.max_drawdown_252,
        atr_21:             r => r.atr_21,
        avg_volume_20:      r => r.avg_volume_20,
        volume_expansion:   r => r.volume_expansion,
        effort_ratio_63:    r => r.effort_ratio_63,
        ema_10_ratio:       r => r.ema_10_ratio,
        ema_20_ratio:       r => r.ema_20_ratio,
        extension_pct:      r => r.extension_pct,
      }
      const getter = cols[sortCol]
      if (getter) {
        const av = numVal(getter(a))
        const bv = numVal(getter(b))
        if (av == null && bv == null) return 0
        if (av == null) return 1
        if (bv == null) return -1
        return dir * (av - bv)
      }
      return 0
    })
  }, [etfs, search, activeTab, leaderOnly, sortCol, sortDir])
  const PAGE_SIZE  = 50
  const totalPages = Math.ceil(filtered.length / PAGE_SIZE)
  const pageRows   = filtered.slice(0, page * PAGE_SIZE)
  const optVisible = OPT_COLS.filter(c => isVisible(c.key)).length
  const totalCols  = 10 + optVisible
  function SortIcon({ col }: { col: SortCol }) {
    if (sortCol !== col) return <ChevronUp className="w-3 h-3 opacity-20" />
    return sortDir === 'asc'
      ? <ChevronUp className="w-3 h-3 text-teal" />
      : <ChevronDown className="w-3 h-3 text-teal" />
  }
  function Th({ label, col, align = 'left' }: { label: string; col: SortCol; align?: 'left' | 'right' }) {
    const active = sortCol === col
    return (
      <th
        onClick={() => handleSort(col)}
        className={`px-3 py-2 font-sans text-[10px] font-semibold uppercase tracking-wider cursor-pointer hover:text-ink-secondary select-none whitespace-nowrap text-${align} ${active ? 'text-teal' : 'text-ink-tertiary'}`}
      >
        <span className={`inline-flex items-center gap-1 ${align === 'right' ? 'flex-row-reverse' : ''}`}>
          {label}
          <SortIcon col={col} />
        </span>
      </th>
    )
  }
  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center gap-0 border-b border-paper-rule">
        {TABS.map(tab => (
          <button
            key={tab}
            onClick={() => { setActiveTab(tab); setPage(1) }}
            className={`px-3 py-2 font-sans text-xs font-medium whitespace-nowrap transition-colors ${
              activeTab === tab
                ? 'border-b-2 border-teal text-ink-primary -mb-px'
                : 'text-ink-tertiary hover:text-ink-secondary'
            }`}
          >
            {tab}
            <span className="ml-1 font-mono text-[10px] opacity-60">{tabCounts[tab] ?? 0}</span>
          </button>
        ))}
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <button
          onClick={() => { setLeaderOnly(v => !v); setPage(1) }}
          className={`px-2.5 py-1 rounded-full font-sans text-[11px] font-medium transition-colors ${
            leaderOnly
              ? 'bg-teal text-white'
              : 'bg-paper-rule/30 text-ink-secondary hover:text-ink-primary hover:bg-paper-rule/50'
          }`}
        >
          Leader/Strong
        </button>
        <input
          type="text"
          value={search}
          onChange={e => { setSearch(e.target.value); setPage(1) }}
          placeholder="Search ticker…"
          className="font-mono text-xs text-ink-primary bg-paper border border-paper-rule rounded px-2 py-1 w-28 focus:outline-none focus:border-teal placeholder:text-ink-tertiary"
        />
        <div className="relative" ref={colsRef}>
          <button
            onClick={() => setColsOpen(o => !o)}
            className="flex items-center gap-1.5 px-2.5 py-1 rounded font-sans text-[11px] font-medium text-ink-secondary bg-paper border border-paper-rule hover:border-teal hover:text-teal transition-colors"
          >
            <SlidersHorizontal className="w-3 h-3" />
            Columns
            {optVisible > 0 && (
              <span className="font-mono text-[10px] bg-teal/10 text-teal px-1 rounded">+{optVisible}</span>
            )}
          </button>
          {colsOpen && (
            <div className="absolute top-full mt-1 left-0 z-30 w-52 bg-paper border border-paper-rule rounded shadow-lg p-3">
              <div className="flex items-center justify-between mb-2">
                <span className="font-sans text-[10px] uppercase tracking-wider text-ink-tertiary font-semibold">Optional Columns</span>
                <button onClick={() => setColsOpen(false)}>
                  <X className="w-3 h-3 text-ink-tertiary hover:text-ink-primary" />
                </button>
              </div>
              <div className="flex flex-col gap-1 max-h-64 overflow-y-auto">
                {OPT_COLS.map(c => (
                  <label key={c.key} className="flex items-center gap-2 cursor-pointer">
                    <input type="checkbox" checked={isVisible(c.key)} onChange={() => toggleCol(c.key)} className="accent-teal" />
                    <span className="font-sans text-xs text-ink-secondary">{c.label}</span>
                  </label>
                ))}
              </div>
            </div>
          )}
        </div>
        <span className="ml-auto font-sans text-xs text-ink-tertiary">{filtered.length} ETFs</span>
      </div>
      <div className="overflow-x-auto border border-paper-rule rounded-sm">
        <table className="w-full border-collapse">
          <thead>
            <tr className="border-b border-paper-rule sticky top-0 bg-paper z-10">
              <Th label="Ticker"   col="ticker" />
              <Th label="Category" col="etf_category" />
              <Th label="Sector"   col="linked_sector" />
              <Th label="RS State" col="rs_state" />
              <Th label="Mom"      col="momentum_state" />
              <th className="px-3 py-2 font-sans text-[10px] font-semibold uppercase tracking-wider text-ink-tertiary whitespace-nowrap">Risk</th>
              <Th label="RS 3M"    col="rs_pctile_3m_vt" align="right" />
              <Th label="3M Ret"   col="ret_3m"           align="right" />
              <Th label="1M Ret"   col="ret_1m"           align="right" />
              {isVisible('ret_1w')            && <Th label="1W Ret"  col="ret_1w"            align="right" />}
              {isVisible('ret_6m')            && <Th label="6M Ret"  col="ret_6m"            align="right" />}
              {isVisible('ret_12m')           && <Th label="12M Ret" col="ret_12m"           align="right" />}
              {isVisible('rs_pctile_1m_vt')   && <Th label="RS 1M"  col="rs_pctile_1m_vt"   align="right" />}
              {isVisible('rs_pctile_3m_acwi') && <Th label="RS ACWI" col="rs_pctile_3m_acwi" align="right" />}
              {isVisible('rs_pctile_3m_gold') && <Th label="RS Gold" col="rs_pctile_3m_gold" align="right" />}
              {isVisible('above_30w_ma') && (
                <th className="px-3 py-2 font-sans text-[10px] font-semibold uppercase tracking-wider text-ink-tertiary whitespace-nowrap text-right">30W MA</th>
              )}
              {isVisible('ema_10_ratio')      && <Th label="EMA10"   col="ema_10_ratio"      align="right" />}
              {isVisible('ema_20_ratio')      && <Th label="EMA20"   col="ema_20_ratio"      align="right" />}
              {isVisible('extension_pct')     && <Th label="Ext %"   col="extension_pct"     align="right" />}
              {isVisible('realized_vol_63')   && <Th label="Vol 63D" col="realized_vol_63"   align="right" />}
              {isVisible('max_drawdown_252')  && <Th label="Max DD"  col="max_drawdown_252"  align="right" />}
              {isVisible('atr_21')            && <Th label="ATR 21"  col="atr_21"            align="right" />}
              {isVisible('avg_volume_20')     && <Th label="Avg Vol" col="avg_volume_20"     align="right" />}
              {isVisible('volume_expansion')  && <Th label="Vol Exp" col="volume_expansion"  align="right" />}
              {isVisible('weinstein_gate_pass') && (
                <th className="px-3 py-2 font-sans text-[10px] font-semibold uppercase tracking-wider text-ink-tertiary whitespace-nowrap text-right">Weinstein</th>
              )}
            </tr>
          </thead>
          <tbody>
            {pageRows.length === 0 ? (
              <tr>
                <td colSpan={totalCols} className="px-6 py-10 text-center font-sans text-sm text-ink-secondary">
                  No ETFs match the current filters.
                </td>
              </tr>
            ) : (
              pageRows.map((row, i) => (
                <tr
                  key={row.ticker}
                  className={`border-b border-paper-rule hover:bg-paper-rule/20 transition-colors ${i % 2 !== 0 ? 'bg-paper-bg/50' : ''}`}
                >
                  <td className="px-3 py-2.5 whitespace-nowrap">
                    <div className="flex items-center gap-1">
                      <span className="font-mono text-sm font-semibold text-ink-primary">{row.ticker}</span>
                      {row.is_benchmark && (
                        <span className="font-sans text-[9px] bg-ink-tertiary/10 text-ink-tertiary px-1 rounded">BM</span>
                      )}
                    </div>
                  </td>
                  <td className="px-3 py-2.5 max-w-[120px]">
                    <span className="font-sans text-xs text-ink-secondary truncate block" title={row.etf_category ?? ''}>
                      {row.etf_category ?? '—'}
                    </span>
                  </td>
                  <td className="px-3 py-2.5">
                    <span className="font-sans text-xs text-ink-tertiary">{row.linked_sector ?? '—'}</span>
                  </td>
                  <td className="px-3 py-2.5"><StateChip value={row.rs_state}       colors={RS_STATE_COLORS}   /></td>
                  <td className="px-3 py-2.5"><StateChip value={row.momentum_state} colors={MOM_STATE_COLORS}  /></td>
                  <td className="px-3 py-2.5"><StateChip value={row.risk_state}     colors={RISK_STATE_COLORS} /></td>
                  <td className="px-3 py-2.5 text-right"><RSPctileBar value={row.rs_pctile_3m_vt} /></td>
                  <td className={`px-3 py-2.5 text-right font-mono text-xs tabular-nums ${fmtPctColor(row.ret_3m)}`}>{fmtPct(row.ret_3m)}</td>
                  <td className={`px-3 py-2.5 text-right font-mono text-xs tabular-nums ${fmtPctColor(row.ret_1m)}`}>{fmtPct(row.ret_1m)}</td>
                  {isVisible('ret_1w')  && <td className={`px-3 py-2.5 text-right font-mono text-xs tabular-nums ${fmtPctColor(row.ret_1w)}`}>{fmtPct(row.ret_1w)}</td>}
                  {isVisible('ret_6m')  && <td className={`px-3 py-2.5 text-right font-mono text-xs tabular-nums ${fmtPctColor(row.ret_6m)}`}>{fmtPct(row.ret_6m)}</td>}
                  {isVisible('ret_12m') && <td className={`px-3 py-2.5 text-right font-mono text-xs tabular-nums ${fmtPctColor(row.ret_12m)}`}>{fmtPct(row.ret_12m)}</td>}
                  {isVisible('rs_pctile_1m_vt')   && <td className="px-3 py-2.5 text-right font-mono text-xs tabular-nums text-ink-secondary">{fmtPctile(row.rs_pctile_1m_vt)}</td>}
                  {isVisible('rs_pctile_3m_acwi') && <td className="px-3 py-2.5 text-right font-mono text-xs tabular-nums text-ink-secondary">{fmtPctile(row.rs_pctile_3m_acwi)}</td>}
                  {isVisible('rs_pctile_3m_gold') && <td className="px-3 py-2.5 text-right font-mono text-xs tabular-nums text-ink-secondary">{fmtPctile(row.rs_pctile_3m_gold)}</td>}
                  {isVisible('above_30w_ma') && (
                    <td className="px-3 py-2.5 text-right">
                      <span className={`font-mono text-xs ${row.above_30w_ma === true ? 'text-signal-pos' : row.above_30w_ma === false ? 'text-signal-neg' : 'text-ink-tertiary'}`}>
                        {fmtBool(row.above_30w_ma)}
                      </span>
                    </td>
                  )}
                  {isVisible('ema_10_ratio')     && <td className="px-3 py-2.5 text-right font-mono text-xs tabular-nums text-ink-secondary">{fmtRatio(row.ema_10_ratio, '', 3)}</td>}
                  {isVisible('ema_20_ratio')     && <td className="px-3 py-2.5 text-right font-mono text-xs tabular-nums text-ink-secondary">{fmtRatio(row.ema_20_ratio, '', 3)}</td>}
                  {isVisible('extension_pct')    && <td className={`px-3 py-2.5 text-right font-mono text-xs tabular-nums ${fmtPctColor(row.extension_pct)}`}>{fmtPct(row.extension_pct)}</td>}
                  {isVisible('realized_vol_63')  && <td className="px-3 py-2.5 text-right font-mono text-xs tabular-nums text-ink-secondary">{fmtVolPct(row.realized_vol_63)}</td>}
                  {isVisible('max_drawdown_252') && <td className="px-3 py-2.5 text-right font-mono text-xs tabular-nums text-signal-neg">{row.max_drawdown_252 ? fmtPct(row.max_drawdown_252) : '—'}</td>}
                  {isVisible('atr_21')           && <td className="px-3 py-2.5 text-right font-mono text-xs tabular-nums text-ink-secondary">{row.atr_21 ? '$' + parseFloat(row.atr_21).toFixed(2) : '—'}</td>}
                  {isVisible('avg_volume_20')    && <td className="px-3 py-2.5 text-right font-mono text-xs tabular-nums text-ink-secondary">{fmtVol(row.avg_volume_20)}</td>}
                  {isVisible('volume_expansion') && <td className="px-3 py-2.5 text-right font-mono text-xs tabular-nums text-ink-secondary">{fmtRatio(row.volume_expansion, 'x', 1)}</td>}
                  {isVisible('weinstein_gate_pass') && (
                    <td className="px-3 py-2.5 text-right">
                      <span className={`font-mono text-xs ${row.weinstein_gate_pass === true ? 'text-signal-pos' : row.weinstein_gate_pass === false ? 'text-signal-neg' : 'text-ink-tertiary'}`}>
                        {fmtBool(row.weinstein_gate_pass)}
                      </span>
                    </td>
                  )}
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
      {page < totalPages && (
        <div className="flex justify-center pt-1">
          <button
            onClick={() => setPage(p => p + 1)}
            className="px-4 py-1.5 font-sans text-xs font-medium text-ink-secondary bg-paper border border-paper-rule rounded hover:border-teal hover:text-teal transition-colors"
          >
            Show more ({filtered.length - pageRows.length} remaining)
          </button>
        </div>
      )}
    </div>
  )
}
