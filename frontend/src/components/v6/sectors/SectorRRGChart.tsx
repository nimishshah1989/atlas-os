'use client'
// frontend/src/components/v6/sectors/SectorRRGChart.tsx
// Relative Rotation Graph — Recharts ScatterChart with SVG trail polylines.
// Data from atlas.mv_sector_rrg (rs_ratio_current / rs_momentum_current / trail_6w).
//
// Quadrant definitions (from migration 104):
//   Leading   — rs_ratio >= 100 AND rs_momentum >= 0  (top-right, green)
//   Improving — rs_ratio <  100 AND rs_momentum >= 0  (top-left, teal)
//   Lagging   — rs_ratio <  100 AND rs_momentum <  0  (bottom-left, red)
//   Weakening — rs_ratio >= 100 AND rs_momentum <  0  (bottom-right, amber)
//
// Trail approach: SVG <polyline> overlay per sector via Recharts `customized` prop.
// Each trail is sorted oldest-first from trail_6w JSONB, then the current position
// appended as the final point. The customized prop receives the scale functions
// from the parent chart, so pixel coordinates match the axis domain exactly.

import { useCallback } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import {
  ScatterChart, Scatter, XAxis, YAxis, CartesianGrid,
  ReferenceLine, Tooltip, ResponsiveContainer, Label,
} from 'recharts'
import type { SectorRRGRow, TrailEntry } from '@/lib/queries/v6/sectors'

// ── Color map by quadrant ─────────────────────────────────────────────────────

const QUADRANT_COLORS: Record<string, string> = {
  Leading:   '#2F6B43',
  Improving: '#1D9E75',
  Lagging:   '#B0492C',
  Weakening: '#B8860B',
}

const QUADRANT_NULL_COLOR = 'var(--color-ink-tertiary, #6B6157)'

function quadrantColor(q: string | null): string {
  if (!q) return QUADRANT_NULL_COLOR
  return QUADRANT_COLORS[q] ?? QUADRANT_NULL_COLOR
}

// ── Radius by constituent count (3 buckets) ───────────────────────────────────

function dotRadius(count: number): number {
  if (count >= 60) return 14
  if (count >= 30) return 10
  return 7
}

// ── Custom dot with label ─────────────────────────────────────────────────────

// shape prop from Recharts Scatter is untyped at the library level
function CustomDot(props: any) { // NOSONAR: Recharts shape props are untyped
  const { cx, cy, payload } = props as {
    cx: number
    cy: number
    payload: SectorRRGRow & { x: number; y: number }
  }

  if (cx == null || cy == null) return null

  const q = payload.quadrant_current
  const color = quadrantColor(q)
  const r = dotRadius(payload.constituent_count ?? 0)
  const labelX = cx + r + 4
  const labelY = cy + 4

  return (
    <g>
      <circle
        cx={cx}
        cy={cy}
        r={r}
        fill={color}
        fillOpacity={0.85}
        data-testid={`rrg-dot-${payload.sector_name}`}
        aria-label={`${payload.sector_name} — ${q ?? 'unknown quadrant'}`}
      />
      <text
        x={labelX}
        y={labelY}
        fontFamily="Inter, -apple-system, sans-serif"
        fontSize={11}
        fontWeight={700}
        fill="var(--color-ink-primary, #1A1714)"
      >
        {payload.sector_name}
      </text>
      <text
        x={labelX}
        y={labelY + 12}
        fontFamily="'JetBrains Mono', Consolas, monospace"
        fontSize={9}
        fill="var(--color-ink-secondary, #3D362E)"
      >
        {payload.constituent_count ?? 0}
        {payload.rs_ratio_current != null
          ? ` · ${payload.rs_ratio_current > 100 ? '+' : ''}${(payload.rs_ratio_current - 100).toFixed(1)}`
          : ''}
      </text>
    </g>
  )
}

// ── Custom tooltip ────────────────────────────────────────────────────────────

type RRGPayload = SectorRRGRow & { x: number; y: number; isTrail?: boolean }

// Recharts tooltip content — receives active + payload injected by Recharts internals.
// The Recharts TooltipProps type doesn't match the runtime shape well; use a local type.
type RRGTooltipArgs = { active?: boolean; payload?: Array<{ payload: RRGPayload }> }

function RRGTooltip({ active, payload }: RRGTooltipArgs) {
  if (!active || !payload?.[0]) return null
  const d = payload[0].payload
  const q = d.quadrant_current ?? 'Unknown'
  const color = quadrantColor(q)

  return (
    <div className="bg-paper border border-paper-rule rounded-[2px] p-3 shadow-md min-w-[180px]">
      <div className="font-serif text-[15px] text-ink-primary mb-1">{d.sector_name}</div>
      <div
        className="inline-block font-mono text-[10px] font-semibold uppercase tracking-wider px-1.5 py-0.5 rounded-[2px] mb-2"
        style={{ background: `${color}22`, color, border: `1px solid ${color}55` }}
      >
        {q}
      </div>
      <div className="space-y-0.5 font-mono text-[11px] text-ink-secondary">
        <div>RS-ratio: <span className="text-ink-primary">{d.rs_ratio_current?.toFixed(2) ?? '—'}</span></div>
        <div>RS-momentum: <span className={`font-semibold ${(d.rs_momentum_current ?? 0) >= 0 ? 'text-signal-pos' : 'text-signal-neg'}`}>
          {d.rs_momentum_current != null ? `${d.rs_momentum_current >= 0 ? '+' : ''}${d.rs_momentum_current.toFixed(2)}` : '—'}
        </span></div>
        <div>Constituents: <span className="text-ink-primary">{d.constituent_count ?? 0}</span></div>
        {d.trail_6w.length > 0 && (
          <div className="text-ink-tertiary">Trail: {d.trail_6w.length}w history</div>
        )}
      </div>
      <div className="mt-2 pt-2 border-t border-paper-rule">
        <Link
          href={`/sectors/${encodeURIComponent(d.sector_name)}`}
          className="text-[11px] text-teal font-medium hover:underline"
        >
          Open deep-dive →
        </Link>
      </div>
    </div>
  )
}

// ── Trail polyline overlay via Recharts customized prop ───────────────────────
// Recharts passes xAxisMap / yAxisMap into any element in the `customized` prop,
// giving access to the d3 scale functions that map domain values → pixel coords.
// We use those to draw SVG <polyline> elements for each sector's 6-week trail.

type ScaleFunc = (v: number) => number | undefined

interface TrailOverlayProps {
  // Injected by Recharts via customized prop
  xAxisMap?: Record<string, { scale?: ScaleFunc }>
  yAxisMap?: Record<string, { scale?: ScaleFunc }>
  // Our own prop — must be passed through customized element creation below
  sectors?: SectorRRGRow[]
}

function TrailOverlayBase({ xAxisMap, yAxisMap, sectors = [] }: TrailOverlayProps) {
  const xScale = xAxisMap ? Object.values(xAxisMap)[0]?.scale : undefined
  const yScale = yAxisMap ? Object.values(yAxisMap)[0]?.scale : undefined

  if (!xScale || !yScale) return null

  return (
    <g data-testid="trail-overlay">
      {sectors.map((sector) => {
        if (!sector.trail_6w?.length) return null
        if (sector.rs_ratio_current == null || sector.rs_momentum_current == null) return null

        // Sort trail oldest-first, then append current position as the endpoint
        const sorted: TrailEntry[] = [...sector.trail_6w]
          .filter((t) => t.rs_ratio != null && t.rs_momentum != null)
          .sort((a, b) => (a.week_end_date < b.week_end_date ? -1 : 1))

        const allPoints: Array<[number, number]> = [
          ...sorted.map((t) => [t.rs_ratio!, t.rs_momentum!] as [number, number]),
          [sector.rs_ratio_current, sector.rs_momentum_current],
        ]

        const pixelPoints = allPoints
          .map(([x, y]) => {
            const px = xScale(x)
            const py = yScale(y)
            return px != null && py != null ? `${px},${py}` : null
          })
          .filter(Boolean)

        if (pixelPoints.length < 2) return null

        const color = quadrantColor(sector.quadrant_current)
        return (
          <polyline
            key={sector.sector_name}
            points={pixelPoints.join(' ')}
            fill="none"
            stroke={color}
            strokeWidth={1.2}
            strokeOpacity={0.42}
            strokeDasharray="3 2"
            data-testid={`trail-${sector.sector_name}`}
          />
        )
      })}
    </g>
  )
}

// Wrapper: renders TrailOverlayBase as a Recharts child element.
// Recharts 3.x injects xAxisMap/yAxisMap into direct children of chart containers.
function TrailOverlay({ sectors, ...chartProps }: TrailOverlayProps & { sectors: SectorRRGRow[] }) {
  return <TrailOverlayBase sectors={sectors} {...chartProps} />
}

// ── Quadrant legend ───────────────────────────────────────────────────────────

function QuadrantLegend({ data }: { data: SectorRRGRow[] }) {
  const counts = {
    Leading:   data.filter((d) => d.quadrant_current === 'Leading').length,
    Improving: data.filter((d) => d.quadrant_current === 'Improving').length,
    Weakening: data.filter((d) => d.quadrant_current === 'Weakening').length,
    Lagging:   data.filter((d) => d.quadrant_current === 'Lagging').length,
  }

  const quadrants: Array<{ key: keyof typeof counts; desc: string }> = [
    { key: 'Leading',   desc: 'Strong RS + rising momentum. Overweight candidates.' },
    { key: 'Weakening', desc: 'Strong RS but momentum fading. Next exit candidates.' },
    { key: 'Improving', desc: 'Weak RS but momentum turning up. Watch closely.' },
    { key: 'Lagging',   desc: 'Weak RS + falling momentum. Underweight / avoid.' },
  ]

  return (
    <div className="space-y-4">
      <div className="bg-paper border border-paper-rule rounded-[2px] p-4">
        <div className="text-[10px] uppercase tracking-[0.18em] text-ink-tertiary font-semibold mb-3">
          Four quadrants · today
        </div>
        {quadrants.map(({ key, desc }) => (
          <div key={key} className="flex items-start gap-2.5 mb-2 last:mb-0">
            <span
              className="w-2.5 h-2.5 rounded-full mt-[3px] shrink-0"
              style={{ background: QUADRANT_COLORS[key] }}
              aria-hidden="true"
            />
            <div>
              <div className="text-[12px] font-semibold text-ink-secondary">
                {key}{' '}
                <span
                  className="font-mono"
                  style={{ color: QUADRANT_COLORS[key] }}
                >
                  {counts[key]}
                </span>
              </div>
              <div className="text-[11px] text-ink-tertiary leading-[1.4]">{desc}</div>
            </div>
          </div>
        ))}
      </div>

      <div className="bg-paper border border-paper-rule rounded-[2px] p-4">
        <div className="text-[10px] uppercase tracking-[0.18em] text-ink-tertiary font-semibold mb-2">
          How to read the RRG
        </div>
        <div className="text-[11.5px] text-ink-secondary leading-[1.55] space-y-1.5">
          <div>Sectors rotate <strong className="font-medium text-ink-primary">counter-clockwise</strong>: Leading → Weakening → Lagging → Improving → back.</div>
          <div><strong className="font-medium text-ink-primary">X-axis</strong>: RS-ratio (100 = parity with Nifty 500). Above 100 = outperforming.</div>
          <div><strong className="font-medium text-ink-primary">Y-axis</strong>: RS-momentum (rate-of-change). Above 0 = accelerating RS.</div>
          <div>Bubble size = # constituents. Trail = 6-week history.</div>
        </div>
      </div>
    </div>
  )
}

// ── Main exported component ───────────────────────────────────────────────────

export function SectorRRGChart({ data }: { data: SectorRRGRow[] }) {
  const router = useRouter()

  const handleClick = useCallback((d: SectorRRGRow) => {
    router.push(`/sectors/${encodeURIComponent(d.sector_name)}`)
  }, [router])

  // Filter rows with valid position data
  const validData = data.filter(
    (d) => d.rs_ratio_current != null && d.rs_momentum_current != null,
  )

  // Convert to scatter-ready format
  const scatterData = validData.map((d) => ({
    ...d,
    x: d.rs_ratio_current!,
    y: d.rs_momentum_current!,
  }))

  // Calculate domain with padding — include trail points in domain calculation
  const trailXY = validData.flatMap((d) =>
    (d.trail_6w ?? [])
      .filter((t) => t.rs_ratio != null && t.rs_momentum != null)
      .map((t) => ({ x: t.rs_ratio!, y: t.rs_momentum! })),
  )

  // Clamp display domain to standard RRG bounds so that one outlier sector
  // (e.g. Conglomerate showing rs_momentum = -194 from a noisy LAG point)
  // doesn't squish all 30 sectors into a tiny cluster at the center.
  // Outliers are still plotted but get pulled to the chart edge.
  const allX = [...scatterData.map((d) => d.x), ...trailXY.map((t) => t.x), 100]
  const allY = [...scatterData.map((d) => d.y), ...trailXY.map((t) => t.y), 0]
  // Data-aware domain (with padding)
  const dataXMin = Math.min(...allX) - 2
  const dataXMax = Math.max(...allX) + 2
  const dataYMin = Math.min(...allY) - 1
  const dataYMax = Math.max(...allY) + 1
  // Standard RRG bounds (cap to keep the chart readable)
  const xMin = Math.max(dataXMin, 85)
  const xMax = Math.min(dataXMax, 130)
  const yMin = Math.max(dataYMin, -15)
  const yMax = Math.min(dataYMax, 25)

  if (validData.length === 0) {
    return (
      <div className="flex items-center justify-center h-[560px] bg-paper border border-paper-rule rounded-[2px] text-ink-tertiary font-sans text-sm">
        RRG data unavailable — no rs_ratio or rs_momentum computed for latest snapshot.
      </div>
    )
  }

  return (
    <div className="grid grid-cols-[2fr_1fr] gap-4" aria-label="Sector Relative Rotation Graph">
      <div className="bg-paper border border-paper-rule rounded-[2px] p-5">
        {/* Controls */}
        <div className="flex items-center justify-between mb-3">
          <div>
            <div className="font-serif text-[18px] text-ink-primary">Sector rotation graph</div>
            <div className="text-[12px] text-ink-tertiary mt-0.5">
              RS-ratio (x) vs RS-momentum (y) — 6-week trail per sector
            </div>
          </div>
        </div>

        <ResponsiveContainer width="100%" height={520}>
          <ScatterChart margin={{ top: 20, right: 80, bottom: 40, left: 40 }}>
            <CartesianGrid strokeDasharray="2 4" stroke="var(--color-ink-rule, #DDD3BF)" opacity={0.6} />

            {/* Quadrant reference lines at x=100 and y=0 */}
            <ReferenceLine x={100} stroke="var(--color-ink-primary, #1A1714)" strokeWidth={0.8} />
            <ReferenceLine y={0} stroke="var(--color-ink-primary, #1A1714)" strokeWidth={0.8} />

            {/* Quadrant background via gradient fills — approximated with rect labels */}
            <XAxis
              type="number"
              dataKey="x"
              domain={[xMin, xMax]}
              tickFormatter={(v: number) => v.toFixed(0)}
              tick={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 10, fill: 'var(--color-ink-tertiary, #6B6157)' }}
              stroke="var(--color-paper-rule, #C2B8A8)"
            >
              <Label
                value="RS-ratio (price vs Nifty 500, rebased to 100)"
                position="insideBottom"
                offset={-20}
                style={{ fontFamily: 'Inter, sans-serif', fontSize: 11, fill: 'var(--color-ink-secondary, #3D362E)', fontWeight: 600 }}
              />
            </XAxis>
            <YAxis
              type="number"
              dataKey="y"
              domain={[yMin, yMax]}
              tickFormatter={(v: number) => v.toFixed(1)}
              tick={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 10, fill: 'var(--color-ink-tertiary, #6B6157)' }}
              stroke="var(--color-paper-rule, #C2B8A8)"
            >
              <Label
                value="RS-momentum (rate of change)"
                angle={-90}
                position="insideLeft"
                offset={10}
                style={{ fontFamily: 'Inter, sans-serif', fontSize: 11, fill: 'var(--color-ink-secondary, #3D362E)', fontWeight: 600 }}
              />
            </YAxis>

            <Tooltip content={<RRGTooltip />} />

            {/* Trail polylines — Recharts 3.x injects xAxisMap/yAxisMap into direct children */}
            <TrailOverlay sectors={validData} />

            {/* Current position dots */}
            <Scatter
              data={scatterData}
              shape={CustomDot}
              onClick={(d) => handleClick(d as unknown as SectorRRGRow)}
              style={{ cursor: 'pointer' }}
            />
          </ScatterChart>
        </ResponsiveContainer>

      </div>

      <QuadrantLegend data={data} />
    </div>
  )
}
