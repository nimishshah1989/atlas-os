'use client'
import { useMemo, useState } from 'react'
import type { StateHistoryRow, MetricHistoryRow } from '@/lib/queries/stocks'
import type { StockRowWithSector } from '@/lib/queries/stocks'
import { pct, pctColor } from '@/lib/stock-formatters'

const RS_COLOR: Record<string, string> = {
  Leader:        '#2F6B43',
  Strong:        '#4CAF78',
  Consolidating: '#1D9E75',
  Emerging:      '#d97706',
  Average:       '#94a3b8',
  Weak:          '#ef6644',
  Laggard:       '#B0492C',
}

const MOM_COLOR: Record<string, string> = {
  Accelerating:  '#2F6B43',
  Improving:     '#4CAF78',
  Flat:          '#94a3b8',
  Deteriorating: '#ef6644',
  Collapsing:    '#B0492C',
}

const RISK_COLOR: Record<string, string> = {
  Low:          '#2F6B43',
  Normal:       '#94a3b8',
  Elevated:     '#d97706',
  High:         '#B0492C',
  'Below Trend':'#7c3aed',
}

const VOL_COLOR: Record<string, string> = {
  Accumulation:         '#2F6B43',
  'Steady-Buying':      '#4CAF78',
  Neutral:              '#94a3b8',
  Distribution:         '#ef6644',
  'Heavy Distribution': '#B0492C',
}

const ROWS: {
  key: keyof Pick<StateHistoryRow, 'rs_state' | 'momentum_state' | 'risk_state' | 'volume_state'>
  label: string
  colorMap: Record<string, string>
}[] = [
  { key: 'rs_state',       label: 'RS State',  colorMap: RS_COLOR },
  { key: 'momentum_state', label: 'Momentum',  colorMap: MOM_COLOR },
  { key: 'risk_state',     label: 'Risk',       colorMap: RISK_COLOR },
  { key: 'volume_state',   label: 'Volume',     colorMap: VOL_COLOR },
]

export function StateHeatmap({ history }: { history: StateHistoryRow[] }) {
  const [tooltip, setTooltip] = useState<{ text: string; x: number; y: number } | null>(null)

  const { dates, dateMap } = useMemo(() => {
    const map = new Map<string, StateHistoryRow>()
    const dateSet = new Set<string>()
    for (const row of history) {
      const d = row.date instanceof Date
        ? row.date.toISOString().slice(0, 10)
        : String(row.date).slice(0, 10)
      dateSet.add(d)
      map.set(d, row)
    }
    return { dates: [...dateSet].sort(), dateMap: map }
  }, [history])

  const monthLabels = useMemo(() => {
    const seen = new Set<string>()
    return dates.map(d => {
      const m = d.slice(0, 7)
      if (seen.has(m)) return null
      seen.add(m)
      const dt = new Date(d)
      return dt.toLocaleDateString('en-IN', { month: 'short', year: '2-digit' })
    })
  }, [dates])

  const CELL_W = 6
  const CELL_H = 20
  const CELL_GAP = 1
  const labelW = 90

  if (history.length === 0) {
    return (
      <p className="font-sans text-xs text-ink-tertiary py-4">
        No state history available for this range.
      </p>
    )
  }

  const totalW = dates.length * (CELL_W + CELL_GAP) + labelW

  return (
    <div className="relative overflow-x-auto pb-1">
      <div style={{ minWidth: totalW }}>
        {/* Month labels row */}
        <div className="flex mb-1" style={{ paddingLeft: labelW }}>
          {dates.map((d, i) => (
            <div
              key={d}
              style={{ width: CELL_W + CELL_GAP, flexShrink: 0, position: 'relative' }}
            >
              {monthLabels[i] && (
                <span
                  className="absolute font-sans text-[9px] font-medium text-ink-tertiary whitespace-nowrap"
                  style={{ left: 0, top: 0 }}
                >
                  {monthLabels[i]}
                </span>
              )}
            </div>
          ))}
        </div>
        {/* State rows */}
        {ROWS.map(row => {
          const latestState = dateMap.get(dates[dates.length - 1])?.[row.key] ?? null
          return (
            <div key={row.key} className="flex items-center mb-1.5">
              <div
                className="font-sans text-[10px] font-medium text-ink-secondary shrink-0 pr-2 text-right"
                style={{ width: labelW }}
              >
                <span>{row.label}</span>
                {latestState && (
                  <span
                    className="ml-1 font-sans text-[9px] font-semibold"
                    style={{ color: row.colorMap[latestState] ?? '#94a3b8' }}
                  >
                    · {latestState}
                  </span>
                )}
              </div>
              <div className="flex gap-[1px]">
                {dates.map(d => {
                  const stateRow = dateMap.get(d)
                  const state = stateRow?.[row.key] ?? null
                  const color = state ? (row.colorMap[state] ?? '#94a3b8') : '#e2e8f0'
                  return (
                    <div
                      key={d}
                      style={{
                        width: CELL_W,
                        height: CELL_H,
                        background: color,
                        opacity: state ? 0.88 : 0.15,
                        flexShrink: 0,
                        cursor: state ? 'pointer' : 'default',
                        borderRadius: 2,
                      }}
                      onMouseEnter={e => {
                        if (!state) return
                        const rect = (e.currentTarget as HTMLElement).getBoundingClientRect()
                        setTooltip({ text: `${d}: ${state}`, x: rect.left + rect.width / 2, y: rect.top - 6 })
                      }}
                      onMouseLeave={() => setTooltip(null)}
                    />
                  )
                })}
              </div>
            </div>
          )
        })}
      </div>
      {tooltip && (
        <div
          role="tooltip"
          className="fixed z-[9999] px-2.5 py-1.5 bg-paper border border-paper-rule rounded-sm shadow-md font-sans text-[11px] text-ink-secondary pointer-events-none -translate-x-1/2 -translate-y-full whitespace-nowrap"
          style={{ left: tooltip.x, top: tooltip.y }}
        >
          {tooltip.text}
        </div>
      )}
    </div>
  )
}

function ReturnRow({ label, value }: { label: string; value: string | null }) {
  return (
    <tr className="border-b border-paper-rule last:border-0">
      <td className="py-2 pr-8 font-sans text-xs text-ink-secondary">{label}</td>
      <td className={`py-2 text-right font-mono text-xs tabular-nums font-semibold ${pctColor(value)}`}>
        {pct(value)}
      </td>
    </tr>
  )
}

export function StockHistoryTab({
  stock,
  stateHistory,
  metricHistory: _metricHistory,
}: {
  stock: StockRowWithSector
  stateHistory: StateHistoryRow[]
  metricHistory: MetricHistoryRow[]
}) {
  return (
    <div className="px-6 py-6 space-y-6">
      {/* State heatmap */}
      <div>
        <div className="font-sans text-[10px] text-ink-tertiary uppercase tracking-wider mb-3">
          State History — 6M
        </div>
        <StateHeatmap history={stateHistory} />
      </div>

      {/* Returns table */}
      <div className="border-t border-paper-rule pt-5">
        <div className="font-sans text-[10px] text-ink-tertiary uppercase tracking-wider mb-3">
          Returns
        </div>
        <table className="border-collapse">
          <tbody>
            <ReturnRow label="1 Month" value={stock.ret_1m} />
            <ReturnRow label="3 Months" value={stock.ret_3m} />
            <ReturnRow label="6 Months" value={stock.ret_6m} />
          </tbody>
        </table>
      </div>
    </div>
  )
}
