// frontend/src/components/sectors/StockBubbleChart.tsx
'use client'
import { useEffect, useRef } from 'react'
import * as d3 from 'd3'
import type { StockRow } from '@/lib/queries/sector-deep-dive'

const STATE_COLOR: Record<string, string> = {
  Overweight_RS:  '#22c55e',
  Underweight_RS: '#ef4444',
}

function colorFor(row: StockRow): string {
  const rs = row.rs_state ?? ''
  const mom = row.momentum_state ?? ''
  if (rs === 'Underweight_RS') return '#ef4444'
  if (rs === 'Overweight_RS' && mom === 'Improving') return '#22c55e'
  if (rs === 'Overweight_RS' && mom === 'Deteriorating') return '#f59e0b'
  if (rs === 'Overweight_RS') return '#1D9E75'
  return '#94a3b8'
}

export function StockBubbleChart({
  stocks,
  onSelect,
}: {
  stocks: StockRow[]
  onSelect?: (symbol: string) => void
}) {
  const svgRef  = useRef<SVGSVGElement>(null)
  const wrapRef = useRef<HTMLDivElement>(null)
  const onSelectRef = useRef(onSelect)
  onSelectRef.current = onSelect

  useEffect(() => {
    const container = wrapRef.current
    const svgEl = svgRef.current
    if (!container || !svgEl || stocks.length === 0) return

    const margin = { top: 30, right: 30, bottom: 64, left: 56 }
    const totalW = container.clientWidth
    const totalH = 480
    const W = totalW - margin.left - margin.right
    const H = totalH - margin.top - margin.bottom

    d3.select(svgEl).selectAll('*').remove()
    d3.select(svgEl).attr('width', totalW).attr('height', totalH)

    const svg = d3.select(svgEl)
      .append('g')
      .attr('transform', `translate(${margin.left},${margin.top})`)

    const points = stocks
      .map(s => ({
        ...s,
        x: s.ret_3m        != null ? parseFloat(s.ret_3m)        : NaN,
        y: s.rs_pctile_3m  != null ? parseFloat(s.rs_pctile_3m)  : NaN,
        r: s.position_size_pct != null ? parseFloat(s.position_size_pct) : 0.005,
      }))
      .filter(p => !isNaN(p.x) && !isNaN(p.y))

    if (points.length === 0) {
      svg.append('text')
        .attr('x', W / 2).attr('y', H / 2)
        .attr('text-anchor', 'middle')
        .attr('font-family', 'var(--font-sans)')
        .attr('font-size', 12)
        .attr('fill', '#94a3b8')
        .text('No stocks with sufficient history')
      return
    }

    const xExt = d3.extent(points, p => p.x) as [number, number]
    const xPad = (xExt[1] - xExt[0]) * 0.12 || 0.05
    const xDomLo = xExt[0] - xPad
    const xDomHi = xExt[1] + xPad
    const xScale = d3.scaleLinear()
      .domain([xDomLo, xDomHi])
      .range([0, W])

    const yScale = d3.scaleLinear()
      .domain([0, 1])
      .range([H, 0])

    const rScale = d3.scaleSqrt()
      .domain([0, d3.max(points, p => p.r) ?? 0.05])
      .range([4, 22])

    const midX = xScale(0)
    const midY = yScale(0.5)

    // Quadrant tints
    // X = 3M return (right = positive return), Y = RS percentile (up = top-ranked)
    const quads = [
      { x: midX, y: 0,    w: W - midX, h: midY,     label: 'LEADERS',    color: '#22c55e' },
      { x: 0,    y: 0,    w: midX,     h: midY,     label: 'RESILIENT',  color: '#1D9E75' },
      { x: midX, y: midY, w: W - midX, h: H - midY, label: 'RISING',     color: '#f59e0b' },
      { x: 0,    y: midY, w: midX,     h: H - midY, label: 'LAGGARDS',   color: '#ef4444' },
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

    // Mid lines
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

    // X axis
    svg.append('g')
      .attr('transform', `translate(0,${H})`)
      .call(d3.axisBottom(xScale).tickFormat(v => `${(+v * 100).toFixed(0)}%`).ticks(7).tickSize(0))
      .call(ax => {
        ax.select('.domain').remove()
        ax.selectAll('.tick text')
          .attr('font-family', 'var(--font-sans)').attr('font-size', 9)
          .attr('fill', '#94a3b8').attr('dy', 12)
      })
    // Y axis
    svg.append('g')
      .call(d3.axisLeft(yScale).tickFormat(v => `${(+v * 100).toFixed(0)}%`).ticks(5).tickSize(0))
      .call(ax => {
        ax.select('.domain').remove()
        ax.selectAll('.tick text')
          .attr('font-family', 'var(--font-sans)').attr('font-size', 9)
          .attr('fill', '#94a3b8').attr('dx', -6)
      })

    svg.append('text')
      .attr('x', W / 2).attr('y', H + 50).attr('text-anchor', 'middle')
      .attr('font-family', 'var(--font-sans)').attr('font-size', 10).attr('fill', '#64748b')
      .text('3-Month Absolute Return →')
    svg.append('text')
      .attr('transform', 'rotate(-90)')
      .attr('x', -H / 2).attr('y', -42).attr('text-anchor', 'middle')
      .attr('font-family', 'var(--font-sans)').attr('font-size', 10).attr('fill', '#64748b')
      .text('↑ RS Percentile vs Peers')

    // Tooltip in body for portal-like behavior
    const tip = d3.select(document.body)
      .append('div')
      .style('position', 'fixed').style('pointer-events', 'none')
      .style('opacity', '0').style('background', '#fff')
      .style('border', '1px solid #e2e8f0').style('border-radius', '2px')
      .style('padding', '8px 10px').style('font-family', 'var(--font-sans)')
      .style('font-size', '11px').style('color', '#1e293b')
      .style('z-index', '9999').style('box-shadow', '0 2px 8px rgba(0,0,0,0.08)')
      .style('min-width', '160px')

    const node = svg.selectAll<SVGGElement, typeof points[0]>('.stock-node')
      .data(points).enter().append('g')
      .attr('class', 'stock-node').style('cursor', 'pointer')

    node.append('circle')
      .attr('cx', p => xScale(p.x)).attr('cy', p => yScale(p.y))
      .attr('r', p => rScale(p.r))
      .attr('fill', p => colorFor(p)).attr('fill-opacity', 0.18)
      .attr('stroke', p => colorFor(p)).attr('stroke-width', 1.5)

    node.append('text')
      .attr('x', p => xScale(p.x))
      .attr('y', p => yScale(p.y) + 3)
      .attr('text-anchor', 'middle')
      .attr('font-family', 'var(--font-sans)')
      .attr('font-size', 7).attr('font-weight', 600)
      .attr('fill', p => colorFor(p))
      .attr('pointer-events', 'none')
      .text(p => p.symbol.length > 8 ? p.symbol.slice(0, 8) : p.symbol)

    node
      .on('mouseenter', function (event, p) {
        d3.select(this).select('circle').attr('fill-opacity', 0.32).attr('stroke-width', 2.5)
        tip.style('opacity', '1')
          .style('left', `${(event.clientX as number) + 14}px`)
          .style('top',  `${(event.clientY as number) - 30}px`)
          .html(`
            <div style="font-weight:700;margin-bottom:4px">${p.symbol}</div>
            <div style="color:#64748b;font-size:10px;margin-bottom:4px">${p.company_name}</div>
            <div style="color:#64748b">3M Return: <span style="color:${p.x >= 0 ? '#22c55e' : '#ef4444'}">${p.x >= 0 ? '+' : ''}${(p.x * 100).toFixed(1)}%</span></div>
            <div style="color:#64748b">RS pctile: <span style="color:#1e293b">${(p.y * 100).toFixed(0)}th</span></div>
            <div style="color:#64748b">Position: <span style="color:#1e293b">${(p.r * 100).toFixed(2)}%</span></div>
            <div style="margin-top:4px;color:#64748b">${p.rs_state ?? '—'} · ${p.momentum_state ?? '—'}</div>
          `)
      })
      .on('mousemove', function (event) {
        tip.style('left', `${(event.clientX as number) + 14}px`).style('top', `${(event.clientY as number) - 30}px`)
      })
      .on('mouseleave', function () {
        d3.select(this).select('circle').attr('fill-opacity', 0.18).attr('stroke-width', 1.5)
        tip.style('opacity', '0')
      })
      .on('click', (_, p) => {
        tip.style('opacity', '0')
        if (onSelectRef.current) onSelectRef.current(p.symbol)
      })

    return () => { tip.remove() }
  }, [stocks])

  return (
    <div ref={wrapRef} className="relative">
      <svg ref={svgRef} className="w-full" />
      <div className="flex items-center gap-4 mt-2 font-sans text-[11px] text-ink-tertiary flex-wrap">
        <span className="flex items-center gap-1.5">
          <span className="inline-block w-2 h-2 rounded-full" style={{ background: '#22c55e' }} />
          Overweight + Improving
        </span>
        <span className="flex items-center gap-1.5">
          <span className="inline-block w-2 h-2 rounded-full" style={{ background: '#1D9E75' }} />
          Overweight + Stable
        </span>
        <span className="flex items-center gap-1.5">
          <span className="inline-block w-2 h-2 rounded-full" style={{ background: '#f59e0b' }} />
          Overweight + Deteriorating
        </span>
        <span className="flex items-center gap-1.5">
          <span className="inline-block w-2 h-2 rounded-full" style={{ background: '#ef4444' }} />
          Underweight
        </span>
        <span className="ml-auto text-ink-tertiary/70">X = 3M return · Y = RS percentile vs peers · Size = position size</span>
      </div>
    </div>
  )
}
