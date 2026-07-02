'use client'
// frontend/src/components/sectors/SectorRRGChart.tsx
// Relative Rotation Graph — Recharts ScatterChart with SVG trail polylines.
// Data from atlas.mv_sector_rrg (rs_ratio_current / rs_momentum_current / trail_6w).
//
// Quadrant definitions (from migration 104):
//   Leading   — rs_ratio >= 100 AND rs_momentum >= 0  (top-right, sig-pos)
//   Improving — rs_ratio <  100 AND rs_momentum >= 0  (top-left, brand)
//   Lagging   — rs_ratio <  100 AND rs_momentum <  0  (bottom-left, sig-neg)
//   Weakening — rs_ratio >= 100 AND rs_momentum <  0  (bottom-right, sig-warn)
//
// Theme-aware: all chart colours (quadrant fills, grid, reference lines, axis ticks
// and labels) resolve from useThemeTokens so the graph recolours live with the
// day/night toggle. Off-theme/pre-mount the hook returns null → neutral fallbacks.
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
import type { SectorRRGRow, TrailEntry } from '@/lib/queries/sectors'
import { useThemeTokens, type ThemeTokens } from '@/components/ui/useThemeTokens'

// ── Quadrant → theme token colour ─────────────────────────────────────────────

type Quad = 'Leading' | 'Improving' | 'Lagging' | 'Weakening'

// Neutral fallbacks for off-theme / pre-mount (mirror StocksBubble2x2 fallbacks).
const FALLBACK = { pos: '#2F6B43', brand: '#1D9E75', neg: '#B0492C', warn: '#C68B2E', null: '#888888' }

function quadColor(q: string | null, t: ThemeTokens | null): string {
  const map: Record<Quad, string> = {
    Leading:   t?.pos ?? FALLBACK.pos,
    Improving: t?.brand ?? FALLBACK.brand,
    Lagging:   t?.neg ?? FALLBACK.neg,
    Weakening: t?.warn ?? FALLBACK.warn,
  }
  if (!q) return t?.tick ?? FALLBACK.null
  return map[q as Quad] ?? (t?.tick ?? FALLBACK.null)
}

// ── Radius by constituent count (3 buckets) ───────────────────────────────────

function dotRadius(count: number): number {
  if (count >= 60) return 14
  if (count >= 30) return 10
  return 7
}

// ── Custom dot with label ─────────────────────────────────────────────────────

// shape prop from Recharts Scatter is untyped at the library level
function makeCustomDot(t: ThemeTokens | null) {
  const txt1 = t?.txt1 ?? '#1A1714'
  const txt2 = t?.txt2 ?? '#3D362E'
  return function CustomDot(props: any) { // NOSONAR: Recharts shape props are untyped
    const { cx, cy, payload } = props as {
      cx: number
      cy: number
      payload: SectorRRGRow & { x: number; y: number }
    }

    if (cx == null || cy == null) return null

    const q = payload.quadrant_current
    const color = quadColor(q, t)
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
          fill={txt1}
        >
          {payload.sector_name}
        </text>
        <text
          x={labelX}
          y={labelY + 12}
          fontFamily="'JetBrains Mono', Consolas, monospace"
          fontSize={9}
          fill={txt2}
        >
          {payload.constituent_count ?? 0}
          {payload.rs_ratio_current != null
            ? ` · ${payload.rs_ratio_current > 100 ? '+' : ''}${(payload.rs_ratio_current - 100).toFixed(1)}`
            : ''}
        </text>
      </g>
    )
  }
}

// ── Custom tooltip ────────────────────────────────────────────────────────────

type RRGPayload = SectorRRGRow & { x: number; y: number; isTrail?: boolean }

// Recharts tooltip content — receives active + payload injected by Recharts internals.
// The Recharts TooltipProps type doesn't match the runtime shape well; use a local type.
type RRGTooltipArgs = { active?: boolean; payload?: Array<{ payload: RRGPayload }> }

function makeRRGTooltip(t: ThemeTokens | null) {
  return function RRGTooltip({ active, payload }: RRGTooltipArgs) {
    if (!active || !payload?.[0]) return null
    const d = payload[0].payload
    const q = d.quadrant_current ?? 'Unknown'
    const color = quadColor(d.quadrant_current, t)

    return (
      <div className="bg-surface-raised border border-edge-rule rounded-tile p-3 shadow-panel min-w-[180px]">
        <div className="font-display text-[15px] text-txt-1 mb-1">{d.sector_name}</div>
        <div
          className="inline-block font-num text-[10px] font-semibold uppercase tracking-wider px-1.5 py-0.5 rounded-tile mb-2"
          style={{ background: `color-mix(in srgb, ${color} 14%, transparent)`, color, border: `1px solid color-mix(in srgb, ${color} 35%, transparent)` }}
        >
          {q}
        </div>
        <div className="space-y-0.5 font-num text-[11px] tabular-nums text-txt-2">
          <div>RS-ratio: <span className="text-txt-1">{d.rs_ratio_current?.toFixed(2) ?? '—'}</span></div>
          <div>RS-momentum: <span className={`font-semibold ${(d.rs_momentum_current ?? 0) >= 0 ? 'text-sig-pos' : 'text-sig-neg'}`}>
            {d.rs_momentum_current != null ? `${d.rs_momentum_current >= 0 ? '+' : ''}${d.rs_momentum_current.toFixed(2)}` : '—'}
          </span></div>
          <div>Constituents: <span className="text-txt-1">{d.constituent_count ?? 0}</span></div>
          {d.trail_6w.length > 0 && (
            <div className="text-txt-3">Trail: {d.trail_6w.length}w history</div>
          )}
        </div>
        <div className="mt-2 pt-2 border-t border-edge-hair">
          <Link
            href={`/sectors/${encodeURIComponent(d.sector_name)}`}
            className="text-[11px] text-brand font-medium hover:underline"
          >
            Open deep-dive →
          </Link>
        </div>
      </div>
    )
  }
}

// ── Trail polyline overlay via Recharts customized prop ───────────────────────
// Recharts passes xAxisMap / yAxisMap into any element in the `customized` prop,
// giving access to the d3 scale functions that map domain values → pixel coords.
// We use those to draw SVG <polyline> elements for each sector's 6-week trail.
// (If trail_6w is empty for a sector, that sector simply renders no polyline —
// no points are fabricated.)

type ScaleFunc = (v: number) => number | undefined

interface TrailOverlayProps {
  // Injected by Recharts via customized prop
  xAxisMap?: Record<string, { scale?: ScaleFunc }>
  yAxisMap?: Record<string, { scale?: ScaleFunc }>
  // Our own props — must be passed through customized element creation below
  sectors?: SectorRRGRow[]
  theme?: ThemeTokens | null
}

function TrailOverlayBase({ xAxisMap, yAxisMap, sectors = [], theme = null }: TrailOverlayProps) {
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

        const color = quadColor(sector.quadrant_current, theme)
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
function TrailOverlay({ sectors, theme, ...chartProps }: TrailOverlayProps & { sectors: SectorRRGRow[] }) {
  return <TrailOverlayBase sectors={sectors} theme={theme} {...chartProps} />
}

// ── Quadrant legend ───────────────────────────────────────────────────────────

function QuadrantLegend({ data, theme }: { data: SectorRRGRow[]; theme: ThemeTokens | null }) {
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
      <div className="rounded-tile border border-edge-hair bg-surface-inset/40 p-4">
        <div className="font-num text-[10px] uppercase tracking-[0.18em] text-txt-3 font-semibold mb-3">
          Four quadrants · today
        </div>
        {quadrants.map(({ key, desc }) => (
          <div key={key} className="flex items-start gap-2.5 mb-2 last:mb-0">
            <span
              className="w-2.5 h-2.5 rounded-full mt-[3px] shrink-0"
              style={{ background: quadColor(key, theme) }}
              aria-hidden="true"
            />
            <div>
              <div className="text-[12px] font-semibold text-txt-2">
                {key}{' '}
                <span
                  className="font-num tabular-nums"
                  style={{ color: quadColor(key, theme) }}
                >
                  {counts[key]}
                </span>
              </div>
              <div className="text-[11px] text-txt-3 leading-[1.4]">{desc}</div>
            </div>
          </div>
        ))}
      </div>

      <div className="rounded-tile border border-edge-hair bg-surface-inset/40 p-4">
        <div className="font-num text-[10px] uppercase tracking-[0.18em] text-txt-3 font-semibold mb-2">
          How to read the RRG
        </div>
        <div className="text-[11.5px] text-txt-2 leading-[1.55] space-y-1.5">
          <div>Sectors rotate <strong className="font-medium text-txt-1">counter-clockwise</strong>: Leading → Weakening → Lagging → Improving → back.</div>
          <div><strong className="font-medium text-txt-1">X-axis</strong>: RS-ratio vs Nifty 500. Divider = the sector median, so right = stronger-than-peers, left = weaker.</div>
          <div><strong className="font-medium text-txt-1">Y-axis</strong>: RS-momentum (rate-of-change). Above 0 = accelerating RS.</div>
          <div>Bubble size = # constituents. Trail = 6-week history.</div>
        </div>
      </div>
    </div>
  )
}

// ── Main exported component ───────────────────────────────────────────────────

export function SectorRRGChart({ data }: { data: SectorRRGRow[] }) {
  const router = useRouter()
  const t = useThemeTokens()

  const handleClick = useCallback((d: SectorRRGRow) => {
    router.push(`/sectors/${encodeURIComponent(d.sector_name)}`)
  }, [router])

  // Filter rows with valid position data
  const validData = data.filter(
    (d) => d.rs_ratio_current != null && d.rs_momentum_current != null,
  )

  // The MV's rs_ratio is currently mis-normalised — every sector lands above 100, so an
  // x=100 divider pins them all in the right half (no Lagging/red, trails off-screen).
  // Until the MV is re-normalised, divide on the cross-sectional MEDIAN rs_ratio so the
  // graph reads as a true RELATIVE rotation: ~half the sectors fall left (Improving/Lagging,
  // incl. red), trails sit inside the domain. Quadrant is recomputed vs the median for the
  // dot colour + legend (the stored quadrant_current assumed the 100 divider).
  const ratiosSorted = [...validData.map((d) => d.rs_ratio_current!)].sort((a, b) => a - b)
  const midRatio = ratiosSorted.length ? ratiosSorted[Math.floor(ratiosSorted.length / 2)] : 100
  const quadVsMid = (x: number, y: number): Quad =>
    x >= midRatio ? (y >= 0 ? 'Leading' : 'Weakening') : (y >= 0 ? 'Improving' : 'Lagging')
  const reData: SectorRRGRow[] = validData.map((d) => ({
    ...d,
    quadrant_current: quadVsMid(d.rs_ratio_current!, d.rs_momentum_current!),
  }))

  // Convert to scatter-ready format
  const scatterData = reData.map((d) => ({
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
  const allX = [...scatterData.map((d) => d.x), ...trailXY.map((t) => t.x)]
  const allY = [...scatterData.map((d) => d.y), ...trailXY.map((t) => t.y), 0]
  // Data-aware domain (with padding) — must INCLUDE the trail points (rs_ratio up to ~165)
  // so trails render inside the plot instead of being clipped off the right edge.
  const dataXMin = Math.min(...allX) - 3
  const dataXMax = Math.max(...allX) + 3
  const dataYMin = Math.min(...allY) - 2
  const dataYMax = Math.max(...allY) + 2
  // Cap only against pathological outliers; otherwise hug the data.
  const xMin = Math.max(dataXMin, 60)
  const xMax = Math.min(dataXMax, 220)
  const yMin = Math.max(dataYMin, -60)
  const yMax = Math.min(dataYMax, 60)

  // Theme-resolved chart chrome colours (neutral fallbacks pre-mount / off-theme)
  const grid = t?.grid ?? '#88888822'
  const axisLine = t?.rule ?? '#88888844'
  const tick = t?.tick ?? '#888888'
  const axisLabel = t?.label ?? '#888888'
  const zeroLine = t?.txt2 ?? '#3D362E'

  const CustomDot = makeCustomDot(t)
  const RRGTooltip = makeRRGTooltip(t)

  if (validData.length === 0) {
    return (
      <div className="flex items-center justify-center h-[560px] rounded-tile border border-edge-hair bg-surface-inset/40 text-txt-3 font-sans text-sm">
        RRG data unavailable — no rs_ratio or rs_momentum computed for latest snapshot.
      </div>
    )
  }

  return (
    <div className="grid grid-cols-[2fr_1fr] gap-4" aria-label="Sector Relative Rotation Graph">
      <div className="rounded-tile border border-edge-hair bg-surface-inset/40 p-5">
        {/* Controls */}
        <div className="flex items-center justify-between mb-3">
          <div>
            <div className="font-display text-[18px] text-txt-1">Sector rotation graph</div>
            <div className="text-[12px] text-txt-3 mt-0.5">
              RS-ratio (x) vs RS-momentum (y) — 6-week trail per sector
            </div>
          </div>
        </div>

        <ResponsiveContainer width="100%" height={520}>
          <ScatterChart margin={{ top: 20, right: 80, bottom: 40, left: 40 }}>
            <CartesianGrid strokeDasharray="2 4" stroke={grid} />

            {/* Quadrant divider on the MEDIAN rs_ratio (see note above) + momentum=0 */}
            <ReferenceLine x={midRatio} stroke={zeroLine} strokeWidth={0.8} />
            <ReferenceLine y={0} stroke={zeroLine} strokeWidth={0.8} />

            <XAxis
              type="number"
              dataKey="x"
              domain={[xMin, xMax]}
              tickFormatter={(v: number) => v.toFixed(0)}
              tick={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 10, fill: tick }}
              stroke={axisLine}
            >
              <Label
                value="RS-ratio vs Nifty 500 — divider = sector median (relative rotation)"
                position="insideBottom"
                offset={-20}
                style={{ fontFamily: 'Inter, sans-serif', fontSize: 11, fill: axisLabel, fontWeight: 600 }}
              />
            </XAxis>
            <YAxis
              type="number"
              dataKey="y"
              domain={[yMin, yMax]}
              tickFormatter={(v: number) => v.toFixed(1)}
              tick={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 10, fill: tick }}
              stroke={axisLine}
            >
              <Label
                value="RS-momentum (rate of change)"
                angle={-90}
                position="insideLeft"
                offset={10}
                style={{ fontFamily: 'Inter, sans-serif', fontSize: 11, fill: axisLabel, fontWeight: 600 }}
              />
            </YAxis>

            <Tooltip content={<RRGTooltip />} />

            {/* Trail polylines — Recharts 3.x injects xAxisMap/yAxisMap into direct children */}
            <TrailOverlay sectors={reData} theme={t} />

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

      <QuadrantLegend data={reData} theme={t} />
    </div>
  )
}
