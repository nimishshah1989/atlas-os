'use client'
import { useEffect, useRef, useState } from 'react'
import * as d3 from 'd3'
import { rsStateColor } from '@/lib/chart-colors'
import type { ETFRow } from '@/lib/queries/etfs'

// Phase 8: bubble size driven by mean_rs_rank_12m (0–1 continuous).
// Map rank 0–1 to radius 5–30 px.
function rsRankToRadius(rank: number | null): number {
  if (rank == null || rank <= 0) return 5
  return Math.min(30, 5 + rank * 25)
}

// ATR contraction ratio (atr_14_252d_ratio) is not yet in ETFRow — per Phase 8 spec,
// x-axis defaults to 1.0 (no contraction) until a per-ETF weighted-average ATR aggregation
// is added to the nightly ETF aggregator and atlas_etf_signal_unified view.
const ATR_RATIO_PLACEHOLDER = 1.0

type Theme = 'all' | 'Broad' | 'Sectoral'

const THEMES: { value: Theme; label: string }[] = [
  { value: 'all',      label: 'All' },
  { value: 'Broad',    label: 'Broad Market' },
  { value: 'Sectoral', label: 'Sectoral' },
]

export function ETFBubbleChart({
  etfs,
  onSelect,
}: {
  etfs: ETFRow[]
  onSelect?: (ticker: string) => void
}) {
  const [theme, setTheme] = useState<Theme>('all')
  const svgRef  = useRef<SVGSVGElement>(null)
  const wrapRef = useRef<HTMLDivElement>(null)
  const onSelectRef = useRef(onSelect)
  onSelectRef.current = onSelect

  const filtered = theme === 'all' ? etfs : etfs.filter(e => e.theme === theme)

  useEffect(() => {
    const container = wrapRef.current
    const svgEl = svgRef.current
    if (!container || !svgEl || filtered.length === 0) return

    const margin = { top: 40, right: 48, bottom: 64, left: 56 }
    const totalW = container.clientWidth
    const totalH = 460
    const W = totalW - margin.left - margin.right
    const H = totalH - margin.top - margin.bottom

    d3.select(svgEl).selectAll('*').remove()
    d3.select(svgEl).attr('width', totalW).attr('height', totalH)

    const svg = d3.select(svgEl)
      .append('g')
      .attr('transform', `translate(${margin.left},${margin.top})`)

    const points = filtered
      .map(e => ({
        ...e,
        // X: ATR contraction ratio — defaults to 1.0 until per-ETF aggregation is available
        x: ATR_RATIO_PLACEHOLDER,
        // Y: mean within-state rank (0–1) across holdings
        y: e.mean_within_state_rank != null ? e.mean_within_state_rank : NaN,
        rsRank: e.mean_rs_rank_12m,
      }))
      .filter(p => !isNaN(p.y))

    if (points.length === 0) {
      svg.append('text')
        .attr('x', W / 2).attr('y', H / 2)
        .attr('text-anchor', 'middle')
        .attr('font-family', 'var(--font-sans)').attr('font-size', 12).attr('fill', '#94a3b8')
        .text('No ETFs with sufficient data')
      return
    }

    // X axis: ATR contraction ratio — all points at 1.0 until per-ETF aggregation ships.
    // Spread points slightly along x using jitter so they're not all stacked.
    const xExt: [number, number] = [0.5, 1.5]
    const xScale = d3.scaleLinear().domain(xExt).range([0, W])

    const yExt = d3.extent(points, p => p.y) as [number, number]
    const yPad = (yExt[1] - yExt[0]) * 0.12 || 0.05
    const yScale = d3.scaleLinear().domain([Math.max(0, yExt[0] - yPad), Math.min(1, yExt[1] + yPad)]).range([H, 0])

    const midX = xScale(1.0)
    const midY = yScale(0.5)

    // Quadrant backgrounds — neutral tones, distinct from RS-state bubble colors
    const quads = [
      { x: 0,    y: 0,    w: midX,      h: midY,     label: 'LOW CONTRACTION',  sub: 'steady vol · high rank',   bg: '#e2f0e8', text: '#2F6B43' },
      { x: midX, y: 0,    w: W - midX,  h: midY,     label: 'EXPANDING VOL',    sub: 'vol rising · high rank',   bg: '#f5f0e8', text: '#B8860B' },
      { x: 0,    y: midY, w: midX,      h: H - midY, label: 'LOW CONTRACTION',  sub: 'steady vol · low rank',    bg: '#e8f0f5', text: '#25394A' },
      { x: midX, y: midY, w: W - midX,  h: H - midY, label: 'EXPANDING VOL',   sub: 'vol rising · low rank',    bg: '#f5e8e8', text: '#B0492C' },
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
        .attr('font-family', 'var(--font-sans)')
        .attr('font-size', 8).attr('font-weight', 700).attr('letter-spacing', 1.5)
        .attr('fill', q.text).attr('opacity', 0.65)
        .text(q.label)
      svg.append('text')
        .attr('x', q.x + q.w / 2)
        .attr('y', q.y + (q.y === 0 ? 26 : q.h - 4))
        .attr('text-anchor', 'middle')
        .attr('font-family', 'var(--font-sans)').attr('font-size', 7)
        .attr('fill', q.text).attr('opacity', 0.40)
        .text(q.sub)
    })

    svg.append('line').attr('x1', midX).attr('x2', midX).attr('y1', 0).attr('y2', H)
      .attr('stroke', '#94a3b8').attr('stroke-width', 1).attr('stroke-dasharray', '4 3')
    svg.append('line').attr('x1', 0).attr('x2', W).attr('y1', midY).attr('y2', midY)
      .attr('stroke', '#94a3b8').attr('stroke-width', 1).attr('stroke-dasharray', '4 3')

    // 0.5 rank label on Y axis
    svg.append('text')
      .attr('x', W + 4).attr('y', midY + 3)
      .attr('font-family', 'var(--font-sans)').attr('font-size', 8).attr('fill', '#94a3b8')
      .text('50%')

    // Axes
    svg.append('g')
      .attr('transform', `translate(0,${H})`)
      .call(d3.axisBottom(xScale).tickFormat(v => `${(+v).toFixed(2)}x`).ticks(4).tickSize(0))
      .call(ax => {
        ax.select('.domain').remove()
        ax.selectAll('.tick text').attr('font-family', 'var(--font-sans)').attr('font-size', 9)
          .attr('fill', '#94a3b8').attr('dy', 12)
      })
    svg.append('g')
      .call(d3.axisLeft(yScale).tickFormat(v => `${((+v) * 100).toFixed(0)}%`).ticks(5).tickSize(0))
      .call(ax => {
        ax.select('.domain').remove()
        ax.selectAll('.tick text').attr('font-family', 'var(--font-sans)').attr('font-size', 9)
          .attr('fill', '#94a3b8').attr('dx', -6)
      })

    svg.append('text')
      .attr('x', W / 2).attr('y', H + 50).attr('text-anchor', 'middle')
      .attr('font-family', 'var(--font-sans)').attr('font-size', 10).attr('fill', '#64748b')
      .text('Volatility contraction (ATR ratio) →')
    svg.append('text')
      .attr('transform', 'rotate(-90)')
      .attr('x', -H / 2).attr('y', -42).attr('text-anchor', 'middle')
      .attr('font-family', 'var(--font-sans)').attr('font-size', 10).attr('fill', '#64748b')
      .text('↑ Within-state rank (cohort)')

    // Tooltip
    const tip = d3.select(document.body)
      .append('div')
      .style('position', 'fixed').style('pointer-events', 'none')
      .style('opacity', '0').style('background', '#fff')
      .style('border', '1px solid #e2e8f0').style('border-radius', '2px')
      .style('padding', '8px 10px').style('font-family', 'var(--font-sans)')
      .style('font-size', '11px').style('color', '#1e293b')
      .style('z-index', '9999').style('box-shadow', '0 2px 8px rgba(0,0,0,0.08)')
      .style('min-width', '180px')

    const node = svg.selectAll<SVGGElement, typeof points[0]>('.etf-node')
      .data(points).enter().append('g')
      .attr('class', 'etf-node').style('cursor', 'pointer')

    node.append('circle')
      .attr('cx', p => xScale(p.x)).attr('cy', p => yScale(p.y))
      .attr('r', p => rsRankToRadius(p.rsRank))
      .attr('fill', p => rsStateColor(p.rs_state)).attr('fill-opacity', 0.18)
      .attr('stroke', p => rsStateColor(p.rs_state)).attr('stroke-width', 1.5)

    node.append('text')
      .attr('x', p => xScale(p.x)).attr('y', p => yScale(p.y) + 3)
      .attr('text-anchor', 'middle')
      .attr('font-family', 'var(--font-sans)').attr('font-size', 7).attr('font-weight', 600)
      .attr('fill', p => rsStateColor(p.rs_state)).attr('pointer-events', 'none')
      .text(p => p.ticker.length > 10 ? p.ticker.slice(0, 10) : p.ticker)

    node
      .on('mouseenter', function (event, p) {
        d3.select(this).select('circle').attr('fill-opacity', 0.32).attr('stroke-width', 2.5)
        const rankPct = p.y != null ? `${(p.y * 100).toFixed(0)}%` : '—'
        const rsRankPct = p.rsRank != null ? `${(p.rsRank * 100).toFixed(0)}%` : '—'
        tip.style('opacity', '1')
          .style('left', `${(event.clientX as number) + 14}px`)
          .style('top', `${(event.clientY as number) - 30}px`)
          .html(`
            <div style="font-weight:700;margin-bottom:3px;font-size:12px;line-height:1.3">${p.ticker}</div>
            <div style="color:#64748b;font-size:10px;margin-bottom:6px">${p.etf_name ?? ''}</div>
            <div style="border-top:1px solid #f1f5f9;padding-top:5px;display:grid;gap:3px">
              <div style="color:#64748b">Within-state rank: <span style="font-weight:600;color:#2F6B43">${rankPct}</span></div>
              <div style="color:#64748b">RS Rank 12M: <span style="color:#1e293b">${rsRankPct}</span></div>
              <div style="color:#64748b">RS State: <span style="color:#1e293b">${p.rs_state ?? '—'}</span></div>
              <div style="color:#64748b">Momentum: <span style="color:#1e293b">${p.momentum_state ?? '—'}</span></div>
              <div style="color:#64748b;font-size:10px">${p.theme}</div>
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
      .on('click', (_, p) => {
        tip.style('opacity', '0')
        if (onSelectRef.current) onSelectRef.current(p.ticker)
      })

    return () => { tip.remove() }
  }, [filtered])

  return (
    <div>
      {/* Theme filter */}
      <div className="flex items-center gap-0.5 bg-paper-rule/20 rounded-sm p-0.5 w-fit mb-4">
        {THEMES.map(({ value, label }) => (
          <button
            key={value}
            onClick={() => setTheme(value)}
            className={
              'px-3 py-0.5 font-sans text-[10px] rounded-[2px] transition-colors ' +
              (theme === value
                ? 'bg-paper text-ink-primary font-medium shadow-sm'
                : 'text-ink-tertiary hover:text-ink-secondary')
            }
          >
            {label}
          </button>
        ))}
      </div>
      <div ref={wrapRef} className="relative">
        <svg ref={svgRef} className="w-full" />
      </div>
      <div className="flex flex-wrap items-center gap-3 mt-2 pt-2 border-t border-paper-rule/40">
        {(['Leader', 'Strong', 'Average', 'Weak', 'Laggard'] as const).map(s => (
          <div key={s} className="flex items-center gap-1.5">
            <div className="w-2.5 h-2.5 rounded-full shrink-0" style={{ background: rsStateColor(s) }} />
            <span className="font-sans text-[10px] text-ink-tertiary">{s}</span>
          </div>
        ))}
        <div className="ml-auto font-sans text-[10px] text-ink-tertiary">
          Bubble size = RS rank 12M · {filtered.length} ETFs · ATR ratio axis pending aggregation
        </div>
      </div>
    </div>
  )
}
