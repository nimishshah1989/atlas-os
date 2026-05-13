'use client'
import { useEffect, useRef, useState } from 'react'
import * as d3 from 'd3'
import type { CountryRow } from '@/lib/queries/global'

const STATE_FILL: Record<string, string> = {
  Overweight:  '#1D9E75',
  Neutral:     '#F59E0B',
  Underweight: '#FB923C',
  Avoid:       '#EF4444',
}

function rsStateFromQuintile(q3mVt: number | null): string {
  if (q3mVt == null) return 'Neutral'
  if (q3mVt <= 1) return 'Overweight'
  if (q3mVt <= 2) return 'Neutral'
  if (q3mVt <= 3) return 'Underweight'
  return 'Avoid'
}

function bubbleFill(row: CountryRow): string {
  const state = row.rs_state ?? rsStateFromQuintile(row.q_3m_vt)
  return STATE_FILL[state] ?? '#94a3b8'
}

type Filter = 'all' | 'dm' | 'em'

const MARGIN = { top: 30, right: 24, bottom: 56, left: 60 }

export function GlobalCountryBubbleChart({ countries }: { countries: CountryRow[] }) {
  const svgRef  = useRef<SVGSVGElement>(null)
  const wrapRef = useRef<HTMLDivElement>(null)
  const [filter, setFilter] = useState<Filter>('all')

  const filtered = filter === 'all' ? countries :
    filter === 'dm' ? countries.filter(c => c.is_developed_market) :
    countries.filter(c => !c.is_developed_market)

  useEffect(() => {
    const container = wrapRef.current
    const svgEl = svgRef.current
    if (!container || !svgEl) return

    const totalW = container.clientWidth
    const totalH = 440
    const W = totalW - MARGIN.left - MARGIN.right
    const H = totalH - MARGIN.top - MARGIN.bottom

    d3.select(svgEl).selectAll('*').remove()
    d3.select(svgEl).attr('width', totalW).attr('height', totalH)

    const svg = d3.select(svgEl)
      .append('g')
      .attr('transform', `translate(${MARGIN.left},${MARGIN.top})`)

    const points = filtered
      .map(r => ({
        ...r,
        x: r.realized_vol_63 != null ? parseFloat(r.realized_vol_63) * 100 : NaN,
        y: r.ret_3m != null ? parseFloat(r.ret_3m) * 100 : NaN,
        score: r.rs_consensus_bullish ?? 0,
        label: r.country.length > 10 ? r.country.slice(0, 9) + '…' : r.country,
      }))
      .filter(p => !isNaN(p.x) && !isNaN(p.y))

    if (points.length === 0) {
      svg.append('text')
        .attr('x', W / 2).attr('y', H / 2)
        .attr('text-anchor', 'middle')
        .attr('font-family', 'var(--font-sans)').attr('font-size', 12).attr('fill', '#94a3b8')
        .text('No country data with sufficient history')
      return
    }

    const xExt = d3.extent(points, p => p.x) as [number, number]
    const xPad = (xExt[1] - xExt[0]) * 0.1 || 2
    const xScale = d3.scaleLinear().domain([xExt[0] - xPad, xExt[1] + xPad]).range([0, W])

    const yExt = d3.extent(points, p => p.y) as [number, number]
    const yPad = (yExt[1] - yExt[0]) * 0.1 || 2
    const yScale = d3.scaleLinear().domain([yExt[0] - yPad, yExt[1] + yPad]).range([H, 0])

    // Zero-return line
    if (yExt[0] < 0 && yExt[1] > 0) {
      svg.append('line')
        .attr('x1', 0).attr('x2', W)
        .attr('y1', yScale(0)).attr('y2', yScale(0))
        .attr('stroke', '#cbd5e1').attr('stroke-dasharray', '4 3').attr('stroke-width', 1)
    }

    // Axes
    const xAxis = d3.axisBottom(xScale).ticks(6).tickFormat(d => `${d}%`)
    const yAxis = d3.axisLeft(yScale).ticks(7).tickFormat(d => `${d as number > 0 ? '+' : ''}${d}%`)

    svg.append('g')
      .attr('transform', `translate(0,${H})`)
      .call(xAxis)
      .call(g => g.select('.domain').remove())
      .call(g => g.selectAll('line').attr('stroke', '#e2e8f0'))
      .call(g => g.selectAll('text').attr('font-family', 'var(--font-mono)').attr('font-size', 10).attr('fill', '#94a3b8'))

    svg.append('g')
      .call(yAxis)
      .call(g => g.select('.domain').remove())
      .call(g => g.selectAll('line').attr('stroke', '#e2e8f0'))
      .call(g => g.selectAll('text').attr('font-family', 'var(--font-mono)').attr('font-size', 10).attr('fill', '#94a3b8'))

    svg.append('text')
      .attr('x', W / 2).attr('y', H + 44)
      .attr('text-anchor', 'middle')
      .attr('font-family', 'var(--font-sans)').attr('font-size', 11).attr('fill', '#64748b')
      .text('Annualised Volatility (63D) →')

    svg.append('text')
      .attr('transform', 'rotate(-90)')
      .attr('x', -H / 2).attr('y', -46)
      .attr('text-anchor', 'middle')
      .attr('font-family', 'var(--font-sans)').attr('font-size', 11).attr('fill', '#64748b')
      .text('← 3M Return')

    // Tooltip
    const tooltip = d3.select(container)
      .selectAll<HTMLDivElement, unknown>('.country-bubble-tooltip')
      .data([null])
      .join('div')
      .attr('class', 'country-bubble-tooltip')
      .style('position', 'absolute')
      .style('pointer-events', 'none')
      .style('background', 'rgba(15,23,42,0.92)')
      .style('color', '#f1f5f9')
      .style('font-family', 'var(--font-sans)')
      .style('font-size', '11px')
      .style('padding', '6px 10px')
      .style('border-radius', '4px')
      .style('white-space', 'nowrap')
      .style('display', 'none')
      .style('z-index', '100')

    // Bubbles
    svg.selectAll<SVGCircleElement, typeof points[0]>('circle')
      .data(points)
      .join('circle')
      .attr('cx', p => xScale(p.x))
      .attr('cy', p => yScale(p.y))
      .attr('r', 8)
      .attr('fill', p => bubbleFill(p))
      .attr('fill-opacity', 0.82)
      .attr('stroke', '#fff')
      .attr('stroke-width', 1.5)
      .style('cursor', 'default')
      .on('mouseover', (event, p) => {
        const ret3m = p.ret_3m != null ? (parseFloat(p.ret_3m) * 100).toFixed(1) : '—'
        const vol   = p.realized_vol_63 != null ? (parseFloat(p.realized_vol_63) * 100).toFixed(1) : '—'
        const state = p.rs_state ?? rsStateFromQuintile(p.q_3m_vt)
        tooltip
          .style('display', 'block')
          .html(`<strong>${p.country}</strong> (${p.ticker})<br/>3M: ${ret3m}% | Vol: ${vol}% | ${state}<br/>RS Bull Score: ${p.rs_consensus_bullish ?? '—'}/20`)
        const [mx, my] = d3.pointer(event, container)
        tooltip.style('left', `${mx + 12}px`).style('top', `${my - 10}px`)
      })
      .on('mousemove', (event) => {
        const [mx, my] = d3.pointer(event, container)
        tooltip.style('left', `${mx + 12}px`).style('top', `${my - 10}px`)
      })
      .on('mouseleave', () => tooltip.style('display', 'none'))

    // Country labels
    svg.selectAll<SVGTextElement, typeof points[0]>('.country-label')
      .data(points)
      .join('text')
      .attr('class', 'country-label')
      .attr('x', p => xScale(p.x))
      .attr('y', p => yScale(p.y) - 11)
      .attr('text-anchor', 'middle')
      .attr('font-family', 'var(--font-sans)')
      .attr('font-size', 9)
      .attr('fill', '#475569')
      .text(p => p.label)
  }, [filtered])

  return (
    <div>
      {/* Filter buttons */}
      <div className="flex items-center gap-1 mb-3">
        {(['all', 'dm', 'em'] as Filter[]).map(f => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            className={[
              'px-2.5 py-1 rounded text-[10px] font-sans font-medium border transition-colors',
              filter === f
                ? 'bg-teal text-white border-teal'
                : 'text-ink-secondary border-paper-rule hover:border-teal hover:text-teal',
            ].join(' ')}
          >
            {f === 'all' ? 'All Countries' : f === 'dm' ? 'Developed' : 'Emerging'}
          </button>
        ))}
        <span className="ml-auto font-mono text-[10px] text-ink-tertiary">{filtered.length} countries</span>
      </div>

      {/* Legend */}
      <div className="flex items-center gap-3 mb-2">
        {Object.entries(STATE_FILL).map(([state, color]) => (
          <div key={state} className="flex items-center gap-1">
            <div className="w-2.5 h-2.5 rounded-full" style={{ background: color }} />
            <span className="font-sans text-[10px] text-ink-secondary">{state}</span>
          </div>
        ))}
      </div>

      <div ref={wrapRef} style={{ position: 'relative', width: '100%' }}>
        <svg ref={svgRef} style={{ display: 'block', width: '100%' }} />
      </div>
    </div>
  )
}
