// frontend/src/components/sectors/StocksTable.tsx
'use client'
import { useState, useMemo, useRef } from 'react'
import { ChevronUp, ChevronDown, CheckCircle2, Info } from 'lucide-react'
import type { StockRow } from '@/lib/queries/sector-deep-dive'
import type { TimeRange } from '@/lib/time-range'

type SortKey =
  | 'symbol' | 'rs_3m_nifty500' | 'rs_pctile_3m' | 'ret_1m' | 'ret_3m' | 'ret_6m'
  | 'position_size_pct' | 'rs_3m_tier_gold'

function pct(v: string | null, digits = 1, signed = true): string {
  if (v == null) return '—'
  const n = parseFloat(v) * 100
  const sign = signed && n >= 0 ? '+' : ''
  return `${sign}${n.toFixed(digits)}%`
}

function pctColor(v: string | null): string {
  if (v == null) return 'text-ink-tertiary'
  return parseFloat(v) >= 0 ? 'text-signal-pos' : 'text-signal-neg'
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
          className="fixed z-[9999] w-60 px-2.5 py-2 bg-paper border border-paper-rule rounded-sm shadow-md font-sans text-[11px] text-ink-secondary leading-relaxed normal-case tracking-normal font-normal pointer-events-none whitespace-normal -translate-x-1/2 -translate-y-full"
          style={{ left: pos.x, top: pos.y }}
        >
          {text}
        </span>
      )}
    </span>
  )
}

// Max possible deploy factor: Risk-On(1.0) × Low-risk(1.2) = 1.2
const DEPLOY_MAX = 1.2

function PosSizeBar({ value }: { value: string | null }) {
  if (value == null) return <span className="font-mono text-xs text-ink-tertiary">—</span>
  const n = parseFloat(value)
  const display = `${(n * 100).toFixed(0)}%`
  const widthPct = Math.min(100, (n / DEPLOY_MAX) * 100)
  const color = n >= 0.7 ? '#2F6B43' : n >= 0.35 ? '#1D9E75' : n > 0 ? '#94a3b8' : '#ef4444'
  return (
    <div className="flex items-center gap-2">
      <div className="w-12 h-1.5 bg-paper-rule rounded-full overflow-hidden">
        <div className="h-full rounded-full" style={{ width: `${widthPct}%`, background: color }} />
      </div>
      <span className="font-mono text-xs tabular-nums" style={{ color }}>{display}</span>
    </div>
  )
}

function StateChip({ rs, mom }: { rs: string | null; mom: string | null }) {
  if (!rs) return <span className="font-sans text-[10px] text-ink-tertiary">—</span>
  const isOver = rs === 'Overweight_RS'
  const tone = isOver
    ? mom === 'Improving' ? 'bg-signal-pos/15 text-signal-pos'
      : mom === 'Deteriorating' ? 'bg-signal-warn/15 text-signal-warn'
      : 'bg-teal/15 text-teal'
    : 'bg-signal-neg/15 text-signal-neg'
  const label = isOver
    ? mom === 'Improving' ? '↑ Strong'
      : mom === 'Deteriorating' ? '↓ Fading'
      : '→ Stable'
    : '↓ Weak'
  return (
    <span className={`inline-flex items-center px-1.5 py-0.5 rounded-[2px] font-sans text-[10px] font-semibold ${tone}`}>
      {label}
    </span>
  )
}

function QualityChip({ ema, wein }: { ema: boolean | null; wein: boolean | null }) {
  if (ema === true && wein === true)
    return <span className="inline-flex items-center px-1.5 py-0.5 rounded-[2px] font-sans text-[10px] font-semibold bg-signal-pos/15 text-signal-pos">▲ Strong</span>
  if (ema === true)
    return <span className="inline-flex items-center px-1.5 py-0.5 rounded-[2px] font-sans text-[10px] font-semibold bg-signal-warn/15 text-signal-warn">≈ Partial</span>
  return <span className="font-sans text-[10px] text-ink-tertiary">—</span>
}

export function StocksTable({
  stocks,
  unit,
  activeRange,
}: {
  stocks: StockRow[]
  unit: 'inr' | 'gold'
  activeRange?: TimeRange
}) {
  const [sortKey, setSortKey] = useState<SortKey>('rs_pctile_3m')
  const [asc, setAsc] = useState(false)

  const activeRetCol: SortKey | null =
    activeRange === '1M' ? 'ret_1m' :
    activeRange === '3M' ? 'ret_3m' :
    activeRange === '6M' ? 'ret_6m' : null

  function handleSort(key: SortKey) {
    if (sortKey === key) setAsc(a => !a)
    else { setSortKey(key); setAsc(false) }
  }

  const sorted = useMemo(() => {
    return [...stocks].sort((a, b) => {
      let cmp = 0
      if (sortKey === 'symbol') {
        cmp = a.symbol.localeCompare(b.symbol)
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
  }, [stocks, sortKey, asc])

  function SortIcon({ k }: { k: SortKey }) {
    if (sortKey !== k) return <ChevronUp className="w-3 h-3 opacity-20" />
    return asc ? <ChevronUp className="w-3 h-3 text-teal" /> : <ChevronDown className="w-3 h-3 text-teal" />
  }

  function Th({ label, k, align = 'left', tip }: { label: string; k: SortKey; align?: 'left' | 'right'; tip?: string }) {
    const isActive = k === activeRetCol
    return (
      <th
        onClick={() => handleSort(k)}
        className={`px-3 py-2 font-sans text-[10px] font-semibold uppercase tracking-wider cursor-pointer hover:text-ink-secondary select-none whitespace-nowrap text-${align} ${isActive ? 'text-teal underline underline-offset-2 decoration-teal/50' : 'text-ink-tertiary'}`}
      >
        <span className={`inline-flex items-center gap-1 ${align === 'right' ? 'flex-row-reverse' : ''}`}>
          {label}
          {tip && <ColTip text={tip} />}
          <SortIcon k={k} />
        </span>
      </th>
    )
  }

  if (stocks.length === 0) {
    return (
      <div className="px-6 py-12 border border-paper-rule rounded-sm text-center">
        <p className="font-sans text-sm text-ink-secondary mb-1">No stocks classified to this sector.</p>
        <p className="font-sans text-xs text-ink-tertiary">
          The sector exists in the master table but has no constituents in the current universe.
        </p>
      </div>
    )
  }

  const rsColumnKey = unit === 'gold' ? 'rs_3m_tier_gold' : 'rs_3m_nifty500'
  const rsColumnLabel = unit === 'gold' ? 'RS 3M (Gold)' : 'RS 3M'

  return (
    <div className="overflow-x-auto border border-paper-rule rounded-sm">
      <table className="w-full border-collapse">
        <thead>
          <tr className="border-b border-paper-rule bg-paper">
            <Th label="Symbol" k="symbol" />
            <th className="px-3 py-2 text-left font-sans text-[10px] font-semibold uppercase tracking-wider text-ink-tertiary whitespace-nowrap">
              State
            </th>
            <Th label="1M" k="ret_1m" align="right" />
            <Th label="3M" k="ret_3m" align="right" />
            <Th label="6M" k="ret_6m" align="right" />
            <Th label={rsColumnLabel} k={rsColumnKey} align="right" />
            <Th label="RS Pctile" k="rs_pctile_3m" align="right"
              tip="Percentile rank within the stock's own RS tier — how it compares to peers at the same level. 90th = top 10% vs peers. Higher is better." />
            <th className="px-3 py-2 text-right font-sans text-[10px] font-semibold uppercase tracking-wider text-ink-tertiary whitespace-nowrap">
              <span className="inline-flex items-center gap-0.5">
                Quality
                <ColTip text="Technical setup quality. Strong = price near 20-day high (EMA-10 confirmation) AND Weinstein stage pass. Partial = EMA-10 criterion met only. — = neither criterion met." />
              </span>
            </th>
            <Th label="Deploy %" k="position_size_pct" align="right"
              tip="Position sizing deployment factor (base × market multiplier × risk multiplier). 100% = full standard position in optimal conditions (Risk-On, Low risk). Scales down in Cautious/Risk-Off markets and Elevated/High risk. 0% = avoid entirely." />
            <th className="px-3 py-2 text-center font-sans text-[10px] font-semibold uppercase tracking-wider text-ink-tertiary whitespace-nowrap">
              <span className="inline-flex items-center gap-0.5">
                Invest
                <ColTip text="Passes all 6 investability gates: (1) Market regime not Risk-Off, (2) Sector Overweight or Neutral, (3) Stock RS state Overweight, (4) Momentum not Deteriorating, (5) Risk state not High or Below Trend, (6) Volume not Distribution. All 6 must pass. In Cautious or Risk-Off markets, very few or no stocks qualify." />
              </span>
            </th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((row, i) => (
            <tr
              key={row.instrument_id}
              className={`border-b border-paper-rule last:border-0 hover:bg-paper-rule/20 transition-colors ${i % 2 === 0 ? '' : 'bg-paper-rule/5'}`}
            >
              <td className="px-3 py-2.5 whitespace-nowrap">
                <div className="font-sans text-xs font-semibold text-ink-primary">{row.symbol}</div>
                <div className="font-sans text-[10px] text-ink-tertiary truncate max-w-[200px]" title={row.company_name}>
                  {row.company_name}
                </div>
              </td>
              <td className="px-3 py-2.5">
                <StateChip rs={row.rs_state} mom={row.momentum_state} />
              </td>
              <td className={`px-3 py-2.5 text-right font-mono text-xs tabular-nums ${pctColor(row.ret_1m)}`}>{pct(row.ret_1m)}</td>
              <td className={`px-3 py-2.5 text-right font-mono text-xs tabular-nums ${pctColor(row.ret_3m)}`}>{pct(row.ret_3m)}</td>
              <td className={`px-3 py-2.5 text-right font-mono text-xs tabular-nums ${pctColor(row.ret_6m)}`}>{pct(row.ret_6m)}</td>
              <td className={`px-3 py-2.5 text-right font-mono text-xs tabular-nums ${pctColor(row[rsColumnKey])}`}>
                {pct(row[rsColumnKey])}
              </td>
              <td className="px-3 py-2.5 text-right font-mono text-xs tabular-nums text-ink-secondary">
                {row.rs_pctile_3m != null ? (parseFloat(row.rs_pctile_3m) * 100).toFixed(0) : '—'}
              </td>
              <td className="px-3 py-2.5 text-right">
                <div className="flex justify-end">
                  <QualityChip ema={row.ema_10_at_20d_high} wein={row.weinstein_gate_pass} />
                </div>
              </td>
              <td className="px-3 py-2.5 text-right">
                <div className="flex justify-end"><PosSizeBar value={row.position_size_pct} /></div>
              </td>
              <td className="px-3 py-2.5 text-center">
                {row.is_investable ? (
                  <CheckCircle2 className="w-3.5 h-3.5 text-signal-pos mx-auto" />
                ) : row.market_gate == null ? (
                  <span className="font-sans text-[10px] text-ink-tertiary">—</span>
                ) : !row.market_gate ? (
                  <span className="font-sans text-[10px] text-signal-neg" title="Market regime is Risk-Off">mkt off</span>
                ) : !row.sector_gate ? (
                  <span className="font-sans text-[10px] text-signal-warn" title="Sector is Underweight or Avoid">sector ↓</span>
                ) : !row.strength_gate ? (
                  <span className="font-sans text-[10px] text-signal-neg" title="RS state is Underweight — stock lagging peers">RS weak</span>
                ) : !row.direction_gate ? (
                  <span className="font-sans text-[10px] text-ink-tertiary" title="Momentum is not Improving or Accelerating">mom flat</span>
                ) : !row.risk_gate ? (
                  <span className="font-sans text-[10px] text-signal-warn" title="Risk state is High or Below Trend">risk ↑</span>
                ) : (
                  <span className="font-sans text-[10px] text-signal-warn" title="Volume pattern is Distribution">dist vol</span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
