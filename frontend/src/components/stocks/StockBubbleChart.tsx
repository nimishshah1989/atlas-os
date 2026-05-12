'use client'
// allow-large: single cohesive D3 component — axes, quadrants, tooltip, legend, filter chips all belong together
import { useEffect, useMemo, useRef, useState } from 'react'
import { useRouter } from 'next/navigation'
import * as d3 from 'd3'
import type { StockRowWithSector } from '@/lib/queries/stocks'

type Period = '1M' | '3M' | '6M' | '1Y'
type DisplayFilter = 'n100' | 'n500' | 'all'
type CapFilter = 'all' | 'large' | 'mid' | 'small'

const PERIOD_RET_KEY: Record<Period, keyof StockRowWithSector> = {
  '1M': 'ret_1m',
  '3M': 'ret_3m',
  '6M': 'ret_6m',
  '1Y': 'ret_12m',
}

const PERIOD_LABEL: Record<Period, string> = {
  '1M': '1M', '3M': '3M', '6M': '6M', '1Y': '1Y',
}

const DISPLAY_FILTERS: { key: DisplayFilter; label: string }[] = [
  { key: 'n100', label: 'N100' },
  { key: 'n500', label: 'N500' },
  { key: 'all',  label: 'All' },
]

const LEGEND = [
  { color: '#2F6B43', label: 'Leader' },
  { color: '#1D9E75', label: 'Strong' },
  { color: '#25394A', label: 'Emerging' },
  { color: '#B8860B', label: 'Consolidating' },
  { color: '#8C8278', label: 'Average' },
  { color: '#B0492C', label: 'Weak / Laggard' },
]

// Max return (absolute) to include — outliers beyond this distort the Y-axis
const RET_CAP = 1.5   // 150%
// Max annualized vol to include
const VOL_CAP = 120   // 120%

function volumeToRadius(vol: number | null): number {
  if (!vol || vol <= 0) return 5
  const log = Math.log10(Math.max(1000, vol))
  // ETF avg volumes for Indian stocks are typically 50K–50M shares.
  // log10(50K)=4.7, log10(50M)=7.7. Map linearly to radius 6–42 px.
  return Math.min(42, 6 + (log - 3) * 6)
}

function navStateColor(rs_state: string | null, _mom_state: string | null): string {
  if (rs_state === 'Leader')        return '#2F6B43'
  if (rs_state === 'Strong')        return '#1D9E75'
  if (rs_state === 'Emerging')      return '#25394A'
  if (rs_state === 'Consolidating') return '#B8860B'
  if (rs_state === 'Weak')          return '#B0492C'
  if (rs_state === 'Laggard')       return '#B0492C'
  return '#8C8278'
}

function formatVolume(vol: number | null): string {
  if (vol == null || vol <= 0) return '—'
  if (vol >= 10_000_000) return `${(vol / 10_000_000).toFixed(1)} Cr`
  return `${(vol / 100_000).toFixed(1)} L`
}

export function StockBubbleChart({ stocks }: { stocks: StockRowWithSector[] }) {
  const router     = useRouter()
  const routerRef  = useRef(router)
  routerRef.current = router

  const svgRef  = useRef<SVGSVGElement>(null)
  const wrapRef = useRef<HTMLDivElement>(null)

  const [period, setPeriod] = useState<Period>('3M')
  const [displayFilter, setDisplayFilter] = useState<DisplayFilter>('n500')
  const [capFilter, setCapFilter] = useState<CapFilter>('all')
  const [sectorFilter, setSectorFilter] = useState<string>('all')

  const sectors = useMemo(() => {
    const unique = Array.from(new Set(stocks.map(s => s.sector).filter((s): s is string => !!s))).sort()
    return unique
  }, [stocks])

  const filteredStocks = useMemo(() => {
    let s = stocks
    if (displayFilter === 'n100') s = s.filter(x => x.in_nifty_100)
    else if (displayFilter === 'n500') s = s.filter(x => x.in_nifty_500)
    if (capFilter === 'large') s = s.filter(x => x.in_nifty_100)
    else if (capFilter === 'mid') s = s.filter(x => x.in_nifty_500 && !x.in_nifty_100)
    else if (capFilter === 'small') s = s.filter(x => !x.in_nifty_500)
    if (sectorFilter !== 'all') s = s.filter(x => x.sector === sectorFilter)
    return s
  }, [stocks, displayFilter, capFilter, sectorFilter])

  const countsByFilter = useMemo(() => ({
    n100: stocks.filter(s => s.in_nifty_100).length,
    n500: stocks.filter(s => s.in_nifty_500).length,
    all:  stocks.length,
  }), [stocks])

  const visibleCount = useMemo(() => {
    const retKey = PERIOD_RET_KEY[period]
    return filteredStocks.filter(s => s[retKey] != null && s.realized_vol_63 != null).length
  }, [filteredStocks, period])

  useEffect(() => {
    const container = wrapRef.current
    const svgEl     = svgRef.current
    if (!container || !svgEl) return

    const retKey = PERIOD_RET_KEY[period]

    const points = filteredStocks.flatMap(s => {
      const retRaw = s[retKey] != null ? parseFloat(s[retKey] as string) : null
      const volRaw = s.realized_vol_63 != null ? parseFloat(s.realized_vol_63) * 100 : null
      if (retRaw == null || volRaw == null) return []
      if (Math.abs(retRaw) > RET_CAP || volRaw > VOL_CAP) return []
      const avgVol = s.avg_volume_20 != null ? parseFloat(s.avg_volume_20) : null
      return [{
        symbol:    s.symbol,
        company:   s.company_name,
        sector:    s.sector,
        x:         volRaw,
        y:         retRaw * 100,
        r:         volumeToRadius(avgVol),
        avgVol,
        color:     navStateColor(s.rs_state, s.momentum_state),
        rs_state:  s.rs_state,
        mom_state: s.momentum_state,
      }]
    })

    const margin = { top: 40, right: 48, bottom: 64, left: 64 }
    const totalW = container.clientWidth
    const totalH = 500
    const W = totalW - margin.left - margin.right
    const H = totalH - margin.top  - margin.bottom

    d3.select(svgEl).selectAll('*').remove()
    d3.select(svgEl).attr('width', totalW).attr('height', totalH)

    if (points.length === 0) {
      d3.select(svgEl).append('text')
        .attr('x', totalW / 2).attr('y', totalH / 2)
        .attr('text-anchor', 'middle')
        .attr('font-family', 'var(--font-sans)').attr('font-size', 12).attr('fill', '#94a3b8')
        .text('No stocks with data for this filter.')
      return
    }

    const svg = d3.select(svgEl).append('g')
      .attr('transform', `translate(${margin.left},${margin.top})`)

    // Axes
    const xExt = d3.extent(points, p => p.x) as [number, number]
    const xPad = Math.max((xExt[1] - xExt[0]) * 0.10, 2)
    const xScale = d3.scaleLinear()
      .domain([Math.max(0, xExt[0] - xPad), Math.min(VOL_CAP, xExt[1] + xPad)])
      .range([0, W])

    const yExt = d3.extent(points, p => p.y) as [number, number]
    const yPad = Math.max((yExt[1] - yExt[0]) * 0.12, 8)
    const yScale = d3.scaleLinear()
      .domain([
        Math.max(-75, Math.floor((yExt[0] - yPad) / 10) * 10),
        Math.min(150, Math.ceil( (yExt[1] + yPad) / 10) * 10),
      ])
      .range([H, 0])

    // Crosshair: X at median vol, Y at 0% return
    const xMed = d3.median(points, p => p.x) ?? 0
    const xMid = xScale(xMed)
    const yMid = yScale(0)

    // Quadrant tints
    const quads = [
      { x: 0,    y: 0,    w: xMid,      h: yMid,     label: 'QUALITY UPTREND', sub: 'low risk · positive return',  bg: '#e2f0e8', text: '#2F6B43' },
      { x: xMid, y: 0,    w: W - xMid,  h: yMid,     label: 'HIGH BETA',       sub: 'high risk · positive return', bg: '#f5f0e8', text: '#B8860B' },
      { x: 0,    y: yMid, w: xMid,      h: H - yMid, label: 'QUIET DRIFT',     sub: 'low risk · negative return',  bg: '#e8f0f5', text: '#25394A' },
      { x: xMid, y: yMid, w: W - xMid,  h: H - yMid, label: 'DANGER ZONE',    sub: 'high risk · negative return', bg: '#f5e8e8', text: '#B0492C' },
    ]
    quads.forEach(q => {
      svg.append('rect')
        .attr('x', q.x).attr('y', q.y)
        .attr('width', q.w).attr('height', q.h)
        .attr('fill', q.bg).attr('opacity', 0.45)
      svg.append('text')
        .attr('x', q.x + q.w / 2)
        .attr('y', q.y + (q.y === 0 ? 14 : q.h - 14))
        .attr('text-anchor', 'middle')
        .attr('font-family', 'var(--font-sans)').attr('font-size', 8).attr('font-weight', 700)
        .attr('letter-spacing', 1.5).attr('fill', q.text).attr('opacity', 0.65)
        .text(q.label)
      svg.append('text')
        .attr('x', q.x + q.w / 2)
        .attr('y', q.y + (q.y === 0 ? 26 : q.h - 4))
        .attr('text-anchor', 'middle')
        .attr('font-family', 'var(--font-sans)').attr('font-size', 7)
        .attr('fill', q.text).attr('opacity', 0.40)
        .text(q.sub)
    })

    // Crosshair lines
    svg.append('line')
      .attr('x1', xMid).attr('x2', xMid).attr('y1', 0).attr('y2', H)
      .attr('stroke', '#94a3b8').attr('stroke-width', 1).attr('stroke-dasharray', '4 3')
    svg.append('line')
      .attr('x1', 0).attr('x2', W).attr('y1', yMid).attr('y2', yMid)
      .attr('stroke', '#94a3b8').attr('stroke-width', 1).attr('stroke-dasharray', '4 3')

    // 0% label on Y axis
    svg.append('text')
      .attr('x', W + 4).attr('y', yMid + 3)
      .attr('font-family', 'var(--font-sans)').attr('font-size', 8).attr('fill', '#94a3b8')
      .text('0%')

    // Median vol label on X crosshair
    svg.append('text')
      .attr('x', xMid + 3).attr('y', 10)
      .attr('font-family', 'var(--font-sans)').attr('font-size', 8).attr('fill', '#94a3b8')
      .text(`${xMed.toFixed(0)}% vol`)

    // Bottom X axis
    svg.append('g')
      .attr('transform', `translate(0,${H})`)
      .call(d3.axisBottom(xScale).tickFormat(v => `${(+v).toFixed(0)}%`).ticks(6).tickSize(0))
      .call(ax => {
        ax.select('.domain').remove()
        ax.selectAll('.tick text')
          .attr('font-family', 'var(--font-sans)').attr('font-size', 9)
          .attr('fill', '#94a3b8').attr('dy', 12)
      })

    // Left Y axis
    svg.append('g')
      .call(d3.axisLeft(yScale)
        .tickFormat(v => `${(+v) >= 0 ? '+' : ''}${(+v).toFixed(0)}%`)
        .ticks(6).tickSize(0))
      .call(ax => {
        ax.select('.domain').remove()
        ax.selectAll('.tick text')
          .attr('font-family', 'var(--font-sans)').attr('font-size', 9)
          .attr('fill', '#94a3b8').attr('dx', -6)
      })

    svg.append('text')
      .attr('x', W / 2).attr('y', H + 50)
      .attr('text-anchor', 'middle')
      .attr('font-family', 'var(--font-sans)').attr('font-size', 10).attr('fill', '#64748b')
      .text('Volatility 63D (%) →')

    svg.append('text')
      .attr('transform', 'rotate(-90)')
      .attr('x', -H / 2).attr('y', -50)
      .attr('text-anchor', 'middle')
      .attr('font-family', 'var(--font-sans)').attr('font-size', 10).attr('fill', '#64748b')
      .text(`↑ ${PERIOD_LABEL[period]} Return (%)`)

    // Tooltip (fixed position so it escapes overflow:hidden parents)
    const tip = d3.select(document.body).append('div')
      .style('position', 'fixed').style('pointer-events', 'none')
      .style('opacity', '0').style('background', '#fff')
      .style('border', '1px solid #e2e8f0').style('border-radius', '2px')
      .style('padding', '8px 10px').style('font-family', 'var(--font-sans)')
      .style('font-size', '11px').style('color', '#1e293b')
      .style('z-index', '9999').style('box-shadow', '0 2px 8px rgba(0,0,0,0.08)')
      .style('min-width', '210px').style('max-width', '280px')

    // Render largest bubbles first (behind smaller ones)
    const sorted = [...points].sort((a, b) => b.r - a.r)

    const node = svg.selectAll<SVGGElement, typeof sorted[0]>('.stock-node')
      .data(sorted).enter().append('g')
      .attr('class', 'stock-node').style('cursor', 'pointer')

    node.append('circle')
      .attr('cx', p => xScale(p.x)).attr('cy', p => yScale(p.y))
      .attr('r',  p => p.r)
      .attr('fill',         p => p.color)
      .attr('fill-opacity', 0.70)
      .attr('stroke',       p => p.color)
      .attr('stroke-width', 0.5)
      .attr('stroke-opacity', 0.85)

    // Label large bubbles only (r >= 16px), truncated to 6 chars
    node.filter(p => p.r >= 16)
      .append('text')
      .attr('x', p => xScale(p.x)).attr('y', p => yScale(p.y) + 3)
      .attr('text-anchor', 'middle')
      .attr('font-family', 'var(--font-sans)').attr('font-size', 7).attr('font-weight', 600)
      .attr('fill', p => p.color).attr('pointer-events', 'none')
      .text(p => p.symbol.length > 6 ? p.symbol.slice(0, 6) : p.symbol)

    node
      .on('mouseenter', function (event, p) {
        d3.select(this).select('circle').attr('fill-opacity', 0.90).attr('stroke-width', 2)
        tip.style('opacity', '1')
          .style('left', `${(event.clientX as number) + 14}px`)
          .style('top',  `${(event.clientY as number) - 30}px`)
          .html(`
            <div style="font-weight:700;margin-bottom:2px;font-size:12px;line-height:1.3">${p.symbol}</div>
            <div style="color:#64748b;font-size:10px;margin-bottom:6px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:240px">${p.company}</div>
            <div style="border-top:1px solid #f1f5f9;padding-top:5px;display:grid;gap:3px">
              <div style="color:#64748b">${PERIOD_LABEL[period]} Return:
                <span style="font-weight:600;color:${p.y >= 0 ? '#2F6B43' : '#B0492C'}">
                  ${p.y >= 0 ? '+' : ''}${p.y.toFixed(1)}%
                </span>
              </div>
              <div style="color:#64748b">Volatility 63D: <span style="color:#1e293b">${p.x.toFixed(1)}%</span></div>
              <div style="color:#64748b">Avg Volume 20D: <span style="color:#1e293b">${formatVolume(p.avgVol)}</span></div>
              <div style="color:#64748b">RS State: <span style="color:#1e293b">${p.rs_state ?? '—'}</span></div>
              <div style="color:#64748b">Momentum State: <span style="color:#1e293b">${p.mom_state ?? '—'}</span></div>
              <div style="color:#64748b">Sector: <span style="color:#1e293b">${p.sector}</span></div>
            </div>
          `)
      })
      .on('mousemove', function (event) {
        tip.style('left', `${(event.clientX as number) + 14}px`)
           .style('top',  `${(event.clientY as number) - 30}px`)
      })
      .on('mouseleave', function () {
        d3.select(this).select('circle').attr('fill-opacity', 0.70).attr('stroke-width', 0.5)
        tip.style('opacity', '0')
      })
      .on('click', (_, p) => {
        tip.style('opacity', '0')
        routerRef.current.push(`/stocks/${encodeURIComponent(p.symbol)}`)
      })

    return () => { tip.remove() }
  }, [filteredStocks, period])

  return (
    <div className="border border-paper-rule rounded-sm bg-paper">
      {/* Header */}
      <div className="px-5 py-3 border-b border-paper-rule flex flex-wrap items-center gap-4">
        <span className="font-sans text-[10px] font-semibold text-ink-tertiary uppercase tracking-wider">
          Stock Map
        </span>
        <div className="flex gap-1">
          {(['1M', '3M', '6M', '1Y'] as Period[]).map(p => (
            <button key={p} type="button" onClick={() => setPeriod(p)}
              className={`px-2 py-0.5 rounded-sm font-sans text-[11px] font-medium transition-colors ${
                period === p ? 'bg-teal text-paper' : 'bg-paper-rule/20 text-ink-secondary hover:bg-paper-rule/40'
              }`}>
              {p}
            </button>
          ))}
        </div>
        <div className="flex gap-1 ml-auto items-center">
          <span className="font-sans text-[10px] text-ink-tertiary mr-1">Index:</span>
          {DISPLAY_FILTERS.map(f => (
            <button key={f.key} type="button" onClick={() => setDisplayFilter(f.key)}
              className={`px-2 py-0.5 rounded-sm font-sans text-[11px] font-medium transition-colors ${
                displayFilter === f.key
                  ? 'bg-ink-secondary text-paper'
                  : 'bg-paper-rule/20 text-ink-secondary hover:bg-paper-rule/40'
              }`}>
              {f.label} ({countsByFilter[f.key]})
            </button>
          ))}
        </div>
      </div>

      {/* Second filter row: cap + sector */}
      <div className="px-5 py-2 border-b border-paper-rule flex flex-wrap items-center gap-4">
        <div className="flex gap-1 items-center">
          <span className="font-sans text-[10px] text-ink-tertiary mr-1">Cap:</span>
          {(['all', 'large', 'mid', 'small'] as CapFilter[]).map(c => (
            <button key={c} type="button" onClick={() => setCapFilter(c)}
              className={`px-2 py-0.5 rounded-sm font-sans text-[11px] font-medium capitalize transition-colors ${
                capFilter === c
                  ? 'bg-teal text-paper'
                  : 'bg-paper-rule/20 text-ink-secondary hover:bg-paper-rule/40'
              }`}>
              {c === 'all' ? 'All' : c === 'large' ? 'Large (N100)' : c === 'mid' ? 'Mid (N500–N100)' : 'Small (ex-N500)'}
            </button>
          ))}
        </div>
        <div className="ml-auto flex items-center gap-2">
          <span className="font-sans text-[10px] text-ink-tertiary">Sector:</span>
          <select
            value={sectorFilter}
            onChange={e => setSectorFilter(e.target.value)}
            className="font-sans text-[11px] text-ink-secondary bg-paper border border-paper-rule rounded-sm px-2 py-0.5 focus:outline-none focus:border-teal"
          >
            <option value="all">All Sectors</option>
            {sectors.map(s => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
        </div>
      </div>

      {/* Description */}
      <div className="px-5 py-2 border-b border-paper-rule/40 bg-paper-rule/5">
        <p className="font-sans text-[11px] text-ink-secondary leading-relaxed">
          X = volatility 63D · Y = {period} return · Bubble = avg volume 20D · Color = RS state · Click for deep-dive
        </p>
      </div>

      {/* Legend */}
      <div className="px-5 pt-2 pb-1 flex flex-wrap items-center gap-3 border-b border-paper-rule/40">
        {LEGEND.map(l => (
          <div key={l.label} className="flex items-center gap-1.5">
            <div className="w-2.5 h-2.5 rounded-full shrink-0" style={{ background: l.color }} />
            <span className="font-sans text-[10px] text-ink-tertiary">{l.label}</span>
          </div>
        ))}
        <div className="ml-auto font-sans text-[10px] text-ink-tertiary">
          Bubble size = avg volume 20D · {visibleCount} stocks
        </div>
      </div>

      {/* Chart canvas */}
      <div ref={wrapRef} className="px-2 py-4">
        <svg ref={svgRef} className="w-full" />
      </div>
    </div>
  )
}
