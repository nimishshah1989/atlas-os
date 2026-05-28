// frontend/src/components/v6/PortfolioAnalyticsClient.tsx
//
// TV-06: Portfolio analytics page — 7-metric grid + cumulative returns chart.
// Metrics: Sharpe, Sortino, Calmar, Beta, Alpha, Max Drawdown, TWR.
// Chart: Recharts LineChart — portfolio vs Nifty 50 cumulative returns.
// CSV export: GET /v1/portfolios/{id}/tv-export.csv

'use client'

import Link from 'next/link'
import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
} from 'recharts'
import type { PortfolioAnalytics, DailyReturn } from '@/lib/queries/v6/portfolio_analytics'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface PortfolioAnalyticsClientProps {
  portfolioId: string
  portfolioName: string
  analytics: PortfolioAnalytics | null
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function fmtNum(n: number | null, decimals = 2, signed = false): string {
  if (n === null) return '—'
  const s = n.toFixed(decimals)
  return signed && n > 0 ? `+${s}` : s
}

function fmtPct(n: number | null, signed = true): string {
  if (n === null) return '—'
  const pct = (n * 100).toFixed(2)
  return signed && n > 0 ? `+${pct}%` : `${pct}%`
}

function signClass(n: number | null): string {
  if (n === null) return 'text-ink-primary'
  return n > 0 ? 'text-signal-pos' : n < 0 ? 'text-signal-neg' : 'text-ink-primary'
}

function fmtDate(iso: string): string {
  const d = new Date(iso)
  if (isNaN(d.getTime())) return iso
  const day = String(d.getDate()).padStart(2, '0')
  const mon = d.toLocaleString('en-US', { month: 'short' })
  const yr = d.getFullYear()
  return `${day}-${mon}-${yr}`
}

// Compute cumulative return series from daily returns.
// Formula: running product of (1 + r_i) - 1
function buildCumulativeSeries(
  daily: DailyReturn[],
): Array<{ date: string; portfolio: number; nifty50: number }> {
  let portfolioCum = 1
  let niftyCum = 1
  return daily.map((row) => {
    portfolioCum *= 1 + row.portfolio_return
    niftyCum *= 1 + row.nifty50_return
    return {
      date: row.date,
      portfolio: portfolioCum - 1,
      nifty50: niftyCum - 1,
    }
  })
}

// Custom dot renderer that shows a labeled circle only at the last data point.
function EndLabelDot(color: string, dataKey: 'portfolio' | 'nifty50', totalPoints: number) {
  // eslint-disable-next-line react/display-name
  return (props: {
    cx?: number; cy?: number; index?: number;
    payload?: { portfolio: number; nifty50: number }
  }) => {
    const { cx = 0, cy = 0, index = 0, payload } = props
    if (index !== totalPoints - 1 || !payload) return null
    const val = payload[dataKey]
    const pct = (val * 100).toFixed(1)
    const sign = val > 0 ? '+' : ''
    return (
      <g>
        <circle cx={cx} cy={cy} r={3} fill={color} />
        <text
          x={cx + 6}
          y={cy + 4}
          fill={color}
          fontSize={10}
          fontFamily="var(--font-mono)"
        >
          {sign}{pct}%
        </text>
      </g>
    )
  }
}

// ---------------------------------------------------------------------------
// 7-metric grid
// ---------------------------------------------------------------------------

interface MetricCellProps {
  label: string
  value: string
  subLabel: string
  valueClass?: string
  tooltip?: string
}

function MetricCell({ label, value, subLabel, valueClass = 'text-ink-primary', tooltip }: MetricCellProps) {
  return (
    <div
      className="flex flex-col items-center justify-center py-4 px-3 border-r border-paper-rule last:border-r-0"
      title={tooltip}
    >
      <span className="font-mono text-[11px] uppercase tracking-wider text-ink-3 mb-1 text-center">
        {label}
      </span>
      <span className={`font-mono text-[22px] font-semibold tabular-nums leading-tight ${valueClass}`}>
        {value}
      </span>
      <span className="font-sans text-[11px] text-ink-4 mt-1 text-center">{subLabel}</span>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Chart tooltip
// ---------------------------------------------------------------------------

interface ChartTooltipProps {
  active?: boolean
  payload?: Array<{ name: string; value: number; color: string }>
  label?: string
}

function ChartTooltip({ active, payload, label }: ChartTooltipProps) {
  if (!active || !payload || payload.length === 0) return null
  return (
    <div className="bg-paper border border-paper-rule rounded-[2px] px-3 py-2 shadow-sm">
      <div className="font-sans text-[11px] text-ink-3 mb-1">{label ? fmtDate(label) : ''}</div>
      {payload.map((p) => {
        const pct = (p.value * 100).toFixed(2)
        const sign = p.value > 0 ? '+' : ''
        return (
          <div key={p.name} className="font-mono text-[12px]" style={{ color: p.color }}>
            {p.name}: {sign}{pct}%
          </div>
        )
      })}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export function PortfolioAnalyticsClient({
  portfolioId,
  portfolioName,
  analytics,
}: PortfolioAnalyticsClientProps) {
  // Empty state
  if (!analytics) {
    return (
      <div className="min-h-screen bg-paper px-8 py-6 max-w-5xl mx-auto">
        <h1 className="font-serif text-2xl text-ink-primary mb-6">{portfolioName}</h1>
        <div className="flex flex-col items-center justify-center py-20 gap-3">
          <p className="font-sans text-sm text-ink-3">
            No closed positions yet. Analytics require at least 1 completed trade.
          </p>
          <Link
            href={`/portfolios/${portfolioId}`}
            className="font-sans text-sm text-accent hover:underline"
          >
            ← Back to portfolio
          </Link>
        </div>
      </div>
    )
  }

  const cumulativeSeries = buildCumulativeSeries(analytics.daily_returns)

  // Date range from daily returns
  const firstDate = analytics.daily_returns[0]?.date ?? null
  const lastDate = analytics.daily_returns[analytics.daily_returns.length - 1]?.date ?? null

  const csvUrl = `/v1/portfolios/${portfolioId}/tv-export.csv`

  return (
    <div className="min-h-screen bg-paper px-8 py-6 max-w-5xl mx-auto">
      {/* Page header */}
      <div className="flex items-start justify-between flex-wrap gap-4 mb-6">
        <h1 className="font-serif text-2xl text-ink-primary">{portfolioName}</h1>
        <a
          href={csvUrl}
          download
          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-[2px] bg-accent text-white font-sans text-sm hover:bg-accent/90 transition-colors"
        >
          ↓ Export to TradingView CSV
        </a>
      </div>

      {/* 7-metric grid */}
      <div className="grid grid-cols-2 md:grid-cols-7 border border-paper-rule rounded-[2px] bg-paper mb-6 overflow-x-auto">
        <MetricCell
          label="Sharpe"
          value={fmtNum(analytics.sharpe, 2)}
          subLabel="Risk-adj return"
          valueClass={signClass(analytics.sharpe)}
          tooltip={analytics.sharpe === null ? 'Requires sufficient return history' : undefined}
        />
        <MetricCell
          label="Sortino"
          value={fmtNum(analytics.sortino, 2)}
          subLabel="Downside risk"
          valueClass={signClass(analytics.sortino)}
          tooltip={analytics.sortino === null ? 'Requires sufficient return history' : undefined}
        />
        <MetricCell
          label="Calmar"
          value={fmtNum(analytics.calmar, 2)}
          subLabel="Return / Max DD"
          valueClass={signClass(analytics.calmar)}
          tooltip={analytics.calmar === null ? 'Requires drawdown data' : undefined}
        />
        <MetricCell
          label="Beta"
          value={fmtNum(analytics.beta, 2)}
          subLabel="vs Nifty 50"
          valueClass="text-ink-primary"
          tooltip={analytics.beta === null ? 'Requires 30+ trading days of data' : undefined}
        />
        <MetricCell
          label="Alpha (Jensen)"
          value={fmtPct(analytics.alpha)}
          subLabel="Excess return"
          valueClass={signClass(analytics.alpha)}
          tooltip={analytics.alpha === null ? 'Requires benchmark data' : undefined}
        />
        <MetricCell
          label="Max Drawdown"
          value={fmtPct(analytics.max_drawdown, false)}
          subLabel="Peak to trough"
          valueClass={analytics.max_drawdown < 0 ? 'text-signal-neg' : 'text-ink-primary'}
        />
        <MetricCell
          label="TWR"
          value={fmtPct(analytics.twr)}
          subLabel="Time-weighted"
          valueClass={signClass(analytics.twr)}
        />
      </div>

      {/* Cumulative returns chart */}
      <div className="mb-6">
        <h2 className="font-sans text-[10px] font-semibold text-ink-3 uppercase tracking-wider mb-3">
          Cumulative Returns
        </h2>
        <div className="border border-paper-rule rounded-[2px] bg-paper p-4">
          {/* h-[180px] on mobile, h-[240px] on md+ per spec */}
          <div className="h-[180px] md:h-[240px]">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart
                data={cumulativeSeries}
                margin={{ top: 8, right: 48, left: 0, bottom: 0 }}
              >
                <CartesianGrid stroke="rgba(194,184,168,0.3)" strokeDasharray="3 3" />
                <XAxis
                  dataKey="date"
                  tick={{ fontSize: 10, fill: '#9A8F82', fontFamily: 'var(--font-mono)' }}
                  tickLine={false}
                  tickFormatter={(v: string) => {
                    const d = new Date(v)
                    if (isNaN(d.getTime())) return v
                    return `${d.toLocaleString('en-US', { month: 'short' })} '${String(d.getFullYear()).slice(2)}`
                  }}
                  minTickGap={60}
                />
                <YAxis
                  tick={{ fontSize: 10, fill: '#9A8F82', fontFamily: 'var(--font-mono)' }}
                  tickLine={false}
                  axisLine={false}
                  tickFormatter={(v: number) => `${(v * 100).toFixed(0)}%`}
                  width={48}
                />
                <Tooltip content={<ChartTooltip />} />
                <Line
                  type="monotone"
                  dataKey="portfolio"
                  name="Portfolio"
                  stroke="#1D9E75"
                  strokeWidth={2}
                  dot={EndLabelDot('#1D9E75', 'portfolio', cumulativeSeries.length)}
                  activeDot={{ r: 3, fill: '#1D9E75' }}
                />
                <Line
                  type="monotone"
                  dataKey="nifty50"
                  name="Nifty 50"
                  stroke="#9A8F82"
                  strokeWidth={1.5}
                  strokeDasharray="5 3"
                  dot={EndLabelDot('#9A8F82', 'nifty50', cumulativeSeries.length)}
                  activeDot={{ r: 3, fill: '#9A8F82' }}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      {/* Lower 2-column panels */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Benchmark comparison */}
        <div className="border border-paper-rule rounded-[2px] bg-paper p-4">
          <h3 className="font-sans text-[10px] font-semibold text-ink-3 uppercase tracking-wider mb-3">
            Benchmark Comparison
          </h3>
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <span className="font-sans text-[12px] text-ink-3">Alpha (Jensen&apos;s)</span>
              <span className={`font-mono text-[13px] font-semibold tabular-nums ${signClass(analytics.alpha)}`}>
                {fmtPct(analytics.alpha)}
              </span>
            </div>
            <div className="flex items-center justify-between">
              <span className="font-sans text-[12px] text-ink-3">Beta</span>
              <span className="font-mono text-[13px] text-ink-primary tabular-nums">
                {fmtNum(analytics.beta, 2)}
              </span>
            </div>
            <div className="flex items-center justify-between">
              <span className="font-sans text-[12px] text-ink-3">Annualised Return</span>
              <span className={`font-mono text-[13px] font-semibold tabular-nums ${signClass(analytics.annualised_return)}`}>
                {fmtPct(analytics.annualised_return)}
              </span>
            </div>
            {analytics.beta !== null && (
              <p className="font-sans text-[11px] text-ink-4 mt-2">
                Beta {analytics.beta.toFixed(2)} indicates the portfolio is{' '}
                {analytics.beta > 1 ? 'more' : 'less'} volatile than Nifty 50.
              </p>
            )}
          </div>
        </div>

        {/* Observation summary */}
        <div className="border border-paper-rule rounded-[2px] bg-paper p-4">
          <h3 className="font-sans text-[10px] font-semibold text-ink-3 uppercase tracking-wider mb-3">
            Observation Summary
          </h3>
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <span className="font-sans text-[12px] text-ink-3">Trading Days</span>
              <span className="font-mono text-[13px] text-ink-primary tabular-nums">
                {analytics.observation_days}
              </span>
            </div>
            {firstDate && lastDate && (
              <div className="flex items-center justify-between">
                <span className="font-sans text-[12px] text-ink-3">Date Range</span>
                <span className="font-mono text-[11px] text-ink-3 tabular-nums">
                  {fmtDate(firstDate)} — {fmtDate(lastDate)}
                </span>
              </div>
            )}
            <div className="flex items-center justify-between">
              <span className="font-sans text-[12px] text-ink-3">Risk-Free Rate (Rf)</span>
              <span className="font-mono text-[13px] text-ink-3 tabular-nums">
                {(analytics.risk_free_rate_used * 100).toFixed(2)}%
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

export default PortfolioAnalyticsClient
