'use client'
// frontend/src/components/v6/india-pulse/DispersionCharts.tsx
//
// Section 3 — Dispersion & concentration.
// Left panel: trailing 60d cross-section dispersion line chart.
// Right panel: sector return bar chart from sector_heatmap data.
// Both use Recharts.

import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  BarChart,
  Bar,
  Cell,
  ReferenceLine,
} from 'recharts'
import type { DispersionPoint, SectorHeatmapItem } from '@/lib/queries/v6/india_pulse'
import { CHART_COLORS } from '@/lib/chart-colors'
import { fmtPct } from './helpers'

type Props = {
  dispersion_60d_series: DispersionPoint[]
  sector_heatmap: SectorHeatmapItem[]
}

function barColor(val: number | null): string {
  if (val == null) return CHART_COLORS.inkTertiary
  if (val > 0.01) return CHART_COLORS.rsLeader
  if (val < -0.01) return CHART_COLORS.rsWeak
  return CHART_COLORS.inkTertiary
}

type TooltipProps = {
  active?: boolean
  payload?: { value: unknown }[]
  label?: string
}

function CustomDispersionTooltip({ active, payload, label }: TooltipProps) {
  if (!active || !payload?.length) return null
  return (
    <div className="bg-paper border border-paper-rule rounded-sm px-2 py-1.5 shadow-sm text-[11px]">
      <div className="text-ink-tertiary mb-0.5">{label}</div>
      <div className="font-mono text-signal-pos font-semibold">
        {payload[0]?.value != null ? (payload[0].value as number).toFixed(4) : '—'}
      </div>
    </div>
  )
}

function CustomSectorTooltip({ active, payload, label }: TooltipProps) {
  if (!active || !payload?.length) return null
  const val = payload[0]?.value as number | null
  return (
    <div className="bg-paper border border-paper-rule rounded-sm px-2 py-1.5 shadow-sm text-[11px]">
      <div className="text-ink-secondary mb-0.5 font-medium">{label}</div>
      <div className={`font-mono font-semibold ${val != null && val > 0 ? 'text-signal-pos' : 'text-signal-neg'}`}>
        {val != null ? fmtPct(val) : '—'} 1W RS
      </div>
    </div>
  )
}

export function DispersionCharts({ dispersion_60d_series, sector_heatmap }: Props) {
  // Prepare dispersion chart data — show last 60 points, format date as short label
  const dispData = dispersion_60d_series
    .filter(p => p.value != null)
    .map(p => ({
      date: p.date ? p.date.slice(5) : '', // MM-DD
      value: p.value,
    }))

  // Prepare sector bar chart — use rs_1w sorted (already sorted by MV)
  const sectorData = sector_heatmap
    .filter(s => s.rs_1w != null)
    .slice(0, 22) // cap at 22
    .map(s => ({
      name: s.sector_name.length > 10 ? s.sector_name.slice(0, 9) + '…' : s.sector_name,
      fullName: s.sector_name,
      rs_1w: s.rs_1w,
    }))

  const posCount = sectorData.filter(s => (s.rs_1w ?? 0) > 0).length
  const negCount = sectorData.filter(s => (s.rs_1w ?? 0) < 0).length

  return (
    <div className="grid grid-cols-2 gap-4">
      {/* Left: 60d dispersion line */}
      <div className="bg-paper border border-paper-rule rounded-sm p-5">
        <div className="flex items-baseline justify-between mb-4">
          <span className="font-serif text-[18px] text-ink-primary">
            Cross-section dispersion · trailing 60d
          </span>
        </div>

        {dispData.length === 0 ? (
          <div className="h-[220px] flex items-center justify-center text-sm text-ink-tertiary">
            No dispersion data available.
          </div>
        ) : (
          <ResponsiveContainer width="100%" height={220}>
            <LineChart data={dispData} margin={{ top: 8, right: 12, left: -8, bottom: 0 }}>
              <CartesianGrid strokeDasharray="2 4" stroke={CHART_COLORS.grid} vertical={false} />
              <XAxis
                dataKey="date"
                tick={{ fontSize: 9, fontFamily: 'var(--font-mono)', fill: CHART_COLORS.inkTertiary }}
                tickLine={false}
                axisLine={{ stroke: CHART_COLORS.grid }}
                interval={Math.floor(dispData.length / 5)}
              />
              <YAxis
                tick={{ fontSize: 9, fontFamily: 'var(--font-mono)', fill: CHART_COLORS.inkTertiary }}
                tickLine={false}
                axisLine={false}
                tickFormatter={v => v.toFixed(3)}
                width={40}
              />
              <Tooltip content={<CustomDispersionTooltip />} />
              <Line
                type="monotone"
                dataKey="value"
                stroke={CHART_COLORS.rsLeader}
                strokeWidth={1.8}
                dot={false}
                activeDot={{ r: 3.5, fill: CHART_COLORS.rsLeader }}
              />
            </LineChart>
          </ResponsiveContainer>
        )}

        <p className="text-[12px] text-ink-tertiary mt-2 leading-[1.45]">
          Realized cross-sectional standard deviation of daily returns across Nifty 500.
          {dispData.length > 0 && dispData[dispData.length - 1]?.value != null && (
            <span className="text-signal-pos font-medium">
              {' '}Current: {dispData[dispData.length - 1].value!.toFixed(4)}
            </span>
          )}
        </p>
      </div>

      {/* Right: Sector return bar chart */}
      <div className="bg-paper border border-paper-rule rounded-sm p-5">
        <div className="flex items-baseline justify-between mb-4">
          <span className="font-serif text-[18px] text-ink-primary">
            Sector RS · 1W
          </span>
        </div>

        {sectorData.length === 0 ? (
          <div className="h-[220px] flex items-center justify-center text-sm text-ink-tertiary">
            No sector data available.
          </div>
        ) : (
          <ResponsiveContainer width="100%" height={220}>
            <BarChart
              data={sectorData}
              margin={{ top: 8, right: 12, left: -8, bottom: 40 }}
              layout="vertical"
            >
              <CartesianGrid strokeDasharray="2 4" stroke={CHART_COLORS.grid} horizontal={false} />
              <XAxis
                type="number"
                tick={{ fontSize: 9, fontFamily: 'var(--font-mono)', fill: CHART_COLORS.inkTertiary }}
                tickLine={false}
                axisLine={{ stroke: CHART_COLORS.grid }}
                tickFormatter={v => `${(v * 100).toFixed(0)}%`}
              />
              <YAxis
                type="category"
                dataKey="name"
                tick={{ fontSize: 8, fontFamily: 'var(--font-sans)', fill: CHART_COLORS.inkTertiary }}
                tickLine={false}
                axisLine={false}
                width={68}
              />
              <Tooltip content={<CustomSectorTooltip />} />
              <ReferenceLine x={0} stroke={CHART_COLORS.inkTertiary} strokeWidth={0.8} />
              <Bar dataKey="rs_1w" radius={[0, 1, 1, 0]}>
                {sectorData.map(entry => (
                  <Cell key={entry.fullName} fill={barColor(entry.rs_1w)} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        )}

        <p className="text-[12px] text-ink-tertiary mt-2 leading-[1.45]">
          1W RS across {sectorData.length} sectors.{' '}
          <strong className="text-signal-pos">{posCount} positive</strong>,{' '}
          <strong className="text-signal-neg">{negCount} negative</strong>.
        </p>
      </div>
    </div>
  )
}
