import type { ReactNode } from 'react'
import { IndicatorChart } from '@/components/regime/IndicatorChart'
import type { ETFMetricHistoryRow } from '@/lib/queries/etfs'
import type { ETFRow } from '@/lib/queries/etfs'
import {
  interpretRSPctile,
  interpretMomentumState,
  interpretWeinsteinGate,
  interpretEMARatio,
  interpret3MReturn,
} from '@/lib/stock-formatters'
import { ETFGatesPanel } from './ETFGatesPanel'

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

export function ETFOverviewTab({
  etf,
  metricHistory,
}: {
  etf: ETFRow
  metricHistory: ETFMetricHistoryRow[]
}) {
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

  const latest = metricHistory[metricHistory.length - 1]

  return (
    <div className="px-6 py-6 space-y-6">
      {/* Weinstein + momentum summary */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <Commentary title="Weinstein Stage">
          {interpretWeinsteinGate(etf.weinstein_gate_pass, null)}
        </Commentary>
        <Commentary title="Momentum">
          {interpretMomentumState(etf.momentum_state)}
        </Commentary>
        <ETFGatesPanel etf={etf} />
      </div>

      {/* Exit triggers — only show if any are active */}
      {(etf.exit_market_riskoff || etf.exit_sector_avoid || etf.exit_rs_deteriorate || etf.exit_momentum_collapse) && (
        <div className="border border-signal-neg/30 bg-signal-neg/5 rounded-sm px-4 py-3">
          <div className="font-sans text-[10px] font-semibold text-signal-neg uppercase tracking-wider mb-2">
            Exit Signals Active
          </div>
          <div className="flex flex-wrap gap-2">
            {etf.exit_market_riskoff && (
              <span className="font-sans text-[11px] text-signal-neg bg-signal-neg/10 px-2 py-0.5 rounded">
                Market Risk-Off
              </span>
            )}
            {etf.exit_sector_avoid && (
              <span className="font-sans text-[11px] text-signal-neg bg-signal-neg/10 px-2 py-0.5 rounded">
                Sector Avoid
              </span>
            )}
            {etf.exit_rs_deteriorate && (
              <span className="font-sans text-[11px] text-signal-neg bg-signal-neg/10 px-2 py-0.5 rounded">
                RS Deteriorating
              </span>
            )}
            {etf.exit_momentum_collapse && (
              <span className="font-sans text-[11px] text-signal-neg bg-signal-neg/10 px-2 py-0.5 rounded">
                Momentum Collapse
              </span>
            )}
          </div>
        </div>
      )}

      {/* Charts */}
      <div>
        <div className="font-sans text-[10px] text-ink-tertiary uppercase tracking-wider mb-4">
          Metric History — 6M
        </div>

        {metricHistory.length === 0 ? (
          <p className="font-sans text-xs text-ink-tertiary">No metric history available for this range.</p>
        ) : (
          <div className="space-y-5">
            {/* RS Pctile */}
            <div className="grid grid-cols-1 lg:grid-cols-[1fr_280px] gap-4 items-start">
              <IndicatorChart
                title="RS Percentile (3M)"
                description="Where this ETF ranks within its peer group on 3-month relative strength. 100th = outperforms all peers."
                currentValue={rawPct(latest?.rs_pctile_3m)}
                isBullish={latest?.rs_pctile_3m != null ? parseFloat(latest.rs_pctile_3m) >= 0.5 : null}
                data={rsPctileData}
                refLine={0.5}
                refLabel="50%"
                variant="area"
                yFormat="pct"
              />
              <Commentary title={`RS Pctile Today · ${rawPct(latest?.rs_pctile_3m)}`}>
                {interpretRSPctile(latest?.rs_pctile_3m ?? null)}
              </Commentary>
            </div>

            {/* 3M Return */}
            <div className="grid grid-cols-1 lg:grid-cols-[1fr_280px] gap-4 items-start">
              <IndicatorChart
                title="3-Month Return"
                description="Rolling 3-month price return. Absolute performance — use RS to judge whether it beats the market."
                currentValue={pctStr(latest?.ret_3m)}
                isBullish={latest?.ret_3m != null ? parseFloat(latest.ret_3m) >= 0 : null}
                data={ret3mData}
                refLine={0}
                refLabel="0"
                variant="area"
                yFormat="pct"
              />
              <Commentary title={`3M Return Today · ${pctStr(latest?.ret_3m)}`}>
                {interpret3MReturn(latest?.ret_3m ?? null)}
              </Commentary>
            </div>

            {/* EMA 10 Ratio */}
            <div className="grid grid-cols-1 lg:grid-cols-[1fr_280px] gap-4 items-start">
              <IndicatorChart
                title="Short-term Momentum (EMA10/EMA20)"
                description="Ratio of this ETF's 10-day EMA to its own 20-day EMA. Above 1.0 = upward price momentum in the short term."
                currentValue={latest?.ema_10_ratio != null ? parseFloat(latest.ema_10_ratio).toFixed(3) : '—'}
                isBullish={latest?.ema_10_ratio != null ? parseFloat(latest.ema_10_ratio) >= 1.0 : null}
                data={emaData}
                refLine={1.0}
                refLabel="1.0 = parity"
                variant="area"
                yFormat="ratio"
              />
              <Commentary title={`EMA Ratio Today · ${latest?.ema_10_ratio != null ? parseFloat(latest.ema_10_ratio).toFixed(3) : '—'}`}>
                {interpretEMARatio(latest?.ema_10_ratio ?? null)}
              </Commentary>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
