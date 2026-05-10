import type { ReactNode } from 'react'
import Link from 'next/link'
import { IndicatorChart } from '@/components/regime/IndicatorChart'
import type { ETFMetricHistoryRow } from '@/lib/queries/etfs'
import type { ETFRow } from '@/lib/queries/etfs'
import type { TimeRange } from '@/lib/time-range'
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

function RangeSelector({ ticker, range }: { ticker: string; range: TimeRange }) {
  return (
    <div className="flex items-center justify-between">
      <div className="font-sans text-[10px] font-semibold text-ink-tertiary uppercase tracking-wider">
        Metric History
      </div>
      <div className="flex items-center gap-0 border border-paper-rule rounded-sm overflow-hidden">
        {(['3M', '6M', '1Y'] as TimeRange[]).map(r => (
          <Link
            key={r}
            href={`/etfs/${encodeURIComponent(ticker)}?range=${r}`}
            className={`px-2.5 py-0.5 font-sans text-[11px] font-medium transition-colors ${
              range === r
                ? 'bg-teal text-white'
                : 'text-ink-secondary hover:bg-paper-rule/30'
            }`}
          >
            {r}
          </Link>
        ))}
      </div>
    </div>
  )
}

export function ETFOverviewTab({
  etf,
  metricHistory,
  range,
}: {
  etf: ETFRow
  metricHistory: ETFMetricHistoryRow[]
  range: TimeRange
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

  const ret1mData = metricHistory.map(r => ({
    date: dateStr(r.date),
    value: r.ret_1m != null ? parseFloat(r.ret_1m) : null,
  }))

  const ret6mData = metricHistory.map(r => ({
    date: dateStr(r.date),
    value: r.ret_6m != null ? parseFloat(r.ret_6m) : null,
  }))

  const extensionData = metricHistory.map(r => ({
    date: dateStr(r.date),
    value: r.extension_pct != null ? parseFloat(r.extension_pct) : null,
  }))

  const volData = metricHistory.map(r => ({
    date: dateStr(r.date),
    value: r.vol_63 != null ? parseFloat(r.vol_63) : null,
  }))

  const drawdownData = metricHistory.map(r => ({
    date: dateStr(r.date),
    value: r.drawdown != null ? parseFloat(r.drawdown) : null,
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
      {(etf.exit_market_riskoff || etf.exit_sector_avoid || etf.exit_rs_deteriorate || etf.exit_momentum_collapse || etf.exit_stop_loss) && (
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
            {etf.exit_stop_loss && (
              <span className="font-sans text-[11px] text-signal-neg bg-signal-neg/10 px-2 py-0.5 rounded">
                Stop-Loss Hit
              </span>
            )}
          </div>
        </div>
      )}

      {/* Charts */}
      <div className="space-y-4">
        <RangeSelector ticker={etf.ticker} range={range} />

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

            {/* 1M Return */}
            <div className="grid grid-cols-1 lg:grid-cols-[1fr_280px] gap-4 items-start">
              <IndicatorChart
                title="1-Month Return"
                description="Rolling 1-month price return. Short-term price momentum."
                currentValue={pctStr(latest?.ret_1m)}
                isBullish={latest?.ret_1m != null ? parseFloat(latest.ret_1m) >= 0 : null}
                data={ret1mData}
                refLine={0}
                refLabel="0"
                variant="area"
                yFormat="pct"
              />
              <Commentary title={`1M Return · ${pctStr(latest?.ret_1m)}`}>
                <p>{latest?.ret_1m != null
                  ? parseFloat(latest.ret_1m) >= 0.03
                    ? 'Strong 1-month performance. Momentum is working.'
                    : parseFloat(latest.ret_1m) >= 0
                      ? 'Marginally positive in the last month.'
                      : 'Negative 1-month return. Short-term price pressure.'
                  : 'Insufficient data.'
                }</p>
              </Commentary>
            </div>

            {/* 6M Return */}
            <div className="grid grid-cols-1 lg:grid-cols-[1fr_280px] gap-4 items-start">
              <IndicatorChart
                title="6-Month Return"
                description="Rolling 6-month price return. Medium-term trend confirmation."
                currentValue={pctStr(latest?.ret_6m)}
                isBullish={latest?.ret_6m != null ? parseFloat(latest.ret_6m) >= 0 : null}
                data={ret6mData}
                refLine={0}
                refLabel="0"
                variant="area"
                yFormat="pct"
              />
              <Commentary title={`6M Return · ${pctStr(latest?.ret_6m)}`}>
                <p>{latest?.ret_6m != null
                  ? parseFloat(latest.ret_6m) >= 0.15
                    ? 'Strong 6-month return. Sustained uptrend.'
                    : parseFloat(latest.ret_6m) >= 0
                      ? 'Positive 6-month return. Trend intact.'
                      : 'Negative 6-month return. Medium-term weakness.'
                  : 'Insufficient data.'
                }</p>
              </Commentary>
            </div>

            {/* Extension vs 200-day MA */}
            <div className="grid grid-cols-1 lg:grid-cols-[1fr_280px] gap-4 items-start">
              <IndicatorChart
                title="Extension vs 200-Day MA"
                description="How far the ETF price is above (+) or below (−) its 200-day moving average. Values above +40% indicate over-extension and elevated reversal risk."
                currentValue={rawPct(latest?.extension_pct) + '%'}
                isBullish={latest?.extension_pct != null
                  ? parseFloat(latest.extension_pct) > 0 && parseFloat(latest.extension_pct) < 0.4
                  : null
                }
                data={extensionData}
                refLine={0.4}
                refLabel="+40% risk zone"
                variant="area"
                yFormat="pct"
              />
              <Commentary title={`Extension · ${rawPct(latest?.extension_pct)}%`}>
                <p>{latest?.extension_pct != null
                  ? parseFloat(latest.extension_pct) >= 0.4
                    ? 'Over-extended above 200-day MA. Risk gate may fail. Consider reducing size.'
                    : parseFloat(latest.extension_pct) >= 0
                      ? 'Within normal extension range. No elevated reversion risk.'
                      : 'Trading below 200-day MA. Stage 3/4 caution — Weinstein gate likely failing.'
                  : 'No extension data.'
                }</p>
                <p className="text-ink-tertiary/70 text-[10px]">
                  Extension = (Price − 200-day MA) ÷ 200-day MA. The 200-day MA is the primary trend line in Weinstein Stage Analysis.
                </p>
              </Commentary>
            </div>

            {/* Realised Volatility */}
            <div className="grid grid-cols-1 lg:grid-cols-[1fr_280px] gap-4 items-start">
              <IndicatorChart
                title="Realised Volatility (63D)"
                description="Annualised realised volatility over the last 63 trading days (~3 months). High volatility increases position sizing risk."
                currentValue={rawPct(latest?.vol_63) + '%'}
                isBullish={latest?.vol_63 != null ? parseFloat(latest.vol_63) < 0.20 : null}
                data={volData}
                refLine={0.20}
                refLabel="20% normal"
                variant="line"
                yFormat="pct"
              />
              <Commentary title={`Vol 63D · ${rawPct(latest?.vol_63)}%`}>
                <p>{latest?.vol_63 != null
                  ? parseFloat(latest.vol_63) > 0.30
                    ? 'Elevated volatility. Reduce position size or wait for vol to compress.'
                    : parseFloat(latest.vol_63) > 0.20
                      ? 'Above-average volatility. Factor into position sizing.'
                      : 'Low volatility. ETF suitable for full-size positions.'
                  : 'No volatility data.'
                }</p>
              </Commentary>
            </div>

            {/* Drawdown */}
            <div className="grid grid-cols-1 lg:grid-cols-[1fr_280px] gap-4 items-start">
              <IndicatorChart
                title="Drawdown from 52-Week High"
                description="Current price vs peak price over the last 252 trading days. A drawdown below −20% indicates significant technical damage."
                currentValue={pctStr(latest?.drawdown)}
                isBullish={latest?.drawdown != null ? parseFloat(latest.drawdown) > -0.10 : null}
                data={drawdownData}
                refLine={-0.20}
                refLabel="−20% damage zone"
                variant="area"
                yFormat="pct"
              />
              <Commentary title={`Drawdown · ${pctStr(latest?.drawdown)}`}>
                <p>{latest?.drawdown != null
                  ? parseFloat(latest.drawdown) < -0.20
                    ? 'Significant drawdown. Technical damage present. Wait for base formation.'
                    : parseFloat(latest.drawdown) < -0.10
                      ? 'Moderate drawdown. Monitor for recovery above key moving averages.'
                      : 'Shallow drawdown. ETF in good technical health.'
                  : 'No drawdown data.'
                }</p>
              </Commentary>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
