'use client'
import { useEffect, useRef } from 'react'
import * as d3 from 'd3'
import type { SectorSnapshot, RRGHistoryRow } from '@/lib/queries/sectors'
import { CHART_COLORS } from '@/lib/chart-colors'

// Oldest → newest. Index 0 = T-4, index 4 = T-0 (today).
const TRAIL_OPACITIES = [0.20, 0.35, 0.55, 0.75, 1.0]

const FALLBACK_COLOR = '#8C8278' // matches CHART_COLORS.inkTertiary

const MOM_COLOR: Record<string, string> = {
  Accelerating:  CHART_COLORS.momAccelerating,
  Improving:     CHART_COLORS.momImproving,
  Flat:          CHART_COLORS.momFlat,
  Deteriorating: CHART_COLORS.momDeteriorating,
  Collapsing:    CHART_COLORS.momCollapsing,
}

type Props = {
  current: SectorSnapshot[]
  history: RRGHistoryRow[]
  onSelect: (sectorName: string) => void
  width?: number
  height?: number
}

type ChartDatum = SectorSnapshot & {
  xRaw: number | null
  yRaw: number | null
  x: number | null
  y: number | null
}

type TrailDatum = RRGHistoryRow & { x: number; y: number }

export function RRGChart({
  current,
  history,
  onSelect,
  width = 720,
  height = 540,
}: Props) {
  const svgRef = useRef<SVGSVGElement>(null)
  // Stable handler ref so re-renders don't tear down the SVG.
  const selectRef = useRef(onSelect)
  selectRef.current = onSelect

  useEffect(() => {
    if (!svgRef.current || current.length === 0) return

    const margin = { top: 40, right: 160, bottom: 50, left: 60 }
    const innerW = width - margin.left - margin.right
    const innerH = height - margin.top - margin.bottom

    // ---- Parse + mean-center ----
    const currentWithFloat: ChartDatum[] = current.map((s) => ({
      ...s,
      xRaw: s.bottomup_rs_3m_nifty500 != null ? parseFloat(s.bottomup_rs_3m_nifty500) : null,
      yRaw: s.rs_momentum != null ? parseFloat(s.rs_momentum) : null,
      x: null,
      y: null,
    }))

    const validX = currentWithFloat
      .map((s) => s.xRaw)
      .filter((v): v is number => v != null && !Number.isNaN(v))
    const validY = currentWithFloat
      .map((s) => s.yRaw)
      .filter((v): v is number => v != null && !Number.isNaN(v))

    const meanX = validX.length > 0 ? (d3.mean(validX) ?? 0) : 0
    const meanY = validY.length > 0 ? (d3.mean(validY) ?? 0) : 0

    const chartData: ChartDatum[] = currentWithFloat.map((s) => ({
      ...s,
      x: s.xRaw != null && !Number.isNaN(s.xRaw) ? s.xRaw - meanX : null,
      y: s.yRaw != null && !Number.isNaN(s.yRaw) ? s.yRaw - meanY : null,
    }))

    // ---- History: filter NULLs, apply same centering ----
    const validHistory: TrailDatum[] = history
      .filter((r) => r.rs !== null && r.momentum !== null)
      .map((r) => ({
        ...r,
        x: (r.rs as number) - meanX,
        y: (r.momentum as number) - meanY,
      }))

    const historyBySector: Map<string, TrailDatum[]> = d3.group(
      validHistory,
      (d) => d.sector_name,
    )

    // ---- Scales over union of trails + dots ----
    const allX: number[] = [
      ...chartData.filter((s) => s.x != null).map((s) => s.x as number),
      ...validHistory.map((r) => r.x),
    ]
    const allY: number[] = [
      ...chartData.filter((s) => s.y != null).map((s) => s.y as number),
      ...validHistory.map((r) => r.y),
    ]

    const xExtent = (d3.extent(allX) as [number, number]) ?? [-1, 1]
    const yExtent = (d3.extent(allY) as [number, number]) ?? [-1, 1]
    const xPad = (xExtent[1] - xExtent[0]) * 0.15 || 0.1
    const yPad = (yExtent[1] - yExtent[0]) * 0.15 || 0.1

    const xScale = d3
      .scaleLinear()
      .domain([xExtent[0] - xPad, xExtent[1] + xPad])
      .range([0, innerW])
    const yScale = d3
      .scaleLinear()
      .domain([yExtent[0] - yPad, yExtent[1] + yPad])
      .range([innerH, 0])

    // ---- Clear and rebuild ----
    d3.select(svgRef.current).selectAll('*').remove()
    const svg = d3
      .select(svgRef.current)
      .attr('width', width)
      .attr('height', height)
      .attr('role', 'img')
      .attr(
        'aria-label',
        `Sector Relative Rotation Graph — ${current.length} sectors`,
      )

    const g = svg.append('g').attr('transform', `translate(${margin.left},${margin.top})`)

    // ---- Crosshair at (0,0) ----
    g.append('line')
      .attr('x1', xScale(0))
      .attr('x2', xScale(0))
      .attr('y1', 0)
      .attr('y2', innerH)
      .attr('stroke', 'var(--color-paper-rule)')
      .attr('stroke-width', 1)
    g.append('line')
      .attr('x1', 0)
      .attr('x2', innerW)
      .attr('y1', yScale(0))
      .attr('y2', yScale(0))
      .attr('stroke', 'var(--color-paper-rule)')
      .attr('stroke-width', 1)

    // ---- Quadrant watermark labels ----
    // Place labels at ~60% of each axis extent, falling back to ±0.3 if extent collapses.
    const quadX = xExtent[1] * 0.6 || 0.3
    const quadY = yExtent[1] * 0.6 || 0.3
    const quadXNeg = xExtent[0] * 0.6 || -0.3
    const quadYNeg = yExtent[0] * 0.6 || -0.3
    const quadLabels = [
      { x: xScale(quadX),    y: yScale(quadY),    text: 'Leading' },
      { x: xScale(quadX),    y: yScale(quadYNeg), text: 'Weakening' },
      { x: xScale(quadXNeg), y: yScale(quadY),    text: 'Improving' },
      { x: xScale(quadXNeg), y: yScale(quadYNeg), text: 'Lagging' },
    ]
    g.selectAll('.ql')
      .data(quadLabels)
      .join('text')
      .attr('x', (d) => d.x)
      .attr('y', (d) => d.y)
      .attr('text-anchor', 'middle')
      .attr('dominant-baseline', 'middle')
      .attr('font-family', 'var(--font-serif)')
      .attr('font-size', '28px')
      .attr('font-weight', '300')
      .attr('fill', 'var(--color-ink-primary)')
      .attr('opacity', 0.12)
      .attr('aria-hidden', 'true')
      .text((d) => d.text)

    // ---- Trailing dots (oldest → newest, opacity ramps) ----
    for (const [sectorName, sectorHistory] of historyBySector) {
      const last5 = sectorHistory.slice(-5)
      const sectorCurrent = chartData.find((s) => s.sector_name === sectorName)
      const color = sectorCurrent
        ? MOM_COLOR[sectorCurrent.bottomup_momentum_state ?? ''] ?? FALLBACK_COLOR
        : FALLBACK_COLOR
      last5.forEach((row, i) => {
        g.append('circle')
          .attr('cx', xScale(row.x))
          .attr('cy', yScale(row.y))
          .attr('r', 4)
          .attr('fill', color)
          .attr('opacity', TRAIL_OPACITIES[i] ?? 1.0)
          .attr('pointer-events', 'none')
      })
    }

    // ---- Main dots ----
    const plottable = chartData.filter(
      (s): s is ChartDatum & { x: number; y: number } => s.x != null && s.y != null,
    )

    const dots = g
      .selectAll<SVGGElement, (typeof plottable)[number]>('.sector-dot')
      .data(plottable)
      .join('g')
      .attr('class', 'sector-dot')
      .attr('transform', (s) => `translate(${xScale(s.x)},${yScale(s.y)})`)
      .attr('tabindex', (_, i) => (i === 0 ? 0 : -1))
      .attr('role', 'button')
      .attr('aria-label', (s) => `${s.sector_name} sector`)
      .style('cursor', 'pointer')
      .on('click', (_event, s) => selectRef.current(s.sector_name))
      .on('keydown', (event: KeyboardEvent, s) => {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault()
          selectRef.current(s.sector_name)
        }
      })

    dots
      .append('circle')
      .attr('r', (s) =>
        Math.max(6, Math.min(18, Math.sqrt(s.constituent_count ?? 1) * 2.5)),
      )
      .attr('fill', (s) => MOM_COLOR[s.bottomup_momentum_state ?? ''] ?? FALLBACK_COLOR)
      .attr('opacity', 0.85)

    dots
      .append('text')
      .attr('dx', 8)
      .attr('dy', 4)
      .attr('font-family', 'var(--font-sans)')
      .attr('font-size', '10px')
      .attr('fill', 'var(--color-ink-primary)')
      .text((s) =>
        s.sector_name.length > 12 ? s.sector_name.slice(0, 12) + '…' : s.sector_name,
      )

    // ---- Axes ----
    const xFmt = d3.format('.2f')
    const yFmt = d3.format('.3f')

    g.append('g')
      .attr('transform', `translate(0,${innerH})`)
      .call(
        d3
          .axisBottom(xScale)
          .ticks(5)
          .tickFormat((d) => xFmt(d as number)),
      )
      .selectAll('text')
      .attr('font-family', 'var(--font-sans)')
      .attr('font-size', '10px')
      .attr('fill', 'var(--color-ink-tertiary)')

    g.append('g')
      .call(
        d3
          .axisLeft(yScale)
          .ticks(5)
          .tickFormat((d) => yFmt(d as number)),
      )
      .selectAll('text')
      .attr('font-family', 'var(--font-sans)')
      .attr('font-size', '10px')
      .attr('fill', 'var(--color-ink-tertiary)')

    // ---- Axis labels ----
    svg
      .append('text')
      .attr('x', margin.left + innerW / 2)
      .attr('y', height - 8)
      .attr('text-anchor', 'middle')
      .attr('font-family', 'var(--font-sans)')
      .attr('font-size', '10px')
      .attr('fill', 'var(--color-ink-tertiary)')
      .text('RS Strength (3M vs Nifty500)')

    svg
      .append('text')
      .attr('transform', `translate(14,${margin.top + innerH / 2}) rotate(-90)`)
      .attr('text-anchor', 'middle')
      .attr('font-family', 'var(--font-sans)')
      .attr('font-size', '10px')
      .attr('fill', 'var(--color-ink-tertiary)')
      .text('RS Momentum (T vs T-20)')

    // ---- Right-side legend (sorted by quadrant) ----
    const quadOrder = (s: (typeof plottable)[number]): number => {
      if (s.x >= 0 && s.y >= 0) return 1 // Leading
      if (s.x >= 0 && s.y < 0) return 2 // Weakening
      if (s.x < 0 && s.y >= 0) return 3 // Improving
      return 4 // Lagging
    }
    const sorted = [...plottable].sort((a, b) => quadOrder(a) - quadOrder(b))
    const legend = svg
      .append('g')
      .attr('transform', `translate(${margin.left + innerW + 12},${margin.top})`)
    sorted.forEach((s, i) => {
      const yPos = i * 16
      if (yPos > innerH) return
      const color = MOM_COLOR[s.bottomup_momentum_state ?? ''] ?? FALLBACK_COLOR
      legend
        .append('circle')
        .attr('cx', 5)
        .attr('cy', yPos + 5)
        .attr('r', 4)
        .attr('fill', color)
      legend
        .append('text')
        .attr('x', 14)
        .attr('y', yPos + 9)
        .attr('font-family', 'var(--font-sans)')
        .attr('font-size', '9px')
        .attr('fill', 'var(--color-ink-secondary)')
        .text(
          s.sector_name.length > 14
            ? s.sector_name.slice(0, 14) + '…'
            : s.sector_name,
        )
    })
  }, [current, history, width, height])

  if (current.length === 0) {
    return (
      <div className="flex items-center justify-center h-64 text-ink-tertiary font-sans text-sm">
        Add at least 3 sectors with 20+ days of history to view the rotation graph.
      </div>
    )
  }

  return (
    <div className="overflow-x-auto">
      <svg ref={svgRef} />
    </div>
  )
}
