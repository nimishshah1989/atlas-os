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
  interpretDrawdown,
  interpretExtension,
  interpretVolumeRatio,
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

function EntryBadge({ label, active }: { label: string; active: boolean | null }) {
  if (active) {
    return (
      <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-sm bg-teal/15 border border-teal/30 font-sans text-xs font-semibold text-teal">
        <span className="w-1.5 h-1.5 rounded-full bg-teal shrink-0" />
        {label}
      </span>
    )
  }
  return (
    <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-sm bg-paper-rule/10 border border-paper-rule/30 font-sans text-xs text-ink-tertiary">
      <span className="w-1.5 h-1.5 rounded-full bg-paper-rule shrink-0" />
      {label}
    </span>
  )
}

function ExitBadge({ label, active }: { label: string; active: boolean | null }) {
  if (active) {
    return (
      <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-sm bg-signal-neg/15 border border-signal-neg/30 font-sans text-xs font-semibold text-signal-neg">
        <span className="w-1.5 h-1.5 rounded-full bg-signal-neg shrink-0" />
        {label}
      </span>
    )
  }
  return (
    <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-sm bg-paper-rule/10 border border-paper-rule/30 font-sans text-xs text-ink-tertiary">
      <span className="w-1.5 h-1.5 rounded-full bg-paper-rule shrink-0" />
      {label}
    </span>
  )
}

function SignalsSection({ stock }: { stock: StockRowWithSector }) {
  const entrySignals = [
    { label: 'Transition (Stage 1→2)', active: stock.transition_trigger },
    { label: 'Breakout to New High', active: stock.breakout_trigger },
  ]
  const exitSignals = [
    { label: 'Market Risk-Off', active: stock.exit_market_riskoff },
    { label: 'Sector Avoid', active: stock.exit_sector_avoid },
    { label: 'RS Deteriorating', active: stock.exit_rs_deteriorate },
    { label: 'Momentum Collapse', active: stock.exit_momentum_collapse },
    { label: 'Volume Distribution', active: stock.exit_volume_distrib },
    { label: 'Stop Loss Hit', active: stock.exit_stop_loss },
  ]

  const anyEntry = entrySignals.some(s => s.active === true)
  const anyExit = exitSignals.some(s => s.active === true)
  const atrVal = stock.atr_21 != null ? parseFloat(stock.atr_21) : null

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
      {/* Entry signals */}
      <div className="border border-paper-rule rounded-sm px-4 py-3">
        <div className="font-sans text-[10px] font-semibold text-ink-tertiary uppercase tracking-wider mb-2 flex items-center gap-2">
          Entry Signals
          {anyEntry && (
            <span className="text-teal text-[9px] font-semibold uppercase tracking-wide">Active</span>
          )}
        </div>
        <div className="flex flex-wrap gap-2">
          {entrySignals.map(s => (
            <EntryBadge key={s.label} label={s.label} active={s.active} />
          ))}
        </div>
        {!anyEntry && (
          <p className="font-sans text-[10px] text-ink-tertiary mt-2">
            No entry triggers currently firing. Both require investable-grade quality.
          </p>
        )}
      </div>

      {/* Exit risk flags */}
      <div className="border border-paper-rule rounded-sm px-4 py-3">
        <div className="font-sans text-[10px] font-semibold text-ink-tertiary uppercase tracking-wider mb-2 flex items-center gap-2">
          Exit Risk Flags
          {anyExit && (
            <span className="text-signal-neg text-[9px] font-semibold uppercase tracking-wide">Warning</span>
          )}
        </div>
        <div className="flex flex-wrap gap-2">
          {exitSignals.map(s => (
            <ExitBadge key={s.label} label={s.label} active={s.active} />
          ))}
        </div>
        {!anyExit && (
          <p className="font-sans text-[10px] text-ink-tertiary mt-2">No exit flags active.</p>
        )}
        {atrVal != null && (
          <div className="mt-2 pt-2 border-t border-paper-rule/30">
            <span className="font-sans text-[10px] text-ink-tertiary">
              ATR-21: <span className="font-mono font-semibold text-ink-secondary">
                ₹{atrVal.toFixed(1)}
              </span>
              <span className="ml-1 text-ink-tertiary">avg daily range</span>
            </span>
          </div>
        )}
      </div>
    </div>
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
  const ema20Data = metricHistory.map(r => ({
    date: dateStr(r.date),
    value: r.ema_20_ratio != null ? (parseFloat(r.ema_20_ratio) - 1) * 100 : null,
  }))
  const drawdownData = metricHistory.map(r => ({
    date: dateStr(r.date),
    value: r.drawdown_ratio_252 != null ? parseFloat(r.drawdown_ratio_252) : null,
  }))
  const extensionData = metricHistory.map(r => ({
    date: dateStr(r.date),
    value: r.extension_pct != null ? parseFloat(r.extension_pct) : null,
  }))
  const volumeData = metricHistory.map(r => ({
    date: dateStr(r.date),
    value: r.avg_volume_20 != null ? parseFloat(r.avg_volume_20) / 1_000_000 : null,
  }))
  const volRatioData = metricHistory.map(r => ({
    date: dateStr(r.date),
    value: r.vol_ratio_63 != null ? parseFloat(r.vol_ratio_63) : null,
  }))

  const latestVolumeM = latest?.avg_volume_20 != null
    ? (parseFloat(latest.avg_volume_20) / 1_000_000).toFixed(2)
    : '—'

  return (
    <div className="px-6 py-6 space-y-8">
      {/* State journey compact strip */}
      <div className="border border-paper-rule rounded-sm bg-paper px-4 py-3">
        <div className="font-sans text-[10px] font-semibold text-ink-tertiary uppercase tracking-wider mb-2">
          State Journey — 6M
        </div>
        <StateJourneyCompact symbol={stock.symbol} days={180} />
      </div>

      {/* Entry / Exit Signals */}
      <div>
        <SectionLabel>Signals</SectionLabel>
        <div className="mt-3">
          <SignalsSection stock={stock} />
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

      {/* Weinstein + Momentum summary cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <Commentary title="Weinstein Stage">
          {interpretWeinsteinGate(stock.weinstein_gate_pass, stock.ema_10_at_20d_high)}
        </Commentary>
        <Commentary title="Momentum">
          {interpretMomentumState(stock.momentum_state)}
        </Commentary>
      </div>

      {/* State history heatmap */}
      <div>
        <SectionLabel>State History — Daily Heatmap (6M)</SectionLabel>
        <div className="mt-3">
          <StateHeatmap history={stateHistory} />
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
            <Commentary title={`EMA10/20 · ${latest?.ema_10_ratio != null ? parseFloat(latest.ema_10_ratio).toFixed(3) : '—'}`}>
              {interpretEMARatio(latest?.ema_10_ratio ?? null)}
            </Commentary>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-[1fr_280px] gap-4 items-start">
            <IndicatorChart
              title="Price vs EMA20 (Medium-term Trend)"
              description="How far the price is from the 20-day EMA as a ratio. Positive = price above EMA20 (uptrend). Negative = price below (pullback/downtrend)."
              currentValue={latest?.ema_20_ratio != null ? (() => { const d = (parseFloat(latest.ema_20_ratio) - 1) * 100; return `${d >= 0 ? '+' : ''}${d.toFixed(2)}%` })() : '—'}
              isBullish={latest?.ema_20_ratio != null ? parseFloat(latest.ema_20_ratio) >= 1.0 : null}
              data={ema20Data}
              refLine={0}
              refLabel="0 = at EMA20"
              variant="area"
              yFormat="pct"
            />
            <Commentary title={`EMA20 Dev · ${latest?.ema_20_ratio != null ? (() => { const d = (parseFloat(latest.ema_20_ratio) - 1) * 100; return `${d >= 0 ? '+' : ''}${d.toFixed(2)}%` })() : '—'}`}>
              {(() => {
                const ratio = latest?.ema_20_ratio != null ? parseFloat(latest.ema_20_ratio) : null
                if (ratio == null) return <p>No data.</p>
                const v = (ratio - 1) * 100
                if (v >= 5) return <p>Price is well above EMA20 (+{v.toFixed(1)}%) — strong medium-term trend. Overextension risk above +10%.</p>
                if (v >= 0) return <p>Price is near or above EMA20 (+{v.toFixed(1)}%) — trend intact; watch for a re-test of the level.</p>
                if (v >= -5) return <p>Price is slightly below EMA20 ({v.toFixed(1)}%) — minor pullback. Trend at risk if price stays below.</p>
                return <p>Price is significantly below EMA20 ({v.toFixed(1)}%) — medium-term downtrend. Caution warranted.</p>
              })()}
            </Commentary>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-[1fr_280px] gap-4 items-start">
            <IndicatorChart
              title="Drawdown from 252D Peak"
              description="How far the stock has fallen from its 252-day high. 0 = at peak. Negative = percentage below peak."
              currentValue={latest?.drawdown_ratio_252 != null ? `${(parseFloat(latest.drawdown_ratio_252) * 100).toFixed(1)}%` : '—'}
              isBullish={latest?.drawdown_ratio_252 != null ? parseFloat(latest.drawdown_ratio_252) > -0.1 : null}
              data={drawdownData}
              refLine={0}
              refLabel="0 = at peak"
              variant="area"
              yFormat="pct"
            />
            <Commentary title={`Drawdown · ${latest?.drawdown_ratio_252 != null ? `${(parseFloat(latest.drawdown_ratio_252) * 100).toFixed(1)}%` : '—'}`}>
              {interpretDrawdown(latest?.drawdown_ratio_252 ?? null)}
            </Commentary>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-[1fr_280px] gap-4 items-start">
            <IndicatorChart
              title="Extension vs 200D EMA"
              description="How far the stock is above or below its 200-day EMA. Positive = above (uptrend). Negative = below (downtrend)."
              currentValue={latest?.extension_pct != null ? `${(parseFloat(latest.extension_pct) * 100).toFixed(1)}%` : '—'}
              isBullish={latest?.extension_pct != null ? parseFloat(latest.extension_pct) > 0 : null}
              data={extensionData}
              refLine={0}
              refLabel="0 = at 200D EMA"
              variant="area"
              yFormat="pct"
            />
            <Commentary title={`Extension · ${latest?.extension_pct != null ? `${(parseFloat(latest.extension_pct) * 100).toFixed(1)}%` : '—'}`}>
              {interpretExtension(latest?.extension_pct ?? null)}
            </Commentary>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-[1fr_280px] gap-4 items-start">
            <IndicatorChart
              title="Average Volume (20D) — Millions"
              description="20-day average trading volume in millions of shares. Rising volume on up days = accumulation. Falling on up days = fading interest."
              currentValue={`${latestVolumeM}M`}
              isBullish={latest?.avg_volume_20 != null ? parseFloat(latest.avg_volume_20) >= 500000 : null}
              data={volumeData}
              refLine={0}
              refLabel=""
              variant="area"
              yFormat="ratio"
            />
            <Commentary title={`Volume · ${latestVolumeM}M`}>
              {interpretVolumeRatio(latest?.avg_volume_20 ?? null)}
            </Commentary>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-[1fr_280px] gap-4 items-start">
            <IndicatorChart
              title="Volume Ratio (63D)"
              description="Current 20D avg volume divided by 63D avg volume. Above 1.0 = volume is expanding vs the 3M baseline (interest increasing). Below 1.0 = fading volume."
              currentValue={latest?.vol_ratio_63 != null ? parseFloat(latest.vol_ratio_63).toFixed(2) : '—'}
              isBullish={latest?.vol_ratio_63 != null ? parseFloat(latest.vol_ratio_63) >= 1.0 : null}
              data={volRatioData}
              refLine={1.0}
              refLabel="1.0 = baseline"
              variant="area"
              yFormat="ratio"
            />
            <Commentary title={`Vol Ratio · ${latest?.vol_ratio_63 != null ? parseFloat(latest.vol_ratio_63).toFixed(2) : '—'}`}>
              {(() => {
                const v = latest?.vol_ratio_63 != null ? parseFloat(latest.vol_ratio_63) : null
                if (v == null) return <p>No data.</p>
                if (v >= 1.5) return <p>Volume is running at {v.toFixed(1)}× its 3M baseline — significant expansion. Could signal a breakout or distribution event depending on price direction.</p>
                if (v >= 1.0) return <p>Volume is modestly above the 3M baseline at {v.toFixed(2)}×. Suggests increasing market participation — healthy for an uptrend.</p>
                if (v >= 0.7) return <p>Volume is below the 3M baseline at {v.toFixed(2)}×. Declining interest; upside moves on low volume carry less conviction.</p>
                return <p>Volume has dried up significantly at {v.toFixed(2)}× the 3M baseline. Either consolidation or fading interest — watch for a catalyst to re-engage volume.</p>
              })()}
            </Commentary>
          </div>
        </div>
      )}
    </div>
  )
}
