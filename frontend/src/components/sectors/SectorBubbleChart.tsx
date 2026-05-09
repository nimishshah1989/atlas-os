'use client'
import { useEffect, useRef } from 'react'
import * as d3 from 'd3'
import type { SectorDecision } from '@/lib/sectors-decision'


export type SectorPoint = {
  sector_name: string
  constituent_count: number
  bottomup_rs_3m_nifty500: string | null
  participation_50: string | null
  sector_state: string
  bottomup_momentum_state: string | null
  decision: SectorDecision
}

const STATE_COLOR: Record<string, string> = {
  Overweight:  '#22c55e',
  Neutral:     '#f59e0b',
  Underweight: '#ef4444',
  Avoid:       '#ef4444',
}

const DECISION_COLOR: Record<string, string> = {
  'ENTER':     '#22c55e',
  'HOLD':      '#14b8a6',
  'ROTATE IN': '#f59e0b',
  'WATCH':     '#94a3b8',
  'PASS':      '#94a3b8',
  'EXIT':      '#ef4444',
}

export function SectorBubbleChart({
  data,
  range,
  onSelect,
}: {
  data: SectorPoint[]
  range: string
  onSelect: (sectorName: string) => void
}) {
  const svgRef    = useRef<SVGSVGElement>(null)
  const wrapRef   = useRef<HTMLDivElement>(null)
  const selectRef = useRef(onSelect)
  selectRef.current = onSelect

  useEffect(() => {
    const container = wrapRef.current
    const svgEl     = svgRef.current
    if (!container || !svgEl || data.length === 0) return

    const margin = { top: 40, right: 40, bottom: 64, left: 68 }
    const totalW = container.clientWidth
    const totalH = 520
    const W = totalW - margin.left - margin.right
    const H = totalH - margin.top  - margin.bottom

    d3.select(svgEl).selectAll('*').remove()
    d3.select(svgEl).attr('width', totalW).attr('height', totalH)

    const svg = d3.select(svgEl)
      .append('g')
      .attr('transform', `translate(${margin.left},${margin.top})`)

    const points = data.map(d => ({
      ...d,
      x: parseFloat(d.bottomup_rs_3m_nifty500 ?? 'NaN'),
      y: parseFloat(d.participation_50 ?? 'NaN'),
      r: d.constituent_count,
    }))

    const validPoints = points.filter(p => !isNaN(p.x) && !isNaN(p.y))

    const xExt = d3.extent(validPoints, p => p.x) as [number, number]
    const xPad = (xExt[1] - xExt[0]) * 0.12
    const xScale = d3.scaleLinear()
      .domain([Math.min(xExt[0] - xPad, -0.08), xExt[1] + xPad])
      .range([0, W])

    const yExt = d3.extent(validPoints, p => p.y) as [number, number]
    const yPad = (yExt[1] - yExt[0]) * 0.12
    const yScale = d3.scaleLinear()
      .domain([Math.max(0, yExt[0] - yPad), Math.min(1.0, yExt[1] + yPad)])
      .range([H, 0])

    const rScale = d3.scaleSqrt()
      .domain([0, d3.max(validPoints, p => p.r) ?? 80])
      .range([6, 34])

    const midX = xScale(0)
    const midY = yScale(0.5)

    const quads = [
      { x: midX, y: 0,    w: W - midX,  h: midY,     label: 'LEADERS',    color: '#22c55e' },
      { x: 0,    y: 0,    w: midX,      h: midY,     label: 'RECOVERING', color: '#f59e0b' },
      { x: midX, y: midY, w: W - midX,  h: H - midY, label: 'NARROWING',  color: '#f59e0b' },
      { x: 0,    y: midY, w: midX,      h: H - midY, label: 'LAGGARDS',   color: '#ef4444' },
    ]

    quads.forEach(q => {
      svg.append('rect')
        .attr('x', q.x).attr('y', q.y)
        .attr('width', q.w).attr('height', q.h)
        .attr('fill', q.color).attr('opacity', 0.04)

      svg.append('text')
        .attr('x', q.x + q.w / 2)
        .attr('y', q.y + (q.y === 0 ? 14 : q.h - 6))
        .attr('text-anchor', 'middle')
        .attr('font-family', 'var(--font-sans)')
        .attr('font-size', 8).attr('font-weight', 700)
        .attr('letter-spacing', 1.5)
        .attr('fill', q.color).attr('opacity', 0.5)
        .text(q.label)
    })

    svg.append('line')
      .attr('x1', midX).attr('x2', midX)
      .attr('y1', 0).attr('y2', H)
      .attr('stroke', '#94a3b8').attr('stroke-width', 1)
      .attr('stroke-dasharray', '3 3')

    svg.append('line')
      .attr('x1', 0).attr('x2', W)
      .attr('y1', midY).attr('y2', midY)
      .attr('stroke', '#94a3b8').attr('stroke-width', 1)
      .attr('stroke-dasharray', '3 3')

    svg.append('g')
      .attr('transform', `translate(0,${H})`)
      .call(
        d3.axisBottom(xScale)
          .tickFormat(v => `${(+v * 100).toFixed(0)}%`)
          .ticks(7)
          .tickSize(0)
      )
      .call(ax => {
        ax.select('.domain').remove()
        ax.selectAll('.tick text')
          .attr('font-family', 'var(--font-sans)')
          .attr('font-size', 9)
          .attr('fill', '#94a3b8')
          .attr('dy', 12)
      })

    svg.append('g')
      .call(
        d3.axisLeft(yScale)
          .tickFormat(v => `${(+v * 100).toFixed(0)}%`)
          .ticks(5)
          .tickSize(0)
      )
      .call(ax => {
        ax.select('.domain').remove()
        ax.selectAll('.tick text')
          .attr('font-family', 'var(--font-sans)')
          .attr('font-size', 9)
          .attr('fill', '#94a3b8')
          .attr('dx', -6)
      })

    svg.append('text')
      .attr('x', W / 2).attr('y', H + 50)
      .attr('text-anchor', 'middle')
      .attr('font-family', 'var(--font-sans)')
      .attr('font-size', 10).attr('fill', '#64748b')
      .text('3-Month Relative Strength vs Nifty 500 →')

    svg.append('text')
      .attr('transform', 'rotate(-90)')
      .attr('x', -H / 2).attr('y', -52)
      .attr('text-anchor', 'middle')
      .attr('font-family', 'var(--font-sans)')
      .attr('font-size', 10).attr('fill', '#64748b')
      .text('↑ Breadth — % Stocks Above 50-Day EMA')

    // Append tooltip to document.body with position:fixed so it escapes
    // any overflow:hidden ancestor in the page layout.
    const tip = d3.select(document.body)
      .append('div')
      .style('position', 'fixed')
      .style('pointer-events', 'none')
      .style('opacity', '0')
      .style('background', '#fff')
      .style('border', '1px solid #e2e8f0')
      .style('border-radius', '2px')
      .style('padding', '8px 10px')
      .style('font-family', 'var(--font-sans)')
      .style('font-size', '11px')
      .style('color', '#1e293b')
      .style('z-index', '9999')
      .style('box-shadow', '0 2px 8px rgba(0,0,0,0.08)')
      .style('min-width', '160px')

    const node = svg.selectAll<SVGGElement, typeof validPoints[0]>('.sector-node')
      .data(validPoints)
      .enter()
      .append('g')
      .attr('class', 'sector-node')
      .style('cursor', 'pointer')

    node.append('circle')
      .attr('cx', p => xScale(p.x))
      .attr('cy', p => yScale(p.y))
      .attr('r',  p => rScale(p.r))
      .attr('fill',         p => STATE_COLOR[p.sector_state] ?? '#94a3b8')
      .attr('fill-opacity', 0.12)
      .attr('stroke',       p => STATE_COLOR[p.sector_state] ?? '#94a3b8')
      .attr('stroke-width', 1.5)

    node.append('text')
      .attr('x', p => xScale(p.x))
      .attr('y', p => yScale(p.y) + 3)
      .attr('text-anchor', 'middle')
      .attr('font-family', 'var(--font-sans)')
      .attr('font-size', 7.5)
      .attr('font-weight', 600)
      .attr('fill', p => STATE_COLOR[p.sector_state] ?? '#94a3b8')
      .attr('pointer-events', 'none')
      .text(p => p.sector_name.length > 9 ? p.sector_name.slice(0, 9) : p.sector_name)

    node
      .on('mouseenter', function (event, p) {
        d3.select(this).select('circle')
          .attr('fill-opacity', 0.25)
          .attr('stroke-width', 2.5)

        tip
          .style('opacity', '1')
          .style('left', `${(event.clientX as number) + 14}px`)
          .style('top',  `${(event.clientY as number) - 30}px`)
          .html(`
            <div style="font-weight:700;margin-bottom:4px">${p.sector_name}</div>
            <div style="color:#64748b;margin-bottom:2px">
              Decision: <span style="font-weight:600;color:${DECISION_COLOR[p.decision]}">${p.decision}</span>
            </div>
            <div style="color:#64748b">RS (3M): <span style="color:#1e293b">${(p.x * 100).toFixed(1)}%</span></div>
            <div style="color:#64748b">Breadth: <span style="color:#1e293b">${(p.y * 100).toFixed(0)}%</span></div>
            <div style="color:#64748b">Stocks: <span style="color:#1e293b">${p.constituent_count}</span></div>
            <div style="margin-top:4px;color:#64748b">Momentum: <span style="color:#1e293b">${p.bottomup_momentum_state ?? '—'}</span></div>
          `)
      })
      .on('mousemove', function (event) {
        tip
          .style('left', `${(event.clientX as number) + 14}px`)
          .style('top',  `${(event.clientY as number) - 30}px`)
      })
      .on('mouseleave', function () {
        d3.select(this).select('circle')
          .attr('fill-opacity', 0.12)
          .attr('stroke-width', 1.5)
        tip.style('opacity', '0')
      })
      .on('click', (_, p) => {
        tip.style('opacity', '0')
        selectRef.current(p.sector_name)
      })

    return () => { tip.remove() }
  }, [data]) // onSelect excluded — stable via selectRef, prevents D3 full-redraw on drawer open

  return (
    <div ref={wrapRef} className="relative">
      <svg ref={svgRef} className="w-full" />
      <div className="flex items-center gap-5 mt-2">
        {([['Overweight', '#22c55e'], ['Neutral', '#f59e0b'], ['Underweight', '#ef4444'], ['Avoid', '#ef4444']] as [string, string][]).map(([label, color]) => (
          <span key={label} className="flex items-center gap-1.5 font-sans text-xs text-ink-secondary">
            <span className="inline-block w-2.5 h-2.5 rounded-full" style={{ background: color, opacity: 0.7 }} />
            {label}
          </span>
        ))}
        <span className="font-sans text-xs text-ink-tertiary ml-2">Bubble size = number of stocks in sector</span>
      </div>
    </div>
  )
}
