'use client'
import { useEffect, useRef } from 'react'
import * as d3 from 'd3'
import type { USSectorRow, USSectorRRGPoint } from '@/lib/queries/us-sectors'

function deriveSectorState(avgRsPctile: number): 'Overweight' | 'Neutral' | 'Underweight' | 'Avoid' {
  if (avgRsPctile >= 60) return 'Overweight'
  if (avgRsPctile >= 42) return 'Neutral'
  if (avgRsPctile >= 28) return 'Underweight'
  return 'Avoid'
}

const STATE_FILL: Record<string, string> = {
  Overweight:  '#1D9E75',
  Neutral:     '#F59E0B',
  Underweight: '#FB923C',
  Avoid:       '#EF4444',
}

const SECTOR_SHORT: Record<string, string> = {
  'Information Technology': 'Tech',
  'Health Care': 'Health',
  'Financials': 'Finance',
  'Consumer Discretionary': 'Cons.D',
  'Communication Services': 'Comm',
  'Industrials': 'Indust.',
  'Consumer Staples': 'Staples',
  'Energy': 'Energy',
  'Materials': 'Matls',
  'Real Estate': 'RE',
  'Utilities': 'Utils',
}

const MARGIN = { top: 30, right: 20, bottom: 50, left: 70 }

type TrailPoint = { date: string; x: number; y: number }

type SectorPlot = {
  name: string
  shortName: string
  x: number
  y: number
  rsPctile: number
  momentum: number
  state: string
  ret3m: number | null
  trail: TrailPoint[]
}

function quadrantLabel(x: number, meanX: number, y: number): string {
  if (x >= meanX && y >= 0) return 'Leading ↗'
  if (x >= meanX && y <  0) return 'Weakening ↘'
  if (x <  meanX && y >= 0) return 'Improving ↖'
  return 'Lagging ↙'
}

export function USRRGChart({
  sectors,
  rrgHistory,
}: {
  sectors: USSectorRow[]
  rrgHistory: USSectorRRGPoint[]
}) {
  const svgRef  = useRef<SVGSVGElement>(null)
  const wrapRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const container = wrapRef.current
    const svgEl     = svgRef.current
    if (!container || !svgEl) return

    const totalW = container.clientWidth || 720
    const totalH = 440
    const W = totalW - MARGIN.left - MARGIN.right
    const H = totalH - MARGIN.top  - MARGIN.bottom

    d3.select(svgEl).selectAll('*').remove()
    d3.select(svgEl).attr('width', totalW).attr('height', totalH)

    if (sectors.length === 0) {
      d3.select(svgEl)
        .append('text')
        .attr('x', totalW / 2).attr('y', totalH / 2)
        .attr('text-anchor', 'middle')
        .attr('font-family', 'var(--font-sans)')
        .attr('font-size', 13).attr('fill', '#94a3b8')
        .text('No sector data available')
      return
    }

    // Group history by sector, sort ascending by date
    const historyBySector = new Map<string, USSectorRRGPoint[]>()
    for (const pt of rrgHistory) {
      const arr = historyBySector.get(pt.gics_sector) ?? []
      arr.push(pt)
      historyBySector.set(pt.gics_sector, arr)
    }
    for (const [k, v] of historyBySector) {
      historyBySector.set(k, [...v].sort((a, b) => a.date.localeCompare(b.date)))
    }

    // Build plot data from current sector snapshot
    const plots: SectorPlot[] = []
    for (const row of sectors) {
      const rsPctileRaw = row.avg_rs_pctile_3m_vt
      const momentumRaw = row.rs_momentum
      if (rsPctileRaw == null || momentumRaw == null) continue
      const rsPctile = parseFloat(rsPctileRaw)
      const momentum = parseFloat(momentumRaw)
      if (isNaN(rsPctile) || isNaN(momentum)) continue

      const sectorHistory = historyBySector.get(row.gics_sector) ?? []
      // Exclude most-recent entry (= current day) from trail
      const trailRows = sectorHistory.slice(0, -1)
      const trail: TrailPoint[] = trailRows
        .map(pt => {
          const tx = pt.avg_rs_pctile_3m_vt != null ? parseFloat(pt.avg_rs_pctile_3m_vt) : null
          const ty = pt.rs_momentum != null ? parseFloat(pt.rs_momentum) : null
          if (tx == null || isNaN(tx) || ty == null || isNaN(ty)) return null
          return { date: pt.date, x: tx, y: ty }
        })
        .filter((p): p is TrailPoint => p !== null)

      plots.push({
        name: row.gics_sector,
        shortName: SECTOR_SHORT[row.gics_sector] ?? row.gics_sector.slice(0, 6),
        x: rsPctile,
        y: momentum,
        rsPctile,
        momentum,
        state: deriveSectorState(rsPctile),
        ret3m: row.avg_ret_3m != null ? parseFloat(row.avg_ret_3m) : null,
        trail,
      })
    }

    if (plots.length === 0) {
      d3.select(svgEl)
        .append('text')
        .attr('x', totalW / 2).attr('y', totalH / 2)
        .attr('text-anchor', 'middle')
        .attr('font-family', 'var(--font-sans)')
        .attr('font-size', 13).attr('fill', '#94a3b8')
        .text('Insufficient data to render RRG')
      return
    }

    const meanX = d3.mean(plots, p => p.x) ?? 50

    // Scale domain: all x/y values including trail points
    const allXVals = plots.flatMap(p => [p.x, ...p.trail.map(t => t.x)])
    const allYVals = plots.flatMap(p => [p.y, ...p.trail.map(t => t.y)])
    const xExt = (d3.extent(allXVals) as [number, number])
    const yExt = (d3.extent(allYVals) as [number, number])
    const xPad = Math.max((xExt[1] - xExt[0]) * 0.15, 5)
    const yPad = Math.max((yExt[1] - yExt[0]) * 0.15, 1)

    const xScale = d3.scaleLinear()
      .domain([xExt[0] - xPad, xExt[1] + xPad])
      .range([0, W])
    const yScale = d3.scaleLinear()
      .domain([yExt[0] - yPad, yExt[1] + yPad])
      .range([H, 0])

    const svg = d3.select(svgEl)
      .append('g')
      .attr('transform', `translate(${MARGIN.left},${MARGIN.top})`)

    const clipId = 'usrrg-clip'
    d3.select(svgEl).append('defs').append('clipPath').attr('id', clipId)
      .append('rect').attr('width', W).attr('height', H)

    // Quadrant backgrounds relative to mean RS and y=0
    const crossX = xScale(meanX)
    const crossY = yScale(0)

    const quads = [
      { x: crossX, y: 0,      w: W - crossX,  h: crossY,     label: 'LEADING ↗',   bg: '#e2f4ee', tc: '#1D9E75' },
      { x: 0,      y: 0,      w: crossX,      h: crossY,     label: 'IMPROVING ↖', bg: '#e8f0f8', tc: '#3B82F6' },
      { x: crossX, y: crossY, w: W - crossX,  h: H - crossY, label: 'WEAKENING ↘', bg: '#fef3c7', tc: '#D97706' },
      { x: 0,      y: crossY, w: crossX,      h: H - crossY, label: 'LAGGING ↙',   bg: '#fee2e2', tc: '#EF4444' },
    ]
    quads.forEach(q => {
      svg.append('rect')
        .attr('x', q.x).attr('y', q.y)
        .attr('width', q.w).attr('height', q.h)
        .attr('fill', q.bg).attr('opacity', 0.30)
      svg.append('text')
        .attr('x', q.x + q.w / 2)
        .attr('y', q.y + (q.y === 0 ? 14 : q.h - 8))
        .attr('text-anchor', 'middle')
        .attr('font-family', 'var(--font-sans)')
        .attr('font-size', 8).attr('font-weight', 700).attr('letter-spacing', 0.8)
        .attr('fill', q.tc).attr('opacity', 0.50)
        .text(q.label)
    })

    // Center crosshairs
    svg.append('line')
      .attr('x1', crossX).attr('x2', crossX).attr('y1', 0).attr('y2', H)
      .attr('stroke', '#94a3b8').attr('stroke-width', 1).attr('stroke-dasharray', '4 3')
    svg.append('line')
      .attr('x1', 0).attr('x2', W).attr('y1', crossY).attr('y2', crossY)
      .attr('stroke', '#94a3b8').attr('stroke-width', 1).attr('stroke-dasharray', '4 3')

    // Axes
    svg.append('g')
      .attr('transform', `translate(0,${H})`)
      .call(d3.axisBottom(xScale).ticks(6).tickFormat(v => `${Math.round(+v * 100)}`).tickSize(0))
      .call(ax => {
        ax.select('.domain').remove()
        ax.selectAll('.tick text')
          .attr('font-family', 'var(--font-sans)').attr('font-size', 9)
          .attr('fill', '#94a3b8').attr('dy', 12)
      })

    svg.append('g')
      .call(d3.axisLeft(yScale).ticks(5).tickFormat(v => `${(+v * 100).toFixed(1)}pp`).tickSize(0))
      .call(ax => {
        ax.select('.domain').remove()
        ax.selectAll('.tick text')
          .attr('font-family', 'var(--font-sans)').attr('font-size', 9)
          .attr('fill', '#94a3b8').attr('dx', -6)
      })

    svg.append('text')
      .attr('x', W / 2).attr('y', H + 42)
      .attr('text-anchor', 'middle')
      .attr('font-family', 'var(--font-sans)').attr('font-size', 10).attr('fill', '#64748b')
      .text('RS Strength (vs VT) →')

    svg.append('text')
      .attr('transform', 'rotate(-90)')
      .attr('x', -H / 2).attr('y', -56)
      .attr('text-anchor', 'middle')
      .attr('font-family', 'var(--font-sans)').attr('font-size', 10).attr('fill', '#64748b')
      .text('RS Momentum')

    // Trail rendering (clipped to chart area)
    const trailGroup = svg.append('g').attr('clip-path', `url(#${clipId})`)
    const lineGen = d3.line<TrailPoint>()
      .x(pt => xScale(pt.x))
      .y(pt => yScale(pt.y))
      .curve(d3.curveCatmullRom.alpha(0.5))

    for (const plot of plots) {
      const color = STATE_FILL[plot.state] ?? '#94a3b8'
      const n = plot.trail.length
      if (n === 0) continue

      // Trail dots: oldest=lowest opacity, newest=highest
      plot.trail.forEach((pt, i) => {
        const opacity = 0.05 + (0.35 * i) / Math.max(n - 1, 1)
        trailGroup.append('circle')
          .attr('cx', xScale(pt.x))
          .attr('cy', yScale(pt.y))
          .attr('r', 2)
          .attr('fill', color)
          .attr('opacity', opacity)
          .attr('pointer-events', 'none')
      })

      // Connect trail + current with a path
      if (n >= 1) {
        const allPts: TrailPoint[] = [...plot.trail, { date: 'current', x: plot.x, y: plot.y }]
        trailGroup.append('path')
          .datum(allPts)
          .attr('d', lineGen)
          .attr('fill', 'none')
          .attr('stroke', color)
          .attr('stroke-width', 1)
          .attr('stroke-opacity', 0.28)
          .attr('pointer-events', 'none')
      }
    }

    // Tooltip portal to body
    const tip = d3.select(document.body)
      .append('div')
      .style('position', 'fixed')
      .style('pointer-events', 'none')
      .style('opacity', '0')
      .style('background', '#fff')
      .style('border', '1px solid #e2e8f0')
      .style('border-radius', '4px')
      .style('padding', '8px 10px')
      .style('font-family', 'var(--font-sans)')
      .style('font-size', '11px')
      .style('color', '#1e293b')
      .style('z-index', '9999')
      .style('box-shadow', '0 2px 8px rgba(0,0,0,0.10)')
      .style('min-width', '172px')

    // Current position bubbles
    const nodes = svg.selectAll<SVGGElement, SectorPlot>('.rrg-node')
      .data(plots)
      .enter()
      .append('g')
      .attr('class', 'rrg-node')
      .attr('transform', p => `translate(${xScale(p.x)},${yScale(p.y)})`)
      .style('cursor', 'default')

    nodes.append('circle')
      .attr('r', 14)
      .attr('fill', p => STATE_FILL[p.state] ?? '#94a3b8')
      .attr('opacity', 0.88)

    nodes.append('text')
      .attr('text-anchor', 'middle')
      .attr('dominant-baseline', 'middle')
      .attr('font-family', 'var(--font-sans)')
      .attr('font-size', 7).attr('font-weight', 600)
      .attr('fill', '#fff')
      .attr('pointer-events', 'none')
      .text(p => p.shortName)

    nodes
      .on('mouseenter', function (event: MouseEvent, p: SectorPlot) {
        nodes.select('circle')
          .attr('opacity', (q: SectorPlot) => q.name === p.name ? 1 : 0.20)
        d3.select(this).select('circle').attr('opacity', 1)

        const ret3mStr = p.ret3m != null
          ? `${p.ret3m >= 0 ? '+' : ''}${(p.ret3m * 100).toFixed(1)}%`
          : '—'
        const momStr = `${p.momentum >= 0 ? '+' : ''}${p.momentum.toFixed(2)}`
        tip
          .style('opacity', '1')
          .style('left', `${(event.clientX as number) + 14}px`)
          .style('top',  `${(event.clientY as number) - 30}px`)
          .html(`
            <div style="font-weight:700;margin-bottom:4px">${p.name}</div>
            <div style="color:#64748b;margin-bottom:2px">
              ${quadrantLabel(p.x, meanX, p.y)} &nbsp;
              <span style="font-weight:600;color:${STATE_FILL[p.state]}">${p.state}</span>
            </div>
            <div style="color:#64748b">RS Pctile: <span style="color:#1e293b">${Math.round(p.rsPctile * 100)}</span></div>
            <div style="color:#64748b">RS Momentum: <span style="color:#1e293b">${momStr}</span></div>
            <div style="color:#64748b">Ret 3M: <span style="color:#1e293b">${ret3mStr}</span></div>
          `)
      })
      .on('mousemove', function (event: MouseEvent) {
        tip.style('left', `${(event.clientX as number) + 14}px`).style('top', `${(event.clientY as number) - 30}px`)
      })
      .on('mouseleave', function () {
        nodes.select('circle').attr('opacity', 0.88)
        tip.style('opacity', '0')
      })

    return () => { tip.remove() }
  }, [sectors, rrgHistory])

  if (sectors.length === 0) {
    return (
      <div className="flex items-center justify-center h-48 text-ink-tertiary font-sans text-sm">
        No data
      </div>
    )
  }

  return (
    <div ref={wrapRef} className="relative w-full h-[440px]">
      <svg ref={svgRef} className="w-full" />
    </div>
  )
}
