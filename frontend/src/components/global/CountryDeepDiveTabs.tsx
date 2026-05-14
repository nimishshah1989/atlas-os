'use client'
import { useState } from 'react'
import Link from 'next/link'
import { IndicatorChart } from '@/components/regime/IndicatorChart'
import type { CountryDetailRow, CountryMetricHistoryRow, CountryStateHistoryRow } from '@/lib/queries/global'
import type { TimeRange } from '@/lib/time-range'

type Tab = 'overview' | 'matrix'

const QUINTILE_COLORS: Record<number, string> = {
  1: 'bg-signal-pos/20 text-signal-pos font-semibold',
  2: 'bg-signal-pos/10 text-signal-pos/80',
  3: 'bg-paper-rule text-ink-tertiary',
  4: 'bg-signal-neg/10 text-signal-neg/80',
  5: 'bg-signal-neg/20 text-signal-neg font-semibold',
}

function QCell({ q, label }: { q: number | null; label: string }) {
  return (
    <div className="flex flex-col items-center gap-1 px-3 py-2 border border-paper-rule rounded-sm">
      <div className="font-sans text-[9px] font-semibold text-ink-tertiary uppercase tracking-wider">{label}</div>
      {q == null
        ? <span className="font-mono text-[11px] text-ink-tertiary">—</span>
        : (
          <span className={`font-mono text-[13px] px-2 py-0.5 rounded ${QUINTILE_COLORS[q] ?? ''}`}>
            Q{q}
          </span>
        )
      }
    </div>
  )
}

function MatrixTab({ country }: { country: CountryDetailRow }) {
  const BENCHMARKS = [
    { label: 'vs ACWI', keys: { '1M': country.q_1m_acwi, '3M': country.q_3m_acwi, '12M': country.q_12m_acwi } },
    { label: 'vs VT', keys: { '1M': country.q_1m_vt, '3M': country.q_3m_vt, '12M': country.q_12m_vt } },
    { label: 'vs EEM', keys: { '1M': country.q_1m_eem, '3M': country.q_3m_eem, '12M': country.q_12m_eem } },
    { label: 'vs Gold', keys: { '1M': country.q_1m_gold, '3M': country.q_3m_gold, '12M': country.q_12m_gold } },
  ]

  return (
    <div className="px-6 py-6 space-y-6">
      <div>
        <div className="font-sans text-[10px] font-semibold text-ink-tertiary uppercase tracking-wider mb-3">
          RS Quintile Matrix — Q1 = top 20% (strongest), Q5 = bottom 20%
        </div>
        <div className="space-y-4">
          {BENCHMARKS.map(bm => (
            <div key={bm.label}>
              <div className="font-sans text-xs font-semibold text-ink-secondary mb-2">{bm.label}</div>
              <div className="grid grid-cols-3 gap-2 max-w-sm">
                {Object.entries(bm.keys).map(([tf, q]) => (
                  <QCell key={tf} q={q} label={tf} />
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Consensus summary */}
      <div className="border border-paper-rule rounded-sm p-4">
        <div className="font-sans text-[10px] font-semibold text-ink-tertiary uppercase tracking-wider mb-2">
          Consensus Score
        </div>
        <div className="flex items-baseline gap-2">
          <span className={`font-mono text-2xl font-semibold ${
            (country.rs_consensus_bullish ?? 0) >= 14 ? 'text-signal-pos' :
            (country.rs_consensus_bullish ?? 0) >= 10 ? 'text-signal-warn' :
            (country.rs_consensus_bullish ?? 0) <= 4 ? 'text-signal-neg' : 'text-ink-primary'
          }`}>
            {country.rs_consensus_bullish ?? '—'}
          </span>
          <span className="font-mono text-sm text-ink-tertiary">/ 20 bullish signals</span>
        </div>
        <p className="font-sans text-xs text-ink-secondary mt-2">
          Each of 4 benchmarks × 5 timeframes = 20 possible bullish signals. ≥14 = consensus bullish. ≤4 = consensus bearish.
        </p>
      </div>
    </div>
  )
}

function OverviewTab({
  country,
  metricHistory,
  range,
}: {
  country: CountryDetailRow
  metricHistory: CountryMetricHistoryRow[]
  range: TimeRange
}) {
  function pctStr(v: string | null): string {
    if (v == null) return '—'
    const n = parseFloat(v) * 100
    return `${n >= 0 ? '+' : ''}${n.toFixed(1)}%`
  }
  function rawPct(v: string | null, digits = 0): string {
    if (v == null) return '—'
    return `${(parseFloat(v) * 100).toFixed(digits)}`
  }
  function d(s: string): string { return s.slice(0, 10) }

  const rsPctileData = metricHistory.map(r => ({ date: d(r.date), value: r.pctile_3m_vt != null ? parseFloat(r.pctile_3m_vt) : null }))
  const ret3mData = metricHistory.map(r => ({ date: d(r.date), value: r.ret_3m != null ? parseFloat(r.ret_3m) : null }))
  const ret12mData = metricHistory.map(r => ({ date: d(r.date), value: r.ret_12m != null ? parseFloat(r.ret_12m) : null }))
  const emaData = metricHistory.map(r => ({ date: d(r.date), value: r.ema_10_ratio != null ? parseFloat(r.ema_10_ratio) : null }))
  const extData = metricHistory.map(r => ({ date: d(r.date), value: r.extension_pct != null ? parseFloat(r.extension_pct) : null }))
  const volData = metricHistory.map(r => ({ date: d(r.date), value: r.realized_vol_63 != null ? parseFloat(r.realized_vol_63) : null }))
  const ddData = metricHistory.map(r => ({ date: d(r.date), value: r.max_drawdown_252 != null ? parseFloat(r.max_drawdown_252) : null }))

  const latest = metricHistory[metricHistory.length - 1]

  return (
    <div className="px-6 py-6 space-y-6">
      <div className="flex items-center justify-between">
        <div className="font-sans text-[10px] font-semibold text-ink-tertiary uppercase tracking-wider">Metric History</div>
        <div className="flex items-center gap-0 border border-paper-rule rounded-sm overflow-hidden">
          {(['1M', '3M', '6M', '1Y'] as TimeRange[]).map(r => (
            <Link
              key={r}
              href={`/global/country/${encodeURIComponent(country.ticker)}?range=${r}`}
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
            title="RS Percentile (3M vs VT)"
            description="Where this country ETF ranks among all global country ETFs on 3-month relative strength vs VT. 100 = outperforms all."
            currentValue={rawPct(latest?.pctile_3m_vt)}
            isBullish={latest?.pctile_3m_vt != null ? parseFloat(latest.pctile_3m_vt) >= 0.5 : null}
            data={rsPctileData}
            refLine={0.5}
            refLabel="50%"
            variant="area"
            yFormat="pct"
          />
          <IndicatorChart
            title="12-Month Return"
            description="Rolling 12-month price return. Full-cycle performance signal."
            currentValue={pctStr(latest?.ret_12m)}
            isBullish={latest?.ret_12m != null ? parseFloat(latest.ret_12m) >= 0 : null}
            data={ret12mData}
            refLine={0}
            refLabel="0"
            variant="area"
            yFormat="pct"
          />
          <IndicatorChart
            title="3-Month Return"
            description="Rolling 3-month price return. Compare against RS to judge relative performance."
            currentValue={pctStr(latest?.ret_3m)}
            isBullish={latest?.ret_3m != null ? parseFloat(latest.ret_3m) >= 0 : null}
            data={ret3mData}
            refLine={0}
            refLabel="0"
            variant="area"
            yFormat="pct"
          />
          <IndicatorChart
            title="Short-term Momentum (EMA10/EMA20)"
            description="Ratio of the ETF's 10-day EMA to its 20-day EMA. Above 1.0 = short-term upward momentum."
            currentValue={latest?.ema_10_ratio != null ? parseFloat(latest.ema_10_ratio).toFixed(3) : '—'}
            isBullish={latest?.ema_10_ratio != null ? parseFloat(latest.ema_10_ratio) >= 1.0 : null}
            data={emaData}
            refLine={1.0}
            refLabel="1.0 = parity"
            variant="area"
            yFormat="ratio"
          />
          <IndicatorChart
            title="Extension vs 200-Day MA"
            description="% above/below the 200-day moving average. Above +40% indicates over-extension and elevated reversion risk."
            currentValue={rawPct(latest?.extension_pct) + '%'}
            isBullish={latest?.extension_pct != null
              ? parseFloat(latest.extension_pct) > 0 && parseFloat(latest.extension_pct) < 0.4
              : null
            }
            data={extData}
            refLine={0.4}
            refLabel="+40% risk zone"
            variant="area"
            yFormat="pct"
          />
          <IndicatorChart
            title="Realised Volatility (63D)"
            description="Annualised realised volatility over 63 trading days (~3 months). High vol = elevated risk."
            currentValue={rawPct(latest?.realized_vol_63) + '%'}
            isBullish={latest?.realized_vol_63 != null ? parseFloat(latest.realized_vol_63) < 0.20 : null}
            data={volData}
            refLine={0.20}
            refLabel="20% normal"
            variant="line"
            yFormat="pct"
          />
          <IndicatorChart
            title="Drawdown from 52-Week High"
            description="Current price vs the 52-week (252 trading day) peak. Below −20% = significant technical damage."
            currentValue={pctStr(latest?.max_drawdown_252)}
            isBullish={latest?.max_drawdown_252 != null ? parseFloat(latest.max_drawdown_252) > -0.10 : null}
            data={ddData}
            refLine={-0.20}
            refLabel="−20% damage zone"
            variant="area"
            yFormat="pct"
          />
        </div>
      )}
    </div>
  )
}

export function CountryDeepDiveTabs({
  country,
  metricHistory,
  stateHistory,
  activeTab: initialTab,
  range,
}: {
  country: CountryDetailRow
  metricHistory: CountryMetricHistoryRow[]
  stateHistory: CountryStateHistoryRow[]
  activeTab: 'overview' | 'matrix'
  range: TimeRange
}) {
  const [tab, setTab] = useState<Tab>(initialTab)

  return (
    <div>
      <div className="px-6 border-b border-paper-rule">
        <div className="flex items-center gap-0">
          {(['overview', 'matrix'] as Tab[]).map(t => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`px-4 py-3 font-sans text-sm capitalize transition-colors border-b-2 -mb-px ${
                tab === t
                  ? 'border-teal text-ink-primary font-medium'
                  : 'border-transparent text-ink-tertiary hover:text-ink-secondary'
              }`}
            >
              {t === 'overview' ? 'Overview' : 'Quintile Matrix'}
            </button>
          ))}
        </div>
      </div>

      {tab === 'overview' && (
        <OverviewTab
          country={country}
          metricHistory={metricHistory}
          range={range}
        />
      )}
      {tab === 'matrix' && (
        <MatrixTab country={country} />
      )}
    </div>
  )
}
