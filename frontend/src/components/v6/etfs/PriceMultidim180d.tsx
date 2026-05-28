'use client'

// frontend/src/components/v6/etfs/PriceMultidim180d.tsx
//
// 180-day price multidim chart for ETF deep-dive (07a).
// Same 4-lane structure as Markets RS / Sectors deep-dive:
//   Lane 1 (60%): Price line + 20D-MA
//   Lane 2 (40%): Volume bars (green/red) + 20D volume MA line
//
// Data: PriceBar[] from mv_etf_deepdive.price_180d JSONB.
// Recharts ComposedChart (line + bar).
// NULL / empty data: shows empty state message.

import { useMemo } from 'react'
import {
  ComposedChart,
  Line,
  Bar,
  Cell,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts'
import type { PriceBar } from '@/lib/queries/v6/etfs'

type TooltipPayloadEntry = { name?: string; value?: number; payload?: ChartRow }
type ChartTooltipProps = { active?: boolean; payload?: TooltipPayloadEntry[]; label?: string }

// ── Moving average helper ─────────────────────────────────────────────────────

function movingAvg(arr: number[], window: number): (number | null)[] {
  return arr.map((_, i) => {
    if (i < window - 1) return null
    const slice = arr.slice(i - window + 1, i + 1)
    return slice.reduce((s, v) => s + v, 0) / window
  })
}

// ── Chart data shape ──────────────────────────────────────────────────────────

type ChartRow = {
  date: string
  close: number
  ma20: number | null
  volume: number
  volColor: string
  volMa20: number | null
}

// ── Tooltip ───────────────────────────────────────────────────────────────────

function CustomTooltip({ active, payload, label }: ChartTooltipProps) {
  if (!active || !payload?.length) return null
  const row = payload[0]?.payload
  if (!row) return null

  return (
    <div className="bg-paper border border-paper-rule rounded-sm p-2.5 shadow-sm text-[11px] min-w-[140px]">
      <div className="font-mono text-ink-tertiary mb-1.5">{label}</div>
      <div className="space-y-0.5">
        {payload.map((p, i) => {
          if (p.name === 'close') {
            return (
              <div key={`close-${i}`} className="flex justify-between gap-3">
                <span className="text-ink-tertiary">Close</span>
                <span className="font-mono font-semibold text-ink-primary">₹{p.value?.toFixed(2)}</span>
              </div>
            )
          }
          if (p.name === 'ma20') {
            return (
              <div key={`ma20-${i}`} className="flex justify-between gap-3">
                <span className="text-ink-tertiary">20D MA</span>
                <span className="font-mono text-signal-info">₹{p.value?.toFixed(2)}</span>
              </div>
            )
          }
          if (p.name === 'volume') {
            const vol = p.value ?? 0
            const volCr = (vol * (row.close || 0)) / 1e7
            return (
              <div key={`volume-${i}`} className="flex justify-between gap-3">
                <span className="text-ink-tertiary">Volume</span>
                <span className="font-mono text-ink-secondary">
                  {vol > 1e6 ? `${(vol / 1e6).toFixed(1)}M` : vol > 1e3 ? `${(vol / 1e3).toFixed(0)}K` : vol.toFixed(0)}
                  {volCr > 0 && ` · ₹${volCr.toFixed(1)} cr`}
                </span>
              </div>
            )
          }
          return null
        })}
      </div>
    </div>
  )
}

// ── Date tick formatter ───────────────────────────────────────────────────────

function fmtDateTick(d: string): string {
  // d is ISO date string e.g. "2025-11-15"
  try {
    const date = new Date(d)
    const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
    return `${date.getDate()}-${months[date.getMonth()]}`
  } catch {
    return d
  }
}

// ── Main component ────────────────────────────────────────────────────────────

export interface PriceMultidim180dProps {
  ticker: string
  priceData: PriceBar[] | null
}

export function PriceMultidim180d({ ticker, priceData }: PriceMultidim180dProps) {
  const chartData = useMemo((): ChartRow[] => {
    if (!priceData || priceData.length === 0) return []

    const closes = priceData.map((b) => b.close)
    const volumes = priceData.map((b) => b.volume)
    const ma20Close = movingAvg(closes, 20)
    const ma20Vol = movingAvg(volumes, 20)

    return priceData.map((bar, i) => ({
      date: bar.date,
      close: bar.close,
      ma20: ma20Close[i],
      volume: bar.volume,
      // Green bar if close >= previous close, else red
      volColor:
        i === 0 || bar.close >= priceData[i - 1].close ? '#2F6B43' : '#B0492C',
      volMa20: ma20Vol[i],
    }))
  }, [priceData])

  // Subsample x-axis ticks for readability (~8 ticks across 180 days)
  const xTicks = useMemo(() => {
    if (chartData.length === 0) return []
    const step = Math.max(1, Math.floor(chartData.length / 8))
    return chartData
      .filter((_, i) => i % step === 0 || i === chartData.length - 1)
      .map((d) => d.date)
  }, [chartData])

  if (!priceData || chartData.length === 0) {
    return (
      <div
        className="h-64 flex items-center justify-center font-sans text-[12px] text-ink-tertiary border border-paper-rule rounded-sm"
        data-testid="price-multidim-empty"
      >
        Price history for <strong className="mx-1 text-ink-secondary">{ticker}</strong> not yet available.
        ETF OHLCV ingest is pending.
      </div>
    )
  }

  const priceMin = Math.min(...chartData.map((d) => d.close))
  const priceMax = Math.max(...chartData.map((d) => d.close))
  const priceRange = priceMax - priceMin
  const priceDomain = [
    Math.floor(priceMin - priceRange * 0.05),
    Math.ceil(priceMax + priceRange * 0.05),
  ]

  const maxVol = Math.max(...chartData.map((d) => d.volume))

  return (
    <div data-testid="price-multidim-180d">
      {/* Price + 20D-MA pane */}
      <div className="mb-1">
        <div className="font-mono text-[10px] text-ink-tertiary mb-1">
          PRICE · {ticker} · daily · 180d
        </div>
        <ResponsiveContainer width="100%" height={220}>
          <ComposedChart data={chartData} margin={{ top: 8, right: 16, bottom: 4, left: 48 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#DDD3BF" strokeOpacity={0.4} vertical={false} />
            <XAxis
              dataKey="date"
              ticks={xTicks}
              tickFormatter={fmtDateTick}
              tick={{ fontSize: 9, fill: '#6B6157', fontFamily: 'JetBrains Mono, monospace' }}
              axisLine={{ stroke: '#C2B8A8' }}
              tickLine={false}
            />
            <YAxis
              domain={priceDomain}
              tickFormatter={(v: number) => `₹${v.toFixed(0)}`}
              tick={{ fontSize: 9, fill: '#6B6157', fontFamily: 'JetBrains Mono, monospace' }}
              axisLine={false}
              tickLine={false}
              width={44}
            />
            <Tooltip content={<CustomTooltip />} />
            <Line
              type="monotone"
              dataKey="close"
              name="close"
              stroke="#1A1714"
              strokeWidth={1.5}
              dot={false}
              activeDot={{ r: 3, fill: '#1A1714' }}
            />
            <Line
              type="monotone"
              dataKey="ma20"
              name="ma20"
              stroke="#3E5C76"
              strokeWidth={1.2}
              dot={false}
              strokeDasharray="4 2"
              connectNulls
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>

      {/* Volume pane */}
      <div className="border-t border-paper-rule pt-1">
        <div className="font-mono text-[10px] text-ink-tertiary mb-1">VOL</div>
        <ResponsiveContainer width="100%" height={100}>
          <ComposedChart data={chartData} margin={{ top: 4, right: 16, bottom: 16, left: 48 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#DDD3BF" strokeOpacity={0.3} vertical={false} />
            <XAxis
              dataKey="date"
              ticks={xTicks}
              tickFormatter={fmtDateTick}
              tick={{ fontSize: 9, fill: '#6B6157', fontFamily: 'JetBrains Mono, monospace' }}
              axisLine={{ stroke: '#C2B8A8' }}
              tickLine={false}
            />
            <YAxis
              domain={[0, maxVol * 1.1]}
              tickFormatter={(v: number) =>
                v >= 1e6 ? `${(v / 1e6).toFixed(0)}M` : v >= 1e3 ? `${(v / 1e3).toFixed(0)}K` : String(v)
              }
              tick={{ fontSize: 9, fill: '#6B6157', fontFamily: 'JetBrains Mono, monospace' }}
              axisLine={false}
              tickLine={false}
              width={44}
            />
            <Tooltip content={<CustomTooltip />} />
            {/* Volume bars — green when close >= prev close, red when down */}
            <Bar
              dataKey="volume"
              name="volume"
              opacity={0.6}
              isAnimationActive={false}
            >
              {chartData.map((row, i) => (
                <Cell
                  key={`vol-cell-${i}`}
                  fill={
                    i === 0 || row.close >= (chartData[i - 1]?.close ?? row.close)
                      ? 'var(--color-signal-pos, #2F6B43)'
                      : 'var(--color-signal-neg, #B0492C)'
                  }
                />
              ))}
            </Bar>
            <Line
              type="monotone"
              dataKey="volMa20"
              name="volMa20"
              stroke="#3E5C76"
              strokeWidth={1.3}
              dot={false}
              connectNulls
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>

      {/* Chart caption */}
      <div className="mt-1 font-sans text-[11px] text-ink-tertiary">
        Price line (black) · 20D MA (blue dashed) · Volume bars (green up / red down) · Volume 20D-MA (blue)
      </div>
    </div>
  )
}

export default PriceMultidim180d
