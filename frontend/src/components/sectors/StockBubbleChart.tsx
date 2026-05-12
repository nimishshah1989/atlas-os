// allow-large: single cohesive D3 component
'use client'
import { useEffect, useRef } from 'react'
import * as d3 from 'd3'
import type { StockRow } from '@/lib/queries/sector-deep-dive'

function colorFor(rs_state: string | null): string {
  if (rs_state === 'Leader')        return '#2F6B43'
  if (rs_state === 'Strong')        return '#1D9E75'
  if (rs_state === 'Emerging')      return '#25394A'
  if (rs_state === 'Consolidating') return '#B8860B'
  if (rs_state === 'Weak')          return '#B0492C'
  if (rs_state === 'Laggard')       return '#B0492C'
  return '#8C8278'
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

    // X = realized_vol_63 (%), Y = ret_3m (%)
    const validPoints = stocks
      .map(s => ({
        ...s,
        x: s.realized_vol_63 != null ? parseFloat(s.realized_vol_63) * 100 : NaN,
        y: s.ret_3m           != null ? parseFloat(s.ret_3m)          * 100 : NaN,
        r: parseFloat(s.position_size_pct ?? '0.005'),
      }))
      .filter(p => !isNaN(p.x) && !isNaN(p.y))

    if (validPoints.length === 0) {
      svg.append('text')
        .attr('x', W / 2).attr('y', H / 2)
        .attr('text-anchor', 'middle')
        .attr('font-family', 'var(--font-sans)')
        .attr('font-size', 12)
        .attr('fill', '#94a3b8')
        .text('No stocks with sufficient history')
      return
    }

    const xExt = d3.extent(validPoints, p => p.x) as [number, number]
    const xPad = (xExt[1] - xExt[0]) * 0.12 || 1
    const xScale = d3.scaleLinear()
      .domain([Math.max(0, xExt[0] - xPad), xExt[1] + xPad])
      .range([0, W])

    const yExt = d3.extent(validPoints, p => p.y) as [number, number]
    const yPad = (yExt[1] - yExt[0]) * 0.12 || 2
    const yScale = d3.scaleLinear()
      .domain([yExt[0] - yPad, yExt[1] + yPad])
      .range([H, 0])

    const rScale = d3.scaleSqrt()
      .domain([0, d3.max(validPoints, p => p.r) ?? 0.05])
      .range([4, 24])

    // Crosshair: X = median volatility, Y = 0% return
    const medianVol = d3.median(validPoints, p => p.x) ?? 0
    const midX = xScale(medianVol)
    const midY = yScale(0)

    // Quadrant tints: top-left=QUALITY UPTREND, top-right=HIGH BETA,
    //                 bottom-left=QUIET DRIFT, bottom-right=DANGER ZONE
    const quads = [
      {
        x: 0,    y: 0,    w: midX,     h: midY,
        label: 'QUALITY UPTREND', sub: 'low risk · positive return',
        bg: '#e2f0e8', textColor: '#2F6B43',
      },
      {
        x: midX, y: 0,    w: W - midX, h: midY,
        label: 'HIGH BETA', sub: 'high risk · positive return',
        bg: '#f5f0e8', textColor: '#B8860B',
      },
      {
        x: 0,    y: midY, w: midX,     h: H - midY,
        label: 'QUIET DRIFT', sub: 'low risk · negative return',
        bg: '#e8f0f5', textColor: '#25394A',
      },
      {
        x: midX, y: midY, w: W - midX, h: H - midY,
        label: 'DANGER ZONE', sub: 'high risk · negative return',
        bg: '#f5e8e8', textColor: '#B0492C',
      },
    ]

    quads.forEach(q => {
      svg.append('rect')
        .attr('x', q.x).attr('y', q.y)
        .attr('width', q.w).attr('height', q.h)
        .attr('fill', q.bg).attr('opacity', 0.35)

      // Main label (top of quadrant if positive-return half, bottom if negative)
      const isTop = q.y === 0
      svg.append('text')
        .attr('x', q.x + q.w / 2)
        .attr('y', isTop ? q.y + 14 : q.y + q.h - 14)
        .attr('text-anchor', 'middle')
        .attr('font-family', 'var(--font-sans)')
        .attr('font-size', 8).attr('font-weight', 700)
        .attr('letter-spacing', 1.5)
        .attr('fill', q.textColor).attr('opacity', 0.65)
        .text(q.label)

      // Sub-label
      svg.append('text')
        .attr('x', q.x + q.w / 2)
        .attr('y', isTop ? q.y + 24 : q.y + q.h - 4)
        .attr('text-anchor', 'middle')
        .attr('font-family', 'var(--font-sans)')
        .attr('font-size', 7)
        .attr('fill', q.textColor).attr('opacity', 0.40)
        .text(q.sub)
    })

    // Crosshair lines
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
      .call(
        d3.axisBottom(xScale)
          .tickFormat(v => `${(+v).toFixed(0)}%`)
          .ticks(7)
          .tickSize(0)
      )
      .call(ax => {
        ax.select('.domain').remove()
        ax.selectAll('.tick text')
          .attr('font-family', 'var(--font-sans)').attr('font-size', 9)
          .attr('fill', '#94a3b8').attr('dy', 12)
      })

    // Y axis — +/- sign format
    svg.append('g')
      .call(
        d3.axisLeft(yScale)
          .tickFormat(v => `${+v >= 0 ? '+' : ''}${(+v).toFixed(0)}%`)
          .ticks(5)
          .tickSize(0)
      )
      .call(ax => {
        ax.select('.domain').remove()
        ax.selectAll('.tick text')
          .attr('font-family', 'var(--font-sans)').attr('font-size', 9)
          .attr('fill', '#94a3b8').attr('dx', -6)
      })

    // Axis labels
    svg.append('text')
      .attr('x', W / 2).attr('y', H + 50).attr('text-anchor', 'middle')
      .attr('font-family', 'var(--font-sans)').attr('font-size', 10).attr('fill', '#64748b')
      .text('Volatility 63D (%) →')
    svg.append('text')
      .attr('transform', 'rotate(-90)')
      .attr('x', -H / 2).attr('y', -42).attr('text-anchor', 'middle')
      .attr('font-family', 'var(--font-sans)').attr('font-size', 10).attr('fill', '#64748b')
      .text('↑ 3M Return (%)')

    // Tooltip
    const tip = d3.select(document.body)
      .append('div')
      .style('position', 'fixed').style('pointer-events', 'none')
      .style('opacity', '0').style('background', '#fff')
      .style('border', '1px solid #e2e8f0').style('border-radius', '2px')
      .style('padding', '8px 10px').style('font-family', 'var(--font-sans)')
      .style('font-size', '11px').style('color', '#1e293b')
      .style('z-index', '9999').style('box-shadow', '0 2px 8px rgba(0,0,0,0.08)')
      .style('min-width', '160px')

    const node = svg.selectAll<SVGGElement, typeof validPoints[0]>('.stock-node')
      .data(validPoints).enter().append('g')
      .attr('class', 'stock-node').style('cursor', 'pointer')

    node.append('circle')
      .attr('cx', p => xScale(p.x)).attr('cy', p => yScale(p.y))
      .attr('r', p => rScale(p.r))
      .attr('fill', p => colorFor(p.rs_state)).attr('fill-opacity', 0.18)
      .attr('stroke', p => colorFor(p.rs_state)).attr('stroke-width', 1.5)

    node.append('text')
      .attr('x', p => xScale(p.x))
      .attr('y', p => yScale(p.y) + 3)
      .attr('text-anchor', 'middle')
      .attr('font-family', 'var(--font-sans)')
      .attr('font-size', 7).attr('font-weight', 600)
      .attr('fill', p => colorFor(p.rs_state))
      .attr('pointer-events', 'none')
      .text(p => p.symbol.length > 8 ? p.symbol.slice(0, 8) : p.symbol)

    node
      .on('mouseenter', function (event, p) {
        d3.select(this).select('circle').attr('fill-opacity', 0.32).attr('stroke-width', 2.5)
        const retColor = p.y >= 0 ? '#2F6B43' : '#B0492C'
        const retSign  = p.y >= 0 ? '+' : ''
        tip.style('opacity', '1')
          .style('left', `${(event.clientX as number) + 14}px`)
          .style('top',  `${(event.clientY as number) - 30}px`)
          .html(`
            <div style="font-weight:700;margin-bottom:2px">${p.symbol}</div>
            <div style="color:#64748b;font-size:10px;margin-bottom:6px">${p.company_name}</div>
            <div style="color:#64748b">3M Return: <span style="color:${retColor}">${retSign}${p.y.toFixed(1)}%</span></div>
            <div style="color:#64748b">Volatility 63D: <span style="color:#1e293b">${p.x.toFixed(1)}%</span></div>
            <div style="color:#64748b">Position: <span style="color:#1e293b">${(p.r * 100).toFixed(2)}%</span></div>
            <div style="margin-top:4px;color:#64748b">${p.rs_state ?? '—'} · ${p.momentum_state ?? '—'}</div>
          `)
      })
      .on('mousemove', function (event) {
        tip
          .style('left', `${(event.clientX as number) + 14}px`)
          .style('top',  `${(event.clientY as number) - 30}px`)
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
      <div className="flex flex-wrap items-center gap-3 mt-2 pt-2 border-t border-paper-rule/40">
        {([
          ['Leader',         '#2F6B43'],
          ['Strong',         '#1D9E75'],
          ['Emerging',       '#25394A'],
          ['Consolidating',  '#B8860B'],
          ['Average',        '#8C8278'],
          ['Weak / Laggard', '#B0492C'],
        ] as [string, string][]).map(([label, color]) => (
          <div key={label} className="flex items-center gap-1.5">
            <div className="w-2.5 h-2.5 rounded-full shrink-0" style={{ background: color }} />
            <span className="font-sans text-[10px] text-ink-tertiary">{label}</span>
          </div>
        ))}
        <div className="ml-auto font-sans text-[10px] text-ink-tertiary">
          Bubble size = position weight
        </div>
      </div>
    </div>
  )
}
