'use client'
import { useState, useMemo, useCallback } from 'react'
import { useRouter } from 'next/navigation'
import {
  ScatterChart,
  Scatter,
  XAxis,
  YAxis,
  ZAxis,
  Tooltip,
  ReferenceLine,
  ReferenceArea,
  ResponsiveContainer,
  Cell,
} from 'recharts'
import type { FullStockRow } from '@/lib/queries/stocks'

type Period = '1M' | '3M' | '6M' | '1Y'
type DisplayFilter = 'n100' | 'n500' | 'all'

const PERIOD_RET_KEY: Record<Period, keyof FullStockRow> = {
  '1M': 'ret_1m',
  '3M': 'ret_3m',
  '6M': 'ret_6m',
  '1Y': 'ret_12m',
}

const DISPLAY_FILTERS: { key: DisplayFilter; label: string }[] = [
  { key: 'n100', label: 'N100' },
  { key: 'n500', label: 'N500' },
  { key: 'all',  label: 'All' },
]

// Max return (absolute) to include — outliers beyond this distort the Y-axis
const RET_CAP = 1.5    // 150%
// Max annualized vol to include
const VOL_CAP = 120    // 120%

function stockColor(rs: string | null, mom: string | null): string {
  if (rs === 'Leader') return '#2F6B43'
  if (rs === 'Strong')
    return (mom === 'Deteriorating' || mom === 'Collapsing') ? '#f59e0b' : '#1D9E75'
  if (rs === 'Emerging')      return '#0ea5e9'
  if (rs === 'Consolidating') return '#f59e0b'
  if (rs === 'Average')       return '#94a3b8'
  return '#ef4444'
}

type BubblePoint = {
  x: number   // annualized vol %
  y: number   // return %
  z: number   // normalized log volume
  symbol: string
  company: string
  sector: string
  color: string
  rs_state: string | null
  mom_state: string | null
}

function CustomTooltip({ active, payload }: { active?: boolean; payload?: Array<{ payload: BubblePoint }> }) {
  if (!active || !payload?.length) return null
  const d = payload[0].payload
  return (
    <div className="bg-paper border border-paper-rule rounded-sm shadow-md px-3 py-2 font-sans text-xs max-w-[220px]">
      <div className="font-semibold text-ink-primary">{d.symbol}</div>
      <div className="text-ink-tertiary text-[10px] mb-1 truncate">{d.company}</div>
      <div className="text-ink-secondary mb-1.5">{d.sector}</div>
      <div className="space-y-0.5 border-t border-paper-rule/40 pt-1.5">
        <div className="text-ink-secondary">
          Return: <span className={d.y >= 0 ? 'text-signal-pos font-medium' : 'text-signal-neg font-medium'}>
            {d.y >= 0 ? '+' : ''}{d.y.toFixed(1)}%
          </span>
        </div>
        <div className="text-ink-secondary">Volatility (63D): {d.x.toFixed(0)}%</div>
        <div className="text-ink-tertiary text-[10px] mt-1">{d.rs_state ?? '—'} · {d.mom_state ?? '—'}</div>
      </div>
    </div>
  )
}

// Custom SVG label for each ReferenceArea quadrant
// viewBox gives pixel bounds of the area inside the chart
type QuadrantPos = 'tl' | 'tr' | 'bl' | 'br'
function quadLabel(pos: QuadrantPos, text: string, sub: string, color: string) {
  return function QuadLabel({ viewBox }: { viewBox?: { x: number; y: number; width: number; height: number } }) {
    if (!viewBox) return null
    const { x, y, width, height } = viewBox
    const isRight = pos === 'tr' || pos === 'br'
    const isBottom = pos === 'bl' || pos === 'br'
    const tx = isRight ? x + width - 10 : x + 10
    const ty1 = isBottom ? y + height - 18 : y + 14
    const ty2 = isBottom ? y + height - 6  : y + 24
    const anchor = isRight ? 'end' : 'start'
    return (
      <g>
        <text
          x={tx} y={ty1}
          fill={color} fillOpacity={0.55}
          fontSize={9} fontWeight={700}
          fontFamily="var(--font-sans)"
          textAnchor={anchor}
          letterSpacing={1.2}
        >
          {text.toUpperCase()}
        </text>
        <text
          x={tx} y={ty2}
          fill={color} fillOpacity={0.35}
          fontSize={8}
          fontFamily="var(--font-sans)"
          textAnchor={anchor}
        >
          {sub}
        </text>
      </g>
    )
  }
}

export function StockBubbleChart({ stocks }: { stocks: FullStockRow[] }) {
  const router = useRouter()
  const [period, setPeriod] = useState<Period>('3M')
  const [displayFilter, setDisplayFilter] = useState<DisplayFilter>('n500')

  const filteredStocks = useMemo(() => {
    if (displayFilter === 'n100') return stocks.filter(s => s.in_nifty_100)
    if (displayFilter === 'n500') return stocks.filter(s => s.in_nifty_500)
    return stocks
  }, [stocks, displayFilter])

  // Compute log-volume range for normalization (per displayed cohort)
  const { logVolMin, logVolMax } = useMemo(() => {
    const logs = filteredStocks
      .map(s => s.avg_volume_20 != null ? Math.log10(parseFloat(s.avg_volume_20) + 1) : null)
      .filter((v): v is number => v != null && isFinite(v))
    if (logs.length < 2) return { logVolMin: 4, logVolMax: 8 }
    return { logVolMin: Math.min(...logs), logVolMax: Math.max(...logs) }
  }, [filteredStocks])

  const data = useMemo<BubblePoint[]>(() => {
    const retKey = PERIOD_RET_KEY[period]
    return filteredStocks.flatMap(s => {
      const retRaw = s[retKey] != null ? parseFloat(s[retKey] as string) : null
      const volRaw = s.realized_vol_63 != null ? parseFloat(s.realized_vol_63) * 100 : null

      if (retRaw == null || volRaw == null) return []
      if (Math.abs(retRaw) > RET_CAP || volRaw > VOL_CAP) return []

      const logVol = s.avg_volume_20 != null ? Math.log10(parseFloat(s.avg_volume_20) + 1) : null
      const range = logVolMax - logVolMin || 1
      const z = logVol != null
        ? 18 + Math.round(((logVol - logVolMin) / range) * 242)
        : 35

      return [{
        x: volRaw,
        y: retRaw * 100,
        z,
        symbol: s.symbol,
        company: s.company_name,
        sector: s.sector,
        color: stockColor(s.rs_state, s.momentum_state),
        rs_state: s.rs_state,
        mom_state: s.momentum_state,
      }]
    })
  }, [filteredStocks, period, logVolMin, logVolMax])

  // Dynamic Y domain — pad 15% beyond actual range, capped
  const [yMin, yMax] = useMemo(() => {
    if (data.length === 0) return [-50, 80]
    const ys = data.map(d => d.y)
    const lo = Math.min(...ys), hi = Math.max(...ys)
    const pad = Math.max((hi - lo) * 0.12, 8)
    return [
      Math.max(-75, Math.floor((lo - pad) / 10) * 10),
      Math.min(150, Math.ceil((hi + pad) / 10) * 10),
    ]
  }, [data])

  // Dynamic X midpoint — median volatility of plotted stocks, rounded to nearest 5
  const volMedian = useMemo(() => {
    if (data.length === 0) return 35
    const xs = [...data.map(d => d.x)].sort((a, b) => a - b)
    const raw = xs[Math.floor(xs.length / 2)]
    return Math.round(raw / 5) * 5
  }, [data])

  const handleClick = useCallback((point: { payload?: BubblePoint }) => {
    if (point?.payload?.symbol)
      router.push(`/stocks/${encodeURIComponent(point.payload.symbol)}`)
  }, [router])

  const countsByFilter = useMemo(() => ({
    n100: stocks.filter(s => s.in_nifty_100).length,
    n500: stocks.filter(s => s.in_nifty_500).length,
    all:  stocks.length,
  }), [stocks])

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
          <span className="font-sans text-[10px] text-ink-tertiary mr-1">Show:</span>
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

      {/* Description */}
      <div className="px-5 py-2 border-b border-paper-rule/40 bg-paper-rule/5">
        <p className="font-sans text-[11px] text-ink-secondary leading-relaxed">
          <span className="font-semibold">Risk vs Return:</span>{' '}
          X = annualized 63-day volatility · Y = {period} return · Bubble size = 20-day avg volume (larger = more liquid).
          Ideal stocks sit top-left. Quadrant split at median vol ({volMedian}%). Click any bubble to open deep-dive.
        </p>
      </div>

      {/* Legend */}
      <div className="px-5 pt-2 pb-1 flex flex-wrap items-center gap-3 border-b border-paper-rule/40">
        {[
          { color: '#2F6B43', label: 'Leader' },
          { color: '#1D9E75', label: 'Strong' },
          { color: '#0ea5e9', label: 'Emerging' },
          { color: '#f59e0b', label: 'Consolidating' },
          { color: '#94a3b8', label: 'Average' },
          { color: '#ef4444', label: 'Weak / Laggard' },
        ].map(l => (
          <div key={l.label} className="flex items-center gap-1.5">
            <div className="w-2.5 h-2.5 rounded-full shrink-0" style={{ background: l.color }} />
            <span className="font-sans text-[10px] text-ink-tertiary">{l.label}</span>
          </div>
        ))}
        <div className="ml-auto font-sans text-[10px] text-ink-tertiary">
          {data.length} stocks · size = avg volume
        </div>
      </div>

      {/* Chart */}
      <div className="px-2 py-4" style={{ height: 480 }}>
        <ResponsiveContainer width="100%" height="100%">
          <ScatterChart margin={{ top: 10, right: 24, bottom: 42, left: 36 }}>

            {/* Quadrant background tints */}
            <ReferenceArea
              x1={0} x2={volMedian} y1={0} y2={yMax}
              fill="#22c55e" fillOpacity={0.04}
              label={quadLabel('tl', 'Quality Uptrend', 'low vol · positive return', '#22c55e')}
            />
            <ReferenceArea
              x1={volMedian} x2={VOL_CAP} y1={0} y2={yMax}
              fill="#f59e0b" fillOpacity={0.04}
              label={quadLabel('tr', 'High Beta', 'high vol · positive return', '#f59e0b')}
            />
            <ReferenceArea
              x1={0} x2={volMedian} y1={yMin} y2={0}
              fill="#94a3b8" fillOpacity={0.04}
              label={quadLabel('bl', 'Quiet Drift', 'low vol · negative return', '#94a3b8')}
            />
            <ReferenceArea
              x1={volMedian} x2={VOL_CAP} y1={yMin} y2={0}
              fill="#ef4444" fillOpacity={0.05}
              label={quadLabel('br', 'Danger Zone', 'high vol · negative return', '#ef4444')}
            />

            <XAxis
              type="number"
              dataKey="x"
              domain={[0, VOL_CAP]}
              tickFormatter={v => `${v.toFixed(0)}%`}
              label={{ value: 'Annualized Volatility % (63-day) →', position: 'insideBottom', offset: -28, fontSize: 10, fill: '#94a3b8' }}
              tick={{ fontSize: 10, fill: '#94a3b8' }}
              tickCount={7}
            />
            <YAxis
              type="number"
              dataKey="y"
              domain={[yMin, yMax]}
              tickFormatter={v => `${v >= 0 ? '+' : ''}${v.toFixed(0)}%`}
              label={{ value: `↑ ${period} Return`, angle: -90, position: 'insideLeft', offset: 14, fontSize: 10, fill: '#94a3b8' }}
              tick={{ fontSize: 10, fill: '#94a3b8' }}
              tickCount={6}
            />
            <ZAxis type="number" dataKey="z" range={[12, 320]} />
            <Tooltip content={<CustomTooltip />} cursor={false} />

            {/* Axis dividers */}
            <ReferenceLine
              y={0}
              stroke="#cbd5e1" strokeDasharray="4 3" strokeWidth={1}
            />
            <ReferenceLine
              x={volMedian}
              stroke="#cbd5e1" strokeDasharray="4 3" strokeWidth={1}
              label={{ value: `${volMedian}% vol`, position: 'insideTopRight', fontSize: 9, fill: '#94a3b8', dy: -4 }}
            />

            <Scatter data={data} onClick={handleClick} cursor="pointer">
              {data.map((entry, i) => (
                <Cell
                  key={`cell-${i}`}
                  fill={entry.color}
                  fillOpacity={0.70}
                  stroke={entry.color}
                  strokeOpacity={0.85}
                  strokeWidth={0.5}
                />
              ))}
            </Scatter>
          </ScatterChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}
