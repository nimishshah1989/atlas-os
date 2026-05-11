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
  height = 640,
}: Props) {
  const svgRef  = useRef<SVGSVGElement>(null)
  const wrapRef = useRef<HTMLDivElement>(null)
  // Stable handler ref so re-renders don't tear down the SVG.
  const selectRef = useRef(onSelect)
  selectRef.current = onSelect

  useEffect(() => {
    const container = wrapRef.current
    if (!container || !svgRef.current || current.length === 0) return

    const totalW  = container.clientWidth || 720
    const margin  = { top: 40, right: 160, bottom: 50, left: 60 }
    const innerW  = totalW - margin.left - margin.right
    const innerH  = height - margin.top - margin.bottom

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

    // ---- Scales from current dots only — history trails are clipped, not scaled ----
    const currentX = chartData.filter((s) => s.x != null).map((s) => s.x as number)
    const currentY = chartData.filter((s) => s.y != null).map((s) => s.y as number)

    const xExtent = (d3.extent(currentX) as [number, number]) ?? [-1, 1]
    const yExtent = (d3.extent(currentY) as [number, number]) ?? [-1, 1]
    const xRange = xExtent[1] - xExtent[0] || 1
    const yRange = yExtent[1] - yExtent[0] || 1
    const xPad = xRange * 0.25
    const yPad = yRange * 0.25

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
      .attr('width', totalW)
      .attr('height', height)
      .attr('role', 'img')
      .attr(
        'aria-label',
        `Sector Relative Rotation Graph — ${current.length} sectors`,
      )

    const clipId = 'rrg-clip'
    svg.append('defs').append('clipPath').attr('id', clipId)
      .append('rect').attr('width', innerW).attr('height', innerH)

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

    // ---- Trailing paths + dots (oldest → newest, opacity ramps, clipped to chart area) ----
    const trailGroup = g.append('g').attr('clip-path', `url(#${clipId})`)
    const lineGen = d3.line<{ px: number; py: number }>()
      .x(d => d.px)
      .y(d => d.py)
      .curve(d3.curveCatmullRom.alpha(0.5))

    // Max pixel distance before we break a trail segment — prevents "teleport" arcs
    // when RS jumps dramatically (e.g. Defence +30pp in 5 days draws a line across the chart)
    const MAX_TRAIL_JUMP = Math.min(innerW, innerH) * 0.35

    for (const [sectorName, sectorHistory] of historyBySector) {
      const last5 = sectorHistory.slice(-5)
      const sectorCurrent = chartData.find((s) => s.sector_name === sectorName)
      const color = sectorCurrent
        ? MOM_COLOR[sectorCurrent.bottomup_momentum_state ?? ''] ?? FALLBACK_COLOR
        : FALLBACK_COLOR

      // Build points: trail history + today's bubble position
      const allPoints = last5.map(r => ({ px: xScale(r.x), py: yScale(r.y) }))
      if (sectorCurrent?.x != null && sectorCurrent?.y != null) {
        allPoints.push({ px: xScale(sectorCurrent.x), py: yScale(sectorCurrent.y) })
      }

      // Split into continuous segments — break wherever two consecutive points
      // are further apart than MAX_TRAIL_JUMP (avoids long "teleport" lines)
      const segments: Array<Array<{ px: number; py: number }>> = []
      let current: Array<{ px: number; py: number }> = []
      for (let i = 0; i < allPoints.length; i++) {
        if (i === 0) { current.push(allPoints[i]); continue }
        const prev = allPoints[i - 1]
        const pt   = allPoints[i]
        const dx = pt.px - prev.px
        const dy = pt.py - prev.py
        const dist = Math.sqrt(dx * dx + dy * dy)
        if (dist > MAX_TRAIL_JUMP) {
          if (current.length >= 2) segments.push(current)
          current = [pt]
        } else {
          current.push(pt)
        }
      }
      if (current.length >= 2) segments.push(current)

      // Draw each continuous segment
      for (const seg of segments) {
        trailGroup.append('path')
          .datum(seg)
          .attr('d', lineGen)
          .attr('fill', 'none')
          .attr('stroke', color)
          .attr('stroke-width', 1.5)
          .attr('stroke-opacity', 0.45)
          .attr('pointer-events', 'none')
      }

      // Draw trail dots with ramping opacity
      last5.forEach((row, i) => {
        trailGroup.append('circle')
          .attr('cx', xScale(row.x))
          .attr('cy', yScale(row.y))
          .attr('r', 3.5)
          .attr('fill', color)
          .attr('opacity', TRAIL_OPACITIES[i] ?? 1.0)
          .attr('pointer-events', 'none')
      })
    }

    // ---- Tooltip (portal to body) ----
    const tip = d3.select(document.body)
      .append('div')
      .style('position', 'fixed')
      .style('pointer-events', 'none')
      .style('opacity', '0')
      .style('background', '#fff')
      .style('border', '1px solid #e2e8f0')
      .style('border-radius', '2px')
      .style('padding', '10px 12px')
      .style('font-family', 'var(--font-sans)')
      .style('font-size', '11px')
      .style('color', '#1e293b')
      .style('z-index', '9999')
      .style('box-shadow', '0 2px 8px rgba(0,0,0,0.10)')
      .style('min-width', '180px')
      .style('max-width', '220px')

    function quadrantLabel(x: number, y: number): string {
      if (x >= 0 && y >= 0) return 'Leading ↗'
      if (x >= 0 && y <  0) return 'Weakening ↘'
      if (x <  0 && y >= 0) return 'Improving ↖'
      return 'Lagging ↙'
    }

    function trailSummary(sectorName: string, currentX: number, currentY: number): string {
      const trail = historyBySector.get(sectorName)
      if (!trail || trail.length < 2) return 'Insufficient trail data'
      const oldest = trail[Math.max(0, trail.length - 5)]
      const dx = currentX - (oldest.x - meanX)
      const dy = currentY - (oldest.y - meanY)
      const dist = Math.sqrt(dx * dx + dy * dy)
      const speed = dist < 0.01 ? 'stationary' : dist < 0.03 ? 'slow' : dist < 0.06 ? 'moderate' : 'fast'
      // Cross product z-component to detect clockwise vs counter-clockwise
      // Using two consecutive vectors from trail
      const mid = trail[Math.floor(trail.length / 2)]
      const v1x = mid.x - meanX - (oldest.x - meanX)
      const v1y = mid.y - meanY - (oldest.y - meanY)
      const v2x = dx
      const v2y = dy
      const cross = v1x * v2y - v1y * v2x
      const rotation = cross > 0 ? 'clockwise' : 'counter-clockwise'
      const dirText = dx > 0.01 ? 'gaining RS' : dx < -0.01 ? 'losing RS' : 'RS stable'
      const momText = dy > 0.005 ? 'momentum rising' : dy < -0.005 ? 'momentum fading' : 'flat momentum'
      return `${dirText}, ${momText} · ${speed} ${rotation}`
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
      .on('mouseenter', (event: MouseEvent, s) => {
        const color = MOM_COLOR[s.bottomup_momentum_state ?? ''] ?? FALLBACK_COLOR
        const qLabel = quadrantLabel(s.x, s.y)
        const summary = trailSummary(s.sector_name, s.x, s.y)
        const rsStr = `${s.x >= 0 ? '+' : ''}${(s.x * 100).toFixed(1)}%`
        const momStr = s.yRaw != null ? `${s.yRaw >= 0 ? '+' : ''}${(s.yRaw).toFixed(3)}` : '—'
        tip
          .style('opacity', '1')
          .style('left', `${(event.clientX as number) + 14}px`)
          .style('top',  `${(event.clientY as number) - 30}px`)
          .html(`
            <div style="font-weight:700;font-size:12px;margin-bottom:6px">${s.sector_name}</div>
            <div style="display:flex;align-items:center;gap:6px;margin-bottom:4px">
              <span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:${color};flex-shrink:0"></span>
              <span style="font-weight:600;color:#1e293b">${qLabel}</span>
            </div>
            <div style="color:#64748b;margin-bottom:2px;line-height:1.5">${summary}</div>
            <div style="border-top:1px solid #e2e8f0;margin:6px 0 4px"></div>
            <div style="color:#64748b">RS 3M: <span style="color:#1e293b;font-weight:600">${rsStr} vs Nifty500</span></div>
            <div style="color:#64748b">Momentum: <span style="color:#1e293b">${momStr}</span> · <span style="color:${color}">${s.bottomup_momentum_state ?? '—'}</span></div>
            <div style="margin-top:4px;color:#94a3b8;font-size:10px">Click to open sector deep dive</div>
          `)
      })
      .on('mousemove', (event: MouseEvent) => {
        tip.style('left', `${(event.clientX as number) + 14}px`).style('top', `${(event.clientY as number) - 30}px`)
      })
      .on('mouseleave', () => {
        tip.style('opacity', '0')
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
        s.sector_name.length > 14 ? s.sector_name.slice(0, 14) + '…' : s.sector_name,
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
    return () => { tip.remove() }
  }, [current, history, height])

  if (current.length === 0) {
    return (
      <div className="flex items-center justify-center h-64 text-ink-tertiary font-sans text-sm">
        Add at least 3 sectors with 20+ days of history to view the rotation graph.
      </div>
    )
  }

  return (
    <div ref={wrapRef} className="relative w-full overflow-x-auto">
      <svg ref={svgRef} />
    </div>
  )
}
