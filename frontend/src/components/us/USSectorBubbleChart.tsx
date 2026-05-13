'use client'
import { useEffect, useRef, useState } from 'react'
import * as d3 from 'd3'
import type { USSectorRow } from '@/lib/queries/us-sectors'

type XView = 'rs' | 'ret-1m' | 'ret-3m' | 'ret-6m'

const SECTOR_SHORT: Record<string, string> = {
  'Information Technology': 'Tech',
  'Health Care': 'Health',
  'Financials': 'Finance',
  'Consumer Discretionary': 'Cons.Disc',
  'Communication Services': 'Comm',
  'Industrials': 'Indust.',
  'Consumer Staples': 'Staples',
  'Energy': 'Energy',
  'Materials': 'Materials',
  'Real Estate': 'RE',
  'Utilities': 'Utilities',
}

// rs_pctile values are 0-1 (rank/count), e.g. 0.65 = 65th percentile
function deriveSectorState(avgRsPctile: number): 'Overweight' | 'Neutral' | 'Underweight' | 'Avoid' {
  if (avgRsPctile >= 0.60) return 'Overweight'
  if (avgRsPctile >= 0.42) return 'Neutral'
  if (avgRsPctile >= 0.28) return 'Underweight'
  return 'Avoid'
}

const STATE_FILL: Record<string, string> = {
  Overweight:  '#1D9E75',
  Neutral:     '#F59E0B',
  Underweight: '#FB923C',
  Avoid:       '#EF4444',
}

const X_CONFIG: Record<XView, { label: string; tooltipLabel: string }> = {
  'rs':     { label: 'RS Percentile (vs VT, 3M) →', tooltipLabel: 'RS Pctile 3M' },
  'ret-1m': { label: '1M Return (avg) →',            tooltipLabel: 'Ret 1M' },
  'ret-3m': { label: '3M Return (avg) →',            tooltipLabel: 'Ret 3M' },
  'ret-6m': { label: '6M Return (avg) →',            tooltipLabel: 'Ret 6M' },
}

const MARGIN = { top: 20, right: 20, bottom: 50, left: 60 }

function getX(row: USSectorRow, view: XView): number | null {
  const raw =
    view === 'rs'     ? row.avg_rs_pctile_3m_vt :
    view === 'ret-1m' ? row.avg_ret_1m :
    view === 'ret-3m' ? row.avg_ret_3m :
                        row.avg_ret_6m
  if (raw == null) return null
  const v = parseFloat(raw)
  return isNaN(v) ? null : v
}

export function USSectorBubbleChart({ sectors }: { sectors: USSectorRow[] }) {
  const svgRef  = useRef<SVGSVGElement>(null)
  const wrapRef = useRef<HTMLDivElement>(null)
  const [xView, setXView] = useState<XView>('rs')

  useEffect(() => {
    const container = wrapRef.current
    const svgEl     = svgRef.current
    if (!container || !svgEl) return

    const totalW = container.clientWidth || 700
    const totalH = 420
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
        .attr('font-size', 13)
        .attr('fill', '#94a3b8')
        .text('No sector data available')
      return
    }

    const isRS = xView === 'rs'

    type Point = {
      name: string
      shortName: string
      x: number
      y: number
      liveCount: number
      state: string
      rsPctile: number
      participation: number
      ret3m: number | null
      leaderCount: number
    }

    const rawPoints: (Point | null)[] = sectors.map(row => {
      const xVal = getX(row, xView)
      const yVal = row.participation_rs != null ? parseFloat(row.participation_rs) : null
      const rsPctile = row.avg_rs_pctile_3m_vt != null ? parseFloat(row.avg_rs_pctile_3m_vt) : null
      if (xVal == null || isNaN(xVal) || yVal == null || isNaN(yVal) || rsPctile == null) return null
      return {
        name: row.gics_sector,
        shortName: SECTOR_SHORT[row.gics_sector] ?? row.gics_sector.slice(0, 8),
        x: xVal,
        y: yVal,
        liveCount: row.live_count,
        state: deriveSectorState(rsPctile),
        rsPctile,
        participation: yVal,
        ret3m: row.avg_ret_3m != null ? parseFloat(row.avg_ret_3m) : null,
        leaderCount: row.rs_state_leader,
      } satisfies Point
    })
    const points: Point[] = rawPoints.filter((p): p is Point => p !== null)

    if (points.length === 0) {
      d3.select(svgEl)
        .append('text')
        .attr('x', totalW / 2).attr('y', totalH / 2)
        .attr('text-anchor', 'middle')
        .attr('font-family', 'var(--font-sans)')
        .attr('font-size', 13)
        .attr('fill', '#94a3b8')
        .text('Insufficient data to render chart')
      return
    }

    // Scales
    const xDomain: [number, number] = isRS
      ? [0, 1]
      : (() => {
          const ext = d3.extent(points, p => p.x) as [number, number]
          const pad = (ext[1] - ext[0]) * 0.15 || 2
          return [ext[0] - pad, ext[1] + pad]
        })()

    const xScale = d3.scaleLinear().domain(xDomain).range([0, W])
    const yScale = d3.scaleLinear().domain([0, 100]).range([H, 0])

    const maxLive = d3.max(points, p => p.liveCount) ?? 1
    const rScale  = d3.scaleSqrt().domain([0, maxLive]).range([8, 22])

    const svg = d3.select(svgEl)
      .append('g')
      .attr('transform', `translate(${MARGIN.left},${MARGIN.top})`)

    // Quadrant backgrounds (only for RS view)
    if (isRS) {
      const midX = xScale(0.5)
      const midY = yScale(35)
      const quads = [
        { x: midX,  y: 0,    w: W - midX,  h: midY,     label: 'Quality Leaders', bg: '#e2f4ee', tc: '#1D9E75' },
        { x: 0,     y: 0,    w: midX,      h: midY,     label: 'Improving',       bg: '#e8f0f8', tc: '#3B82F6' },
        { x: midX,  y: midY, w: W - midX,  h: H - midY, label: 'Weakening',       bg: '#fef3c7', tc: '#D97706' },
        { x: 0,     y: midY, w: midX,      h: H - midY, label: 'Lagging',         bg: '#fee2e2', tc: '#EF4444' },
      ]
      quads.forEach(q => {
        svg.append('rect')
          .attr('x', q.x).attr('y', q.y)
          .attr('width', q.w).attr('height', q.h)
          .attr('fill', q.bg).attr('opacity', 0.35)
        svg.append('text')
          .attr('x', q.x + q.w / 2)
          .attr('y', q.y + (q.y === 0 ? 14 : q.h - 8))
          .attr('text-anchor', 'middle')
          .attr('font-family', 'var(--font-sans)')
          .attr('font-size', 8).attr('font-weight', 700)
          .attr('letter-spacing', 1)
          .attr('fill', q.tc).attr('opacity', 0.55)
          .text(q.label.toUpperCase())
      })
      // Reference lines
      svg.append('line')
        .attr('x1', midX).attr('x2', midX).attr('y1', 0).attr('y2', H)
        .attr('stroke', '#94a3b8').attr('stroke-width', 1).attr('stroke-dasharray', '4 3')
      svg.append('line')
        .attr('x1', 0).attr('x2', W).attr('y1', midY).attr('y2', midY)
        .attr('stroke', '#94a3b8').attr('stroke-width', 1).attr('stroke-dasharray', '4 3')
    }

    // Axes
    // RS pctile stored 0-1, display as whole-number percentile (0–100)
    const xFmt = isRS
      ? (v: d3.NumberValue) => `${Math.round(+v * 100)}`
      : (v: d3.NumberValue) => `${(+v * 100).toFixed(0)}%`

    svg.append('g')
      .attr('transform', `translate(0,${H})`)
      .call(d3.axisBottom(xScale).ticks(6).tickFormat(xFmt).tickSize(0))
      .call(ax => {
        ax.select('.domain').remove()
        ax.selectAll('.tick text')
          .attr('font-family', 'var(--font-sans)').attr('font-size', 9)
          .attr('fill', '#94a3b8').attr('dy', 12)
      })

    svg.append('g')
      .call(d3.axisLeft(yScale).ticks(5).tickFormat(v => `${+v}%`).tickSize(0))
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
      .text(X_CONFIG[xView].label)

    svg.append('text')
      .attr('transform', 'rotate(-90)')
      .attr('x', -H / 2).attr('y', -46)
      .attr('text-anchor', 'middle')
      .attr('font-family', 'var(--font-sans)').attr('font-size', 10).attr('fill', '#64748b')
      .text('↑ Participation RS %')

    // Tooltip
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
      .style('min-width', '168px')

    const nodes = svg.selectAll<SVGGElement, Point>('.bubble-node')
      .data(points)
      .enter()
      .append('g')
      .attr('class', 'bubble-node')
      .style('cursor', 'default')

    nodes.append('circle')
      .attr('cx', p => xScale(p.x))
      .attr('cy', p => yScale(p.y))
      .attr('r',  p => rScale(p.liveCount))
      .attr('fill',         p => STATE_FILL[p.state] ?? '#94a3b8')
      .attr('fill-opacity', 0.80)
      .attr('stroke',       p => STATE_FILL[p.state] ?? '#94a3b8')
      .attr('stroke-width', 1.5)
      .attr('stroke-opacity', 1)

    nodes.append('text')
      .attr('x', p => xScale(p.x))
      .attr('y', p => yScale(p.y) + 3)
      .attr('text-anchor', 'middle')
      .attr('font-family', 'var(--font-sans)')
      .attr('font-size', 7)
      .attr('font-weight', 600)
      .attr('fill', '#fff')
      .attr('pointer-events', 'none')
      .text(p => p.shortName)

    nodes
      .on('mouseenter', function (event: MouseEvent, p: Point) {
        d3.select(this).select('circle').attr('fill-opacity', 1).attr('stroke-width', 2.5)
        const ret3mStr = p.ret3m != null
          ? `${p.ret3m >= 0 ? '+' : ''}${(p.ret3m * 100).toFixed(1)}%`
          : '—'
        tip
          .style('opacity', '1')
          .style('left', `${(event.clientX as number) + 14}px`)
          .style('top',  `${(event.clientY as number) - 30}px`)
          .html(`
            <div style="font-weight:700;margin-bottom:4px">${p.name}</div>
            <div style="color:#64748b;margin-bottom:2px">
              State: <span style="font-weight:600;color:${STATE_FILL[p.state]}">${p.state}</span>
            </div>
            <div style="color:#64748b">RS Pctile: <span style="color:#1e293b">${Math.round(p.rsPctile * 100)}</span></div>
            <div style="color:#64748b">Participation RS: <span style="color:#1e293b">${p.participation.toFixed(1)}%</span></div>
            <div style="color:#64748b">Ret 3M: <span style="color:#1e293b">${ret3mStr}</span></div>
            <div style="color:#64748b">Leaders: <span style="color:#1e293b">${p.leaderCount}</span></div>
            <div style="color:#64748b">Live stocks: <span style="color:#1e293b">${p.liveCount}</span></div>
          `)
      })
      .on('mousemove', function (event: MouseEvent) {
        tip
          .style('left', `${(event.clientX as number) + 14}px`)
          .style('top',  `${(event.clientY as number) - 30}px`)
      })
      .on('mouseleave', function () {
        d3.select(this).select('circle').attr('fill-opacity', 0.80).attr('stroke-width', 1.5)
        tip.style('opacity', '0')
      })

    return () => { tip.remove() }
  }, [sectors, xView])

  if (sectors.length === 0) {
    return (
      <div className="flex items-center justify-center h-48 text-ink-tertiary font-sans text-sm">
        No data
      </div>
    )
  }

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-1">
        {(['rs', 'ret-1m', 'ret-3m', 'ret-6m'] as XView[]).map(v => (
          <button
            key={v}
            onClick={() => setXView(v)}
            className={[
              'px-2.5 py-0.5 rounded text-[11px] font-sans font-medium border transition-colors',
              xView === v
                ? 'bg-teal-600 text-white border-teal-600'
                : 'bg-paper text-ink-secondary border-paper-rule hover:border-teal-400',
            ].join(' ')}
          >
            {v === 'rs' ? 'RS 3M' : v === 'ret-1m' ? '1M' : v === 'ret-3m' ? '3M' : '6M'}
          </button>
        ))}
        <span className="ml-2 text-[10px] text-ink-tertiary font-sans">X axis</span>
      </div>
      <div ref={wrapRef} className="relative w-full h-[420px] overflow-visible">
        <svg ref={svgRef} className="w-full" />
      </div>
      <div className="flex flex-wrap items-center gap-3 pt-1.5 border-t border-paper-rule/40">
        {(['Overweight', 'Neutral', 'Underweight', 'Avoid'] as const).map(s => (
          <div key={s} className="flex items-center gap-1.5">
            <div className="w-2.5 h-2.5 rounded-full shrink-0" style={{ background: STATE_FILL[s] }} />
            <span className="font-sans text-[10px] text-ink-tertiary">{s}</span>
          </div>
        ))}
        <div className="ml-auto font-sans text-[10px] text-ink-tertiary">Bubble size = live stocks</div>
      </div>
    </div>
  )
}
