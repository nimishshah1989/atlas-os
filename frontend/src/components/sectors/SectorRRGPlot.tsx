// Recharts scatter plot of sector RS level (Y) vs RS velocity (X) with the
// four RRG quadrants colour-coded. Reads SectorRotationRow rows from the
// `mv_sector_rotation_state` materialized view (see lib/queries/rotation.ts).
//
// This is a new, standalone component for SP02. It does NOT replace the
// existing D3 `RRGChart.tsx`; a later sub-project may decide which one
// the sectors page uses.
'use client'

import {
  CartesianGrid,
  Cell,
  ReferenceLine,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

import { CHART_COLORS } from '@/lib/chart-colors'
import type { RRGQuadrant, SectorRotationRow } from '@/lib/queries/rotation'

// ----------------------------------------------------------------------- //
// Types                                                                   //
// ----------------------------------------------------------------------- //

type Props = {
  data: SectorRotationRow[]
  /** Height in pixels (default 480). */
  height?: number
  /** Show raw `rs_level` on Y-axis instead of `rs_pctile_cross_sector`. */
  useRawRS?: boolean
}

type PlotPoint = {
  sector_name: string
  x: number // rs_velocity
  y: number // rs_pctile_cross_sector | rs_level
  quadrant: RRGQuadrant | null
  sector_state: string | null
}

// ----------------------------------------------------------------------- //
// Constants                                                               //
// ----------------------------------------------------------------------- //

// Quadrant fills mirror the project palette (CHART_COLORS) so the RRG plot
// reads as part of the same family as bubble charts / heatmaps.
const QUADRANT_COLORS: Record<RRGQuadrant, string> = {
  Leading:   CHART_COLORS.rsLeader,        // dark green — strong + improving
  Improving: CHART_COLORS.rsStrong,        // teal — building momentum
  Lagging:   CHART_COLORS.rsLaggard,       // signal-neg — weak + falling
  Weakening: CHART_COLORS.rsConsolidating, // amber — rolling over
}

const FALLBACK_COLOR = CHART_COLORS.inkTertiary

// ----------------------------------------------------------------------- //
// Helpers                                                                 //
// ----------------------------------------------------------------------- //

function parseNum(v: string | null | undefined): number | null {
  if (v == null) return null
  const n = Number(v)
  return Number.isFinite(n) ? n : null
}

function quadrantColor(q: RRGQuadrant | null): string {
  return q ? QUADRANT_COLORS[q] : FALLBACK_COLOR
}

function fmtVelocity(v: number): string {
  return v >= 0 ? `+${v.toFixed(3)}` : v.toFixed(3)
}

// ----------------------------------------------------------------------- //
// Tooltip                                                                 //
// ----------------------------------------------------------------------- //

type TooltipProps = {
  active?: boolean
  payload?: Array<{ payload: PlotPoint }>
}

function RRGTooltip({ active, payload }: TooltipProps) {
  if (!active || !payload?.length) return null
  const d = payload[0].payload
  const xLabel = fmtVelocity(d.x)
  const yLabel = `${(d.y * 100).toFixed(1)}%`
  return (
    <div className="bg-paper border border-paper-rule px-3 py-2 rounded-sm shadow-sm min-w-[180px]">
      <p className="font-sans text-[12px] font-semibold text-ink-primary mb-1">
        {d.sector_name}
      </p>
      <p
        className="font-sans text-[11px] mb-1.5"
        style={{ color: quadrantColor(d.quadrant) }}
      >
        {d.quadrant ?? 'Unknown'}
      </p>
      <p className="font-sans text-[11px] flex justify-between gap-4 text-ink-tertiary">
        <span>RS Percentile</span>
        <span className="font-mono tabular-nums text-ink-primary">{yLabel}</span>
      </p>
      <p className="font-sans text-[11px] flex justify-between gap-4 text-ink-tertiary">
        <span>RS Velocity</span>
        <span className="font-mono tabular-nums text-ink-primary">{xLabel}</span>
      </p>
      {d.sector_state && (
        <p className="font-sans text-[11px] flex justify-between gap-4 text-ink-tertiary">
          <span>State</span>
          <span className="text-ink-primary">{d.sector_state}</span>
        </p>
      )}
    </div>
  )
}

// ----------------------------------------------------------------------- //
// Main component                                                          //
// ----------------------------------------------------------------------- //

export function SectorRRGPlot({ data, height = 480, useRawRS = false }: Props) {
  const points: PlotPoint[] = data.flatMap((row) => {
    const x = parseNum(row.rs_velocity)
    const y = useRawRS ? parseNum(row.rs_level) : parseNum(row.rs_pctile_cross_sector)
    if (x === null || y === null) return []
    return [{
      sector_name:  row.sector_name,
      x,
      y,
      quadrant:     (row.rrg_quadrant as RRGQuadrant | null) ?? null,
      sector_state: row.sector_state ?? null,
    }]
  })

  if (points.length === 0) {
    return (
      <div className="flex h-48 items-center justify-center text-sm text-ink-tertiary">
        No sector rotation data available
      </div>
    )
  }

  // Y-axis: 0–1 for percentile view, auto for raw RS level.
  const yDomain: [number, number] | ['auto', 'auto'] = useRawRS
    ? ['auto', 'auto']
    : [0, 1]
  const yTickFormatter = useRawRS
    ? (v: number) => v.toFixed(2)
    : (v: number) => `${(v * 100).toFixed(0)}%`

  return (
    <div className="w-full" style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        <ScatterChart margin={{ top: 24, right: 24, bottom: 48, left: 24 }}>
          <CartesianGrid strokeDasharray="3 3" stroke={CHART_COLORS.grid} />

          {/* Quadrant dividers — vertical at velocity=0, horizontal at median RS */}
          <ReferenceLine
            x={0}
            stroke={CHART_COLORS.inkTertiary}
            strokeWidth={1.25}
            strokeDasharray="6 3"
            label={{
              value: 'Velocity = 0',
              position: 'insideTopRight',
              fontSize: 11,
              fill: CHART_COLORS.inkTertiary,
            }}
          />
          <ReferenceLine
            y={useRawRS ? 1 : 0.5}
            stroke={CHART_COLORS.inkTertiary}
            strokeWidth={1.25}
            strokeDasharray="6 3"
            label={{
              value: useRawRS ? 'RS = 1.0' : 'Median RS',
              position: 'insideTopLeft',
              fontSize: 11,
              fill: CHART_COLORS.inkTertiary,
            }}
          />

          <XAxis
            type="number"
            dataKey="x"
            name="RS Velocity"
            label={{
              value: 'RS Velocity (4-week RoC)',
              position: 'insideBottom',
              offset: -16,
              fontSize: 12,
              fill: CHART_COLORS.inkTertiary,
            }}
            tickFormatter={(v: number) =>
              v >= 0 ? `+${v.toFixed(2)}` : v.toFixed(2)
            }
            tick={{ fontSize: 11 }}
            stroke={CHART_COLORS.grid}
          />
          <YAxis
            type="number"
            dataKey="y"
            name={useRawRS ? 'RS Level' : 'RS Percentile'}
            domain={yDomain}
            tickFormatter={yTickFormatter}
            label={{
              value: useRawRS ? 'RS Level' : 'RS Percentile (cross-sector)',
              angle: -90,
              position: 'insideLeft',
              fontSize: 12,
              fill: CHART_COLORS.inkTertiary,
            }}
            tick={{ fontSize: 11 }}
            stroke={CHART_COLORS.grid}
          />

          <Tooltip
            content={<RRGTooltip />}
            cursor={{ strokeDasharray: '3 3' }}
          />

          <Scatter name="Sectors" data={points}>
            {points.map((entry, idx) => (
              <Cell
                key={`cell-${idx}`}
                fill={quadrantColor(entry.quadrant)}
                stroke={quadrantColor(entry.quadrant)}
                strokeWidth={1}
                fillOpacity={0.85}
              />
            ))}
          </Scatter>
        </ScatterChart>
      </ResponsiveContainer>
    </div>
  )
}

export default SectorRRGPlot
