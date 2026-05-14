'use client'
import { useState } from 'react'
import Link from 'next/link'
import { IndicatorChart } from '@/components/regime/IndicatorChart'
import type { USSectorRow, USSectorStockRow, USSectorMetricHistoryRow } from '@/lib/queries/us-sectors'
import type { TimeRange } from '@/lib/time-range'
import { rsStateColor } from '@/lib/chart-colors'

type Tab = 'overview' | 'stocks'

function pctStr(v: string | null, scale = 100): string {
  if (v == null) return '—'
  const n = parseFloat(v) * scale
  return `${n >= 0 ? '+' : ''}${n.toFixed(1)}%`
}

function rawPct(v: string | null, digits = 0): string {
  if (v == null) return '—'
  return `${(parseFloat(v) * 100).toFixed(digits)}`
}

function dateStr(d: string): string {
  return d.slice(0, 10)
}

function RSStateChip({ state }: { state: string | null }) {
  if (!state) return <span className="text-ink-tertiary font-mono text-[10px]">—</span>
  const color = rsStateColor(state)
  return (
    <span
      className="font-sans text-[9px] font-semibold px-1.5 py-0.5 rounded"
      style={{ background: color + '22', color }}
    >
      {state}
    </span>
  )
}

function StocksTab({ sectorName, stocks }: { sectorName: string; stocks: USSectorStockRow[] }) {
  if (stocks.length === 0) {
    return (
      <div className="px-6 py-8 text-center font-sans text-sm text-ink-tertiary">
        No stocks available for this sector.
      </div>
    )
  }
  return (
    <div className="px-6 py-4 overflow-x-auto">
      <table className="w-full border-collapse min-w-[900px]">
        <thead>
          <tr className="border-b border-paper-rule">
            <th className="py-2 px-2 font-sans text-[10px] font-medium text-ink-tertiary uppercase tracking-wide text-left">Ticker</th>
            <th className="py-2 px-2 font-sans text-[10px] font-medium text-ink-tertiary uppercase tracking-wide text-left">Name</th>
            <th className="py-2 px-2 font-sans text-[10px] font-medium text-ink-tertiary uppercase tracking-wide text-left">RS State</th>
            <th className="py-2 px-2 font-sans text-[10px] font-medium text-ink-tertiary uppercase tracking-wide text-right">RS Pctile</th>
            <th className="py-2 px-2 font-sans text-[10px] font-medium text-ink-tertiary uppercase tracking-wide text-right">1M</th>
            <th className="py-2 px-2 font-sans text-[10px] font-medium text-ink-tertiary uppercase tracking-wide text-right">3M</th>
            <th className="py-2 px-2 font-sans text-[10px] font-medium text-ink-tertiary uppercase tracking-wide text-right">6M</th>
            <th className="py-2 px-2 font-sans text-[10px] font-medium text-ink-tertiary uppercase tracking-wide text-center">30W</th>
            <th className="py-2 px-2 font-sans text-[10px] font-medium text-ink-tertiary uppercase tracking-wide text-right">Vol 63D</th>
            <th className="py-2 px-2 font-sans text-[10px] font-medium text-ink-tertiary uppercase tracking-wide text-right">Drawdown</th>
          </tr>
        </thead>
        <tbody>
          {stocks.map(s => {
            const ret1m = parseFloat(s.ret_1m ?? '0') * 100
            const ret3m = parseFloat(s.ret_3m ?? '0') * 100
            const ret6m = parseFloat(s.ret_6m ?? '0') * 100
            const rsPctile = s.rs_pctile_3m_vt != null ? (parseFloat(s.rs_pctile_3m_vt) * 100).toFixed(0) : '—'
            const vol = s.realized_vol_63 != null ? (parseFloat(s.realized_vol_63) * 100).toFixed(1) + '%' : '—'
            const dd = s.max_drawdown_252 != null ? (parseFloat(s.max_drawdown_252) * 100).toFixed(1) + '%' : '—'
            return (
              <tr key={s.ticker} className="border-b border-paper-rule/40 hover:bg-paper-rule/10 transition-colors">
                <td className="py-2 px-2">
                  <Link
                    href={`/us/stocks/${encodeURIComponent(s.ticker)}`}
                    className="font-mono text-xs font-semibold text-teal hover:underline"
                  >
                    {s.ticker}
                  </Link>
                </td>
                <td className="py-2 px-2 font-sans text-xs text-ink-secondary max-w-[180px] truncate">
                  {s.company_name ?? '—'}
                </td>
                <td className="py-2 px-2">
                  <RSStateChip state={s.rs_state} />
                </td>
                <td className="py-2 px-2 font-mono text-xs tabular-nums text-right text-ink-primary">{rsPctile}</td>
                <td className={`py-2 px-2 font-mono text-xs tabular-nums text-right ${s.ret_1m != null ? ret1m >= 0 ? 'text-signal-pos' : 'text-signal-neg' : 'text-ink-tertiary'}`}>
                  {s.ret_1m != null ? `${ret1m >= 0 ? '+' : ''}${ret1m.toFixed(1)}%` : '—'}
                </td>
                <td className={`py-2 px-2 font-mono text-xs tabular-nums text-right ${s.ret_3m != null ? ret3m >= 0 ? 'text-signal-pos' : 'text-signal-neg' : 'text-ink-tertiary'}`}>
                  {s.ret_3m != null ? `${ret3m >= 0 ? '+' : ''}${ret3m.toFixed(1)}%` : '—'}
                </td>
                <td className={`py-2 px-2 font-mono text-xs tabular-nums text-right ${s.ret_6m != null ? ret6m >= 0 ? 'text-signal-pos' : 'text-signal-neg' : 'text-ink-tertiary'}`}>
                  {s.ret_6m != null ? `${ret6m >= 0 ? '+' : ''}${ret6m.toFixed(1)}%` : '—'}
                </td>
                <td className="py-2 px-2 text-center">
                  {s.above_30w_ma == null
                    ? <span className="text-ink-tertiary">—</span>
                    : <span className={`w-2 h-2 rounded-full inline-block ${s.above_30w_ma ? 'bg-signal-pos' : 'bg-signal-neg'}`} />
                  }
                </td>
                <td className="py-2 px-2 font-mono text-xs tabular-nums text-right text-ink-secondary">{vol}</td>
                <td className={`py-2 px-2 font-mono text-xs tabular-nums text-right ${s.max_drawdown_252 != null ? parseFloat(s.max_drawdown_252) < -0.15 ? 'text-signal-neg' : 'text-ink-secondary' : 'text-ink-tertiary'}`}>
                  {dd}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

function OverviewTab({
  sector,
  sectorName,
  metricHistory,
  range,
}: {
  sector: USSectorRow
  sectorName: string
  metricHistory: USSectorMetricHistoryRow[]
  range: TimeRange
}) {
  const rsPctileData = metricHistory.map(r => ({
    date: dateStr(r.date),
    value: r.avg_rs_pctile_3m_vt != null ? parseFloat(r.avg_rs_pctile_3m_vt) : null,
  }))
  const ret3mData = metricHistory.map(r => ({
    date: dateStr(r.date),
    value: r.avg_ret_3m != null ? parseFloat(r.avg_ret_3m) : null,
  }))
  const partData = metricHistory.map(r => ({
    date: dateStr(r.date),
    value: r.participation_rs != null ? parseFloat(r.participation_rs) / 100 : null,
  }))
  const latest = metricHistory[metricHistory.length - 1]
  const rsPctile = parseFloat(sector.avg_rs_pctile_3m_vt ?? '0')
  const partRs = parseFloat(sector.participation_rs ?? '0')

  return (
    <div className="px-6 py-6 space-y-6">
      {/* Summary stats */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {[
          { label: 'RS Pctile (3M vs VT)', value: (rsPctile * 100).toFixed(0), color: rsPctile >= 0.6 ? 'text-signal-pos' : rsPctile >= 0.4 ? 'text-signal-warn' : 'text-signal-neg' },
          { label: 'Leader + Strong', value: `${sector.rs_state_leader + sector.rs_state_strong} stocks`, color: 'text-ink-primary' },
          { label: 'Participation RS', value: `${partRs.toFixed(0)}%`, color: partRs >= 50 ? 'text-signal-pos' : partRs >= 30 ? 'text-signal-warn' : 'text-signal-neg' },
          { label: 'Above 30W MA', value: `${sector.participation_30w != null ? (parseFloat(sector.participation_30w)).toFixed(0) : '—'}%`, color: 'text-ink-primary' },
        ].map(t => (
          <div key={t.label} className="border border-paper-rule rounded-sm px-4 py-3">
            <div className="font-sans text-[10px] font-semibold text-ink-tertiary uppercase tracking-wider mb-1">{t.label}</div>
            <div className={`font-mono text-sm font-semibold ${t.color}`}>{t.value}</div>
          </div>
        ))}
      </div>

      {/* Range selector */}
      <div className="flex items-center justify-between">
        <div className="font-sans text-[10px] font-semibold text-ink-tertiary uppercase tracking-wider">Metric History</div>
        <div className="flex items-center gap-0 border border-paper-rule rounded-sm overflow-hidden">
          {(['1M', '3M', '6M', '1Y'] as TimeRange[]).map(r => (
            <Link
              key={r}
              href={`/us/sectors/${encodeURIComponent(sectorName)}?range=${r}`}
              className={`px-2.5 py-0.5 font-sans text-[11px] font-medium transition-colors ${
                range === r ? 'bg-teal text-white' : 'text-ink-secondary hover:bg-paper-rule/30'
              }`}
            >
              {r}
            </Link>
          ))}
        </div>
      </div>

      {metricHistory.length === 0 ? (
        <p className="font-sans text-xs text-ink-tertiary">No metric history available for this range.</p>
      ) : (
        <div className="space-y-5">
          <IndicatorChart
            title="Avg RS Percentile (3M vs VT)"
            description="Average RS percentile of stocks in this sector vs VT benchmark over 3 months. Higher = sector outperforming global market."
            currentValue={rawPct(latest?.avg_rs_pctile_3m_vt)}
            isBullish={latest?.avg_rs_pctile_3m_vt != null ? parseFloat(latest.avg_rs_pctile_3m_vt) >= 0.5 : null}
            data={rsPctileData}
            refLine={0.5}
            refLabel="50%"
            variant="area"
            yFormat="pct"
          />
          <IndicatorChart
            title="Avg 3M Return"
            description="Average 3-month price return across active stocks in this sector."
            currentValue={pctStr(latest?.avg_ret_3m)}
            isBullish={latest?.avg_ret_3m != null ? parseFloat(latest.avg_ret_3m) >= 0 : null}
            data={ret3mData}
            refLine={0}
            refLabel="0"
            variant="area"
            yFormat="pct"
          />
          <IndicatorChart
            title="Participation (Leader + Strong)"
            description="% of stocks in Leader or Strong RS state. High breadth = broad sector health, not just a few large-caps pulling the average."
            currentValue={rawPct(latest?.participation_rs) + '%'}
            isBullish={latest?.participation_rs != null ? parseFloat(latest.participation_rs) >= 35 : null}
            data={partData}
            refLine={0.35}
            refLabel="35% threshold"
            variant="area"
            yFormat="pct"
          />
        </div>
      )}
    </div>
  )
}

export function USSectorDetailTabs({
  sectorName,
  sector,
  stocks,
  metricHistory,
  activeTab: initialTab,
  range,
}: {
  sectorName: string
  sector: USSectorRow
  stocks: USSectorStockRow[]
  metricHistory: USSectorMetricHistoryRow[]
  activeTab: 'overview' | 'stocks'
  range: TimeRange
}) {
  const [tab, setTab] = useState<Tab>(initialTab)

  return (
    <div>
      <div className="px-6 border-b border-paper-rule">
        <div className="flex items-center gap-0">
          {(['overview', 'stocks'] as Tab[]).map(t => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`px-4 py-3 font-sans text-sm capitalize transition-colors border-b-2 -mb-px ${
                tab === t
                  ? 'border-teal text-ink-primary font-medium'
                  : 'border-transparent text-ink-tertiary hover:text-ink-secondary'
              }`}
            >
              {t === 'overview' ? 'Overview' : `Stocks (${stocks.length})`}
            </button>
          ))}
        </div>
      </div>

      {tab === 'overview' && (
        <OverviewTab
          sector={sector}
          sectorName={sectorName}
          metricHistory={metricHistory}
          range={range}
        />
      )}
      {tab === 'stocks' && (
        <StocksTab sectorName={sectorName} stocks={stocks} />
      )}
    </div>
  )
}
