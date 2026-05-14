'use client'
import { useEffect, useRef, useState } from 'react'
import * as d3 from 'd3'
import { rsStateColor } from '@/lib/chart-colors'
import type { USStockRow } from '@/lib/queries/us-stocks'

function volumeToRadius(vol: number | null): number {
  if (!vol || vol <= 0) return 5
  const log = Math.log10(Math.max(1000, vol))
  return Math.min(36, 5 + (log - 3) * 7)
}

type Period = '1M' | '3M' | '6M' | '1Y'
const PERIOD_KEY: Record<Period, keyof USStockRow> = {
  '1M': 'ret_1m',
  '3M': 'ret_3m',
  '6M': 'ret_6m',
  '1Y': 'ret_12m',
}

const FILTERS: { key: 'sp500' | 'all'; label: string }[] = [
  { key: 'sp500', label: 'S&P 500' },
  { key: 'all',   label: 'All' },
]

const LEGEND = [
  { color: '#2F6B43', label: 'Leader' },
  { color: '#1D9E75', label: 'Strong' },
  { color: '#25394A', label: 'Emerging' },
  { color: '#B8860B', label: 'Consolidating' },
  { color: '#8C8278', label: 'Average' },
  { color: '#B0492C', label: 'Weak / Laggard' },
]

const VOL_CAP = 120
const RET_CAP = 1.5

export function USStockBubbleChart({ stocks }: { stocks: USStockRow[] }) {
  const svgRef  = useRef<SVGSVGElement>(null)
  const wrapRef = useRef<HTMLDivElement>(null)
  const [period, setPeriod]   = useState<Period>('3M')
  const [filter, setFilter]   = useState<'sp500' | 'all'>('sp500')

  const live = stocks.filter(s => s.history_gate_pass && s.liquidity_gate_pass)
  const displayed = filter === 'sp500' ? live.filter(s => s.in_sp500) : live

  useEffect(() => {
    const container = wrapRef.current
    const svgEl     = svgRef.current
    if (!container || !svgEl) return

    const margin  = { top: 30, right: 40, bottom: 60, left: 56 }
    const totalW  = container.clientWidth || 720
    const totalH  = 460
    const W = totalW - margin.left - margin.right
    const H = totalH - margin.top  - margin.bottom

    d3.select(svgEl).selectAll('*').remove()
    d3.select(svgEl).attr('width', totalW).attr('height', totalH)

    const retKey = PERIOD_KEY[period]
    const points = displayed
      .map(s => ({
        ticker:    s.ticker,
        name:      s.company_name ?? s.ticker,
        x:         s.realized_vol_63 != null ? parseFloat(s.realized_vol_63) * 100 : NaN,
        y:         s[retKey] != null ? parseFloat(s[retKey] as string) * 100 : NaN,
        avgVol:    s.avg_volume_20 != null ? parseFloat(s.avg_volume_20) : null,
        rs_state:  s.rs_state,
        mom_state: s.momentum_state,
        sector:    s.gics_sector,
      }))
      .filter(p => !isNaN(p.x) && !isNaN(p.y) && p.x < VOL_CAP && Math.abs(p.y) < RET_CAP * 100)

    if (points.length === 0) {
      d3.select(svgEl).append('text')
        .attr('x', totalW / 2).attr('y', totalH / 2)
        .attr('text-anchor', 'middle')
        .attr('font-family', 'var(--font-sans)').attr('font-size', 13).attr('fill', '#94a3b8')
        .text('No stock data with sufficient history')
      return
    }

    const svg = d3.select(svgEl)
      .append('g')
      .attr('transform', `translate(${margin.left},${margin.top})`)

    const xExt = d3.extent(points, p => p.x) as [number, number]
    const xPad = (xExt[1] - xExt[0]) * 0.08 || 2
    const xScale = d3.scaleLinear().domain([Math.max(0, xExt[0] - xPad), xExt[1] + xPad]).range([0, W])

    const yExt = d3.extent(points, p => p.y) as [number, number]
    const yPad = (yExt[1] - yExt[0]) * 0.08 || 2
    const yScale = d3.scaleLinear().domain([yExt[0] - yPad, yExt[1] + yPad]).range([H, 0])

    const midX = xScale(d3.median(points, p => p.x) ?? (xExt[0] + xExt[1]) / 2)
    const midY = yScale(0)

    const quads = [
      { x: 0,    y: 0,    w: midX,      h: midY,     label: 'QUALITY',   sub: 'low vol · positive return',  bg: '#e2f0e8', text: '#2F6B43' },
      { x: midX, y: 0,    w: W - midX,  h: midY,     label: 'HIGH BETA', sub: 'high vol · positive return', bg: '#f5f0e8', text: '#B8860B' },
      { x: 0,    y: midY, w: midX,      h: H - midY, label: 'QUIET',     sub: 'low vol · negative return',  bg: '#e8f0f5', text: '#25394A' },
      { x: midX, y: midY, w: W - midX,  h: H - midY, label: 'DANGER',    sub: 'high vol · negative return', bg: '#f5e8e8', text: '#B0492C' },
    ]
    quads.forEach(q => {
      svg.append('rect')
        .attr('x', q.x).attr('y', q.y)
        .attr('width', q.w).attr('height', q.h)
        .attr('fill', q.bg).attr('opacity', 0.40)
      svg.append('text')
        .attr('x', q.x + q.w / 2)
        .attr('y', q.y + (q.y === 0 ? 14 : q.h - 14))
        .attr('text-anchor', 'middle')
        .attr('font-family', 'var(--font-sans)')
        .attr('font-size', 8).attr('font-weight', 700).attr('letter-spacing', 1.5)
        .attr('fill', q.text).attr('opacity', 0.65)
        .text(q.label)
    })

    svg.append('line').attr('x1', midX).attr('x2', midX).attr('y1', 0).attr('y2', H)
      .attr('stroke', '#94a3b8').attr('stroke-width', 1).attr('stroke-dasharray', '4 3')
    svg.append('line').attr('x1', 0).attr('x2', W).attr('y1', midY).attr('y2', midY)
      .attr('stroke', '#94a3b8').attr('stroke-width', 1).attr('stroke-dasharray', '4 3')

    svg.append('text')
      .attr('x', W + 4).attr('y', midY + 3)
      .attr('font-family', 'var(--font-sans)').attr('font-size', 8).attr('fill', '#94a3b8')
      .text('0%')

    svg.append('g')
      .attr('transform', `translate(0,${H})`)
      .call(d3.axisBottom(xScale).tickFormat(v => `${(+v).toFixed(0)}%`).ticks(6).tickSize(0))
      .call(ax => {
        ax.select('.domain').remove()
        ax.selectAll('.tick text').attr('font-family', 'var(--font-sans)').attr('font-size', 9)
          .attr('fill', '#94a3b8').attr('dy', 12)
      })
    svg.append('g')
      .call(d3.axisLeft(yScale).tickFormat(v => `${(+v) >= 0 ? '+' : ''}${(+v).toFixed(0)}%`).ticks(5).tickSize(0))
      .call(ax => {
        ax.select('.domain').remove()
        ax.selectAll('.tick text').attr('font-family', 'var(--font-sans)').attr('font-size', 9)
          .attr('fill', '#94a3b8').attr('dx', -6)
      })

    svg.append('text')
      .attr('x', W / 2).attr('y', H + 50).attr('text-anchor', 'middle')
      .attr('font-family', 'var(--font-sans)').attr('font-size', 10).attr('fill', '#64748b')
      .text('Annualised 63-Day Volatility (%) →')
    svg.append('text')
      .attr('transform', 'rotate(-90)')
      .attr('x', -H / 2).attr('y', -42).attr('text-anchor', 'middle')
      .attr('font-family', 'var(--font-sans)').attr('font-size', 10).attr('fill', '#64748b')
      .text(`↑ ${period} Return (%)`)

    const tip = d3.select(document.body)
      .append('div')
      .style('position', 'fixed').style('pointer-events', 'none')
      .style('opacity', '0').style('background', '#fff')
      .style('border', '1px solid #e2e8f0').style('border-radius', '2px')
      .style('padding', '8px 10px').style('font-family', 'var(--font-sans)')
      .style('font-size', '11px').style('color', '#1e293b')
      .style('z-index', '9999').style('box-shadow', '0 2px 8px rgba(0,0,0,0.08)')
      .style('min-width', '180px')

    const node = svg.selectAll<SVGGElement, typeof points[0]>('.us-stock-node')
      .data(points).enter().append('g')
      .attr('class', 'us-stock-node').style('cursor', 'default')

    node.append('circle')
      .attr('cx', p => xScale(p.x)).attr('cy', p => yScale(p.y))
      .attr('r', p => volumeToRadius(p.avgVol))
      .attr('fill', p => rsStateColor(p.rs_state)).attr('fill-opacity', 0.18)
      .attr('stroke', p => rsStateColor(p.rs_state)).attr('stroke-width', 1.5)

    node.append('text')
      .attr('x', p => xScale(p.x)).attr('y', p => yScale(p.y) + 3)
      .attr('text-anchor', 'middle')
      .attr('font-family', 'var(--font-sans)').attr('font-size', 6).attr('font-weight', 600)
      .attr('fill', p => rsStateColor(p.rs_state)).attr('pointer-events', 'none')
      .text(p => p.name !== p.ticker ? p.name.split(' ')[0] : p.ticker)

    node
      .on('mouseenter', function (event, p) {
        d3.select(this).select('circle').attr('fill-opacity', 0.32).attr('stroke-width', 2.5)
        const ret = `${p.y >= 0 ? '+' : ''}${p.y.toFixed(1)}%`
        tip.style('opacity', '1')
          .style('left', `${(event.clientX as number) + 14}px`)
          .style('top', `${(event.clientY as number) - 30}px`)
          .html(`
            <div style="font-weight:700;margin-bottom:2px;font-size:12px">${p.ticker}</div>
            <div style="color:#64748b;font-size:10px;margin-bottom:6px">${p.name !== p.ticker ? p.name : ''}</div>
            <div style="border-top:1px solid #f1f5f9;padding-top:5px;display:grid;gap:3px">
              <div style="color:#64748b">${period} Return: <span style="font-weight:600;color:${p.y >= 0 ? '#2F6B43' : '#B0492C'}">${ret}</span></div>
              <div style="color:#64748b">Volatility 63D: <span style="color:#1e293b">${p.x.toFixed(1)}%</span></div>
              <div style="color:#64748b">RS State: <span style="color:#1e293b">${p.rs_state ?? '—'}</span></div>
              <div style="color:#64748b">Momentum: <span style="color:#1e293b">${p.mom_state ?? '—'}</span></div>
              <div style="color:#64748b;font-size:10px">${p.sector ?? ''}</div>
            </div>
          `)
      })
      .on('mousemove', function (event) {
        tip.style('left', `${(event.clientX as number) + 14}px`).style('top', `${(event.clientY as number) - 30}px`)
      })
      .on('mouseleave', function () {
        d3.select(this).select('circle').attr('fill-opacity', 0.18).attr('stroke-width', 1.5)
        tip.style('opacity', '0')
      })

    return () => { tip.remove() }
  }, [displayed, period])

  return (
    <div>
      {/* Controls */}
      <div className="flex items-center gap-4 mb-4 flex-wrap">
        <div className="flex items-center gap-0.5 bg-paper-rule/20 rounded-sm p-0.5">
          {FILTERS.map(({ key, label }) => (
            <button
              key={key}
              onClick={() => setFilter(key)}
              className={
                'px-3 py-0.5 font-sans text-[10px] rounded-[2px] transition-colors ' +
                (filter === key
                  ? 'bg-paper text-ink-primary font-medium shadow-sm'
                  : 'text-ink-tertiary hover:text-ink-secondary')
              }
            >
              {label}
            </button>
          ))}
        </div>
        <div className="flex items-center gap-0.5 bg-paper-rule/20 rounded-sm p-0.5">
          {(['1M', '3M', '6M', '1Y'] as Period[]).map(p => (
            <button
              key={p}
              onClick={() => setPeriod(p)}
              className={
                'px-3 py-0.5 font-sans text-[10px] rounded-[2px] transition-colors ' +
                (period === p
                  ? 'bg-paper text-ink-primary font-medium shadow-sm'
                  : 'text-ink-tertiary hover:text-ink-secondary')
              }
            >
              {p}
            </button>
          ))}
        </div>
        <span className="ml-auto font-sans text-[10px] text-ink-tertiary">
          {displayed.length} stocks · bubble size = avg vol 20D
        </span>
      </div>

      <div ref={wrapRef} className="relative">
        <svg ref={svgRef} className="w-full" />
      </div>

      <div className="flex flex-wrap items-center gap-3 mt-2 pt-2 border-t border-paper-rule/40">
        {LEGEND.map(({ color, label }) => (
          <div key={label} className="flex items-center gap-1.5">
            <div className="w-2.5 h-2.5 rounded-full shrink-0" style={{ background: color }} />
            <span className="font-sans text-[10px] text-ink-tertiary">{label}</span>
          </div>
        ))}
      </div>
    </div>
  )
}
