'use client'
import { useEffect, useMemo, useRef } from 'react'
import { useRouter } from 'next/navigation'
import * as d3 from 'd3'
import type { FundRow } from '@/lib/queries/funds'
import type { Period } from '@/lib/url-params'
import type { FilterChip } from '@/components/funds/FundPageClient'
import { rsStateColor } from '@/lib/chart-colors'

// allow-large: single cohesive D3 component — axes, quadrants, tooltip, legend, filter chips all belong together

const RET_CAP = 1.5   // 150% — exclude extreme outliers

const PERIOD_RET_KEY: Record<Period, keyof FundRow> = {
  '1M': 'ret_1m',
  '3M': 'ret_3m',
  '6M': 'ret_6m',
  '1Y': 'ret_12m',
}

const PERIOD_LABEL: Record<Period, string> = {
  '1M': '1M', '3M': '3M', '6M': '6M', '1Y': '1Y',
}

const BUBBLE_FILTERS: { key: FilterChip; label: string }[] = [
  { key: 'all',         label: 'All' },
  { key: 'recommended', label: 'Recommended' },
  { key: 'hold',        label: 'Hold' },
  { key: 'leader_nav',  label: 'Leader NAV' },
]

const LEGEND = [
  { color: '#2F6B43', label: 'Leader NAV' },
  { color: '#1D9E75', label: 'Strong NAV' },
  { color: '#25394A', label: 'Emerging NAV' },
  { color: '#B8860B', label: 'Consolidating NAV' },
  { color: '#8C8278', label: 'Average NAV' },
  { color: '#B0492C', label: 'Weak / Laggard NAV' },
]

// Log-linear radius: every 10× AUM increase = constant radius step.
// Gives clear visual differentiation across the 100 Cr → 1 lakh Cr range.
function aumToRadius(aum: number | null): number {
  if (!aum || aum <= 0) return 5
  const log = Math.log10(Math.max(10, aum))
  // log10 of 10 Cr = 1, of ~10M Cr = 7. Map linearly to radius 6–46 px.
  return Math.min(46, 6 + (log - 1) * 6.67)
}

type Props = {
  funds: FundRow[]
  period: Period
  activeFilter: FilterChip
  onFilterChange: (f: FilterChip) => void
  onPeriodChange: (p: Period) => void
}

export function FundBubbleChart({ funds, period, activeFilter, onFilterChange, onPeriodChange }: Props) {
  const router     = useRouter()
  const routerRef  = useRef(router)
  routerRef.current = router

  const svgRef  = useRef<SVGSVGElement>(null)
  const wrapRef = useRef<HTMLDivElement>(null)

  const filteredFunds = useMemo(() => {
    if (activeFilter === 'all')         return funds
    if (activeFilter === 'recommended') return funds.filter(f => f.recommendation === 'Recommended')
    if (activeFilter === 'hold')        return funds.filter(f => f.recommendation === 'Hold')
    if (activeFilter === 'leader_nav')  return funds.filter(f => f.nav_state === 'Leader NAV')
    return funds
  }, [funds, activeFilter])

  const visibleCount = useMemo(() => {
    const retKey = PERIOD_RET_KEY[period]
    return filteredFunds.filter(f => f[retKey] != null && f.realized_vol_63 != null).length
  }, [filteredFunds, period])

  useEffect(() => {
    const container = wrapRef.current
    const svgEl     = svgRef.current
    if (!container || !svgEl) return

    const retKey = PERIOD_RET_KEY[period]

    const points = filteredFunds.flatMap(f => {
      const retRaw = f[retKey] != null ? parseFloat(f[retKey] as string) : null
      const volRaw = f.realized_vol_63 != null ? parseFloat(f.realized_vol_63) : null
      if (retRaw == null || volRaw == null) return []
      if (Math.abs(retRaw) > RET_CAP) return []
      const aumRaw      = f.aum_cr != null ? parseFloat(f.aum_cr) : null
      const navStateKey = f.nav_state ? f.nav_state.replace(/ NAV$/, '') : null
      return [{
        mstarId:        f.mstar_id,
        schemeName:     f.scheme_name,
        amc:            f.amc,
        x:              volRaw * 100,
        y:              retRaw * 100,
        r:              aumToRadius(aumRaw),
        aum:            aumRaw,
        color:          rsStateColor(navStateKey),
        recommendation: f.recommendation,
        navState:       f.nav_state,
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
        .text('No funds with data for this filter.')
      return
    }

    const svg = d3.select(svgEl).append('g')
      .attr('transform', `translate(${margin.left},${margin.top})`)

    // Axes
    const xExt = d3.extent(points, p => p.x) as [number, number]
    const xPad = Math.max((xExt[1] - xExt[0]) * 0.10, 1)
    const xScale = d3.scaleLinear()
      .domain([Math.max(0, xExt[0] - xPad), xExt[1] + xPad])
      .range([0, W])

    const yExt = d3.extent(points, p => p.y) as [number, number]
    const yPad = Math.max((yExt[1] - yExt[0]) * 0.12, 5)
    const yScale = d3.scaleLinear()
      .domain([
        Math.max(-80, Math.floor((yExt[0] - yPad) / 5) * 5),
        Math.min(150, Math.ceil( (yExt[1] + yPad) / 5) * 5),
      ])
      .range([H, 0])

    // Crosshair: X at median vol, Y at 0% return
    const xMed = d3.median(points, p => p.x) ?? 0
    const xMid = xScale(xMed)
    const yMid = yScale(0)

    // Quadrant tints (same palette as Sector + ETF charts)
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

    const node = svg.selectAll<SVGGElement, typeof sorted[0]>('.fund-node')
      .data(sorted).enter().append('g')
      .attr('class', 'fund-node').style('cursor', 'pointer')

    node.append('circle')
      .attr('cx', p => xScale(p.x)).attr('cy', p => yScale(p.y))
      .attr('r',  p => p.r)
      .attr('fill',         p => p.color)
      .attr('fill-opacity', p => p.recommendation === 'Recommended' ? 0.22 : 0.14)
      .attr('stroke',       p => p.color)
      .attr('stroke-width', 1.5)

    // Label large bubbles only (AUM large enough to read)
    node.filter(p => p.r >= 20)
      .append('text')
      .attr('x', p => xScale(p.x)).attr('y', p => yScale(p.y) + 3)
      .attr('text-anchor', 'middle')
      .attr('font-family', 'var(--font-sans)').attr('font-size', 7).attr('font-weight', 600)
      .attr('fill', p => p.color).attr('pointer-events', 'none')
      .text(p => {
        const short = p.schemeName
          .replace(/\b(Direct|Regular|Growth|IDCW|Plan|Fund)\b.*/i, '')
          .trim()
        return short.length > 15 ? short.slice(0, 15) + '…' : short
      })

    node
      .on('mouseenter', function (event, p) {
        d3.select(this).select('circle').attr('fill-opacity', 0.35).attr('stroke-width', 2.5)
        tip.style('opacity', '1')
          .style('left', `${(event.clientX as number) + 14}px`)
          .style('top',  `${(event.clientY as number) - 30}px`)
          .html(`
            <div style="font-weight:700;margin-bottom:3px;font-size:12px;line-height:1.3">${p.schemeName}</div>
            <div style="color:#64748b;font-size:10px;margin-bottom:6px">${p.amc}</div>
            <div style="border-top:1px solid #f1f5f9;padding-top:5px;display:grid;gap:3px">
              <div style="color:#64748b">${PERIOD_LABEL[period]} Return:
                <span style="font-weight:600;color:${p.y >= 0 ? '#2F6B43' : '#B0492C'}">
                  ${p.y >= 0 ? '+' : ''}${p.y.toFixed(1)}%
                </span>
              </div>
              <div style="color:#64748b">Volatility 63D: <span style="color:#1e293b">${p.x.toFixed(1)}%</span></div>
              <div style="color:#64748b">AUM:
                <span style="color:#1e293b">
                  ${p.aum != null ? '₹' + p.aum.toLocaleString('en-IN', { maximumFractionDigits: 0 }) + ' Cr' : '—'}
                </span>
              </div>
              <div style="color:#64748b">NAV State: <span style="color:#1e293b">${p.navState ?? '—'}</span></div>
              <div style="color:#64748b">Recommendation: <span style="color:#1e293b">${p.recommendation ?? '—'}</span></div>
            </div>
          `)
      })
      .on('mousemove', function (event) {
        tip.style('left', `${(event.clientX as number) + 14}px`)
           .style('top',  `${(event.clientY as number) - 30}px`)
      })
      .on('mouseleave', function (_, p) {
        d3.select(this).select('circle')
          .attr('fill-opacity', p.recommendation === 'Recommended' ? 0.22 : 0.14)
          .attr('stroke-width', 1.5)
        tip.style('opacity', '0')
      })
      .on('click', (_, p) => {
        tip.style('opacity', '0')
        routerRef.current.push(`/funds/${p.mstarId}`)
      })

    return () => { tip.remove() }
  }, [filteredFunds, period])

  return (
    <div className="border border-paper-rule rounded-sm bg-paper">
      {/* Header */}
      <div className="px-5 py-3 border-b border-paper-rule flex flex-wrap items-center gap-4">
        <span className="font-sans text-[10px] font-semibold text-ink-tertiary uppercase tracking-wider">
          Fund Map
        </span>
        <div className="flex items-center gap-0.5 border border-paper-rule rounded-sm overflow-hidden">
          {(['1M', '3M', '6M', '1Y'] as Period[]).map(p => (
            <button
              key={p} type="button" onClick={() => onPeriodChange(p)}
              className={`px-2.5 py-0.5 font-sans text-[11px] font-medium transition-colors ${
                period === p ? 'bg-teal text-white' : 'text-ink-secondary hover:bg-paper-rule/30'
              }`}
            >
              {p}
            </button>
          ))}
        </div>
        <div className="flex gap-1">
          {BUBBLE_FILTERS.map(f => (
            <button
              key={f.key} type="button" onClick={() => onFilterChange(f.key)}
              className={`px-2 py-0.5 rounded-sm font-sans text-[11px] font-medium transition-colors ${
                activeFilter === f.key
                  ? 'bg-ink-secondary text-paper'
                  : 'bg-paper-rule/20 text-ink-secondary hover:bg-paper-rule/40'
              }`}
            >
              {f.label}
            </button>
          ))}
        </div>
      </div>

      {/* Description */}
      <div className="px-5 py-2 border-b border-paper-rule/40 bg-paper-rule/5">
        <p className="font-sans text-[11px] text-ink-secondary leading-relaxed">
          X = volatility 63D · Y = {period} return · Bubble = AUM · Color = NAV state · Click for deep-dive
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
          Bubble size = AUM · {visibleCount} funds
        </div>
      </div>

      {/* Chart canvas */}
      <div ref={wrapRef} className="px-2 py-4">
        <svg ref={svgRef} className="w-full" />
      </div>
    </div>
  )
}
