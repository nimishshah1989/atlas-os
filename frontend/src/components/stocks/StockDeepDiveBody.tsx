'use client'
import type { ReactNode } from 'react'
import { IndicatorChart } from '@/components/regime/IndicatorChart'
import type { MetricHistoryRow, StateHistoryRow, StockRowWithSector } from '@/lib/queries/stocks'
import {
  interpretRSPctile,
  interpretMomentumState,
  interpretWeinsteinGate,
  interpretEMARatio,
  interpret3MReturn,
  pct,
  pctColor,
} from '@/lib/stock-formatters'
import { StateHeatmap } from './StockHistoryTab'
import { StateJourneyCompact } from '@/components/ui/StateJourneyCompact'

function Commentary({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="flex flex-col justify-center h-full px-5 py-4 bg-paper-rule/5 border border-paper-rule/40 rounded-sm">
      <div className="font-sans text-[10px] font-semibold text-ink-tertiary uppercase tracking-wider mb-2">
        {title}
      </div>
      <div className="font-sans text-xs text-ink-secondary leading-relaxed space-y-2">
        {children}
      </div>
    </div>
  )
}

function dateStr(d: Date | string): string {
  return d instanceof Date ? d.toISOString().slice(0, 10) : String(d).slice(0, 10)
}

function pctStr(v: string | null, digits = 1): string {
  if (v == null) return '—'
  const n = parseFloat(v) * 100
  return `${n >= 0 ? '+' : ''}${n.toFixed(digits)}%`
}

function rawPct(v: string | null, digits = 0): string {
  if (v == null) return '—'
  return `${(parseFloat(v) * 100).toFixed(digits)}`
}

function SectionLabel({ children }: { children: ReactNode }) {
  return (
    <div className="font-sans text-[10px] text-ink-tertiary uppercase tracking-wider">
      {children}
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

export function StockDeepDiveBody({
  stock,
  metricHistory,
  stateHistory,
}: {
  stock: StockRowWithSector
  metricHistory: MetricHistoryRow[]
  stateHistory: StateHistoryRow[]
}) {
  const latest = metricHistory[metricHistory.length - 1]

  const rsPctileData = metricHistory.map(r => ({
    date: dateStr(r.date),
    value: r.rs_pctile_3m != null ? parseFloat(r.rs_pctile_3m) : null,
  }))
  const ret3mData = metricHistory.map(r => ({
    date: dateStr(r.date),
    value: r.ret_3m != null ? parseFloat(r.ret_3m) : null,
  }))
  const emaData = metricHistory.map(r => ({
    date: dateStr(r.date),
    value: r.ema_10_ratio != null ? parseFloat(r.ema_10_ratio) : null,
  }))

  return (
    <div className="px-6 py-6 space-y-8">
      {/* State journey compact strip — quick overview of last 6M */}
      <div className="border border-paper-rule rounded-sm bg-paper px-4 py-3">
        <div className="font-sans text-[10px] font-semibold text-ink-tertiary uppercase tracking-wider mb-2">
          State Journey — 6M
        </div>
        <StateJourneyCompact symbol={stock.symbol} days={180} />
      </div>

      {/* Weinstein + Momentum summary cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <Commentary title="Weinstein Stage">
          {interpretWeinsteinGate(stock.weinstein_gate_pass, stock.ema_10_at_20d_high)}
        </Commentary>
        <Commentary title="Momentum">
          {interpretMomentumState(stock.momentum_state)}
        </Commentary>
      </div>

      {/* State history heatmap — daily granularity */}
      <div>
        <SectionLabel>State History — Daily Heatmap (6M)</SectionLabel>
        <div className="mt-3">
          <StateHeatmap history={stateHistory} />
        </div>
      </div>

      {/* Returns */}
      <div>
        <SectionLabel>Returns</SectionLabel>
        <div className="mt-3 grid grid-cols-2 sm:grid-cols-5 gap-3">
          {([
            { label: '1 Week',   value: stock.ret_1w   as string | null },
            { label: '1 Month',  value: stock.ret_1m   as string | null },
            { label: '3 Months', value: stock.ret_3m   as string | null },
            { label: '6 Months', value: stock.ret_6m   as string | null },
            { label: '12 Months',value: stock.ret_12m  as string | null },
          ]).map(r => {
            const n = r.value != null ? parseFloat(r.value) * 100 : null
            const sign = n != null && n >= 0 ? '+' : ''
            return (
              <div key={r.label} className="flex flex-col gap-0.5 px-3 py-2 border border-paper-rule rounded-sm">
                <span className="font-sans text-[10px] text-ink-tertiary">{r.label}</span>
                <span className={`font-mono text-sm font-semibold tabular-nums ${pctColor(r.value)}`}>
                  {n != null ? `${sign}${n.toFixed(1)}%` : '—'}
                </span>
              </div>
            )
          })}
        </div>
      </div>

      {/* Metric charts */}
      {metricHistory.length === 0 ? (
        <p className="font-sans text-xs text-ink-tertiary">No metric history available.</p>
      ) : (
        <div className="space-y-5">
          <SectionLabel>Metric History — 6M</SectionLabel>

          <div className="grid grid-cols-1 lg:grid-cols-[1fr_280px] gap-4 items-start">
            <IndicatorChart
              title="RS Percentile (3M)"
              description="Rank within sector peers on 3M relative strength. 100th = beats all peers. Below 50th = underperforms most."
              currentValue={rawPct(latest?.rs_pctile_3m)}
              isBullish={latest?.rs_pctile_3m != null ? parseFloat(latest.rs_pctile_3m) >= 0.5 : null}
              data={rsPctileData}
              refLine={0.5}
              refLabel="50%"
              variant="area"
              yFormat="pct"
            />
            <Commentary title={`RS Pctile · ${rawPct(latest?.rs_pctile_3m)}`}>
              {interpretRSPctile(latest?.rs_pctile_3m ?? null)}
            </Commentary>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-[1fr_280px] gap-4 items-start">
            <IndicatorChart
              title="3-Month Return"
              description="Rolling 3M price return. Absolute — compare with RS to judge relative to market."
              currentValue={pctStr(latest?.ret_3m)}
              isBullish={latest?.ret_3m != null ? parseFloat(latest.ret_3m) >= 0 : null}
              data={ret3mData}
              refLine={0}
              refLabel="0"
              variant="area"
              yFormat="pct"
            />
            <Commentary title={`3M Return · ${pctStr(latest?.ret_3m)}`}>
              {interpret3MReturn(latest?.ret_3m ?? null)}
            </Commentary>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-[1fr_280px] gap-4 items-start">
            <IndicatorChart
              title="Short-term Momentum (EMA10/EMA20)"
              description="Ratio of 10-day EMA to 20-day EMA. Above 1.0 means short-term trend is rising faster than medium-term."
              currentValue={latest?.ema_10_ratio != null ? parseFloat(latest.ema_10_ratio).toFixed(3) : '—'}
              isBullish={latest?.ema_10_ratio != null ? parseFloat(latest.ema_10_ratio) >= 1.0 : null}
              data={emaData}
              refLine={1.0}
              refLabel="1.0 = parity"
              variant="area"
              yFormat="ratio"
            />
            <Commentary title={`EMA Ratio · ${latest?.ema_10_ratio != null ? parseFloat(latest.ema_10_ratio).toFixed(3) : '—'}`}>
              {interpretEMARatio(latest?.ema_10_ratio ?? null)}
            </Commentary>
          </div>
        </div>
      )}
    </div>
  )
}
