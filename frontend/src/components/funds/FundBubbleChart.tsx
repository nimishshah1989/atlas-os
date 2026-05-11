'use client'
import { useMemo, useCallback } from 'react'
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
import type { FundRow } from '@/lib/queries/funds'
import type { Period } from '@/lib/url-params'
import type { FilterChip } from '@/components/funds/FundPageClient'
import { CHART_COLORS } from '@/lib/chart-colors'

// allow-large: single cohesive component — axes, quadrants, tooltip, legend, filter chips all belong together (mirrors StockBubbleChart pattern)

const RET_CAP = 1.5   // 150% — exclude extreme return outliers

const PERIOD_RET_KEY: Record<Period, keyof FundRow> = {
  '1M': 'ret_1m',
  '3M': 'ret_3m',
  '6M': 'ret_6m',
  '1Y': 'ret_12m',
}

const PERIOD_PCTILE_KEY: Record<Period, keyof FundRow> = {
  '1M': 'rs_pctile_1m',
  '3M': 'rs_pctile_3m',
  '6M': 'rs_pctile_6m',
  '1Y': 'rs_pctile_6m', // 6M is best available proxy for 1Y
}

const BUBBLE_FILTERS: { key: FilterChip; label: string }[] = [
  { key: 'all',         label: 'All' },
  { key: 'recommended', label: 'Recommended' },
  { key: 'hold',        label: 'Hold' },
  { key: 'leader_nav',  label: 'Leader NAV' },
]

const LEGEND = [
  { color: CHART_COLORS.rsLeader,    label: 'Recommended' },
  { color: '#B8860B',                label: 'Hold' },
  { color: CHART_COLORS.rsWeak,      label: 'Reduce / Exit' },
  { color: CHART_COLORS.inkTertiary, label: 'No Rating' },
]

type BubblePoint = {
  x: number               // RS percentile (0–100)
  y: number               // period return %
  z: number               // bubble size (vol)
  mstarId: string
  schemeName: string
  amc: string
  color: string
  vol: number | null
  rsPctile: number | null
  recommendation: string | null
}

function recColor(recommendation: string | null): string {
  switch (recommendation) {
    case 'Recommended': return CHART_COLORS.rsLeader
    case 'Hold':        return '#B8860B'
    case 'Reduce':      return CHART_COLORS.rsWeak
    case 'Exit':        return CHART_COLORS.rsWeak
    default:            return CHART_COLORS.inkTertiary
  }
}

function CustomTooltip({
  active,
  payload,
}: {
  active?: boolean
  payload?: Array<{ payload: BubblePoint }>
}) {
  if (!active || !payload?.length) return null
  const d = payload[0].payload
  return (
    <div className="bg-paper border border-paper-rule rounded-sm shadow-md px-3 py-2 font-sans text-xs max-w-[240px]">
      <div className="font-semibold text-ink-primary truncate">{d.schemeName}</div>
      <div className="text-ink-tertiary text-[10px] mb-1 truncate">{d.amc}</div>
      <div className="space-y-0.5 border-t border-paper-rule/40 pt-1.5">
        <div>
          Return:{' '}
          <span className={d.y >= 0 ? 'text-signal-pos font-medium' : 'text-signal-neg font-medium'}>
            {d.y >= 0 ? '+' : ''}{d.y.toFixed(1)}%
          </span>
        </div>
        <div className="text-ink-secondary">
          RS Pctile: {d.rsPctile != null ? `${d.rsPctile.toFixed(0)}th` : '—'}
        </div>
        <div className="text-ink-secondary">
          Vol (63D): {d.vol != null ? `${d.vol.toFixed(0)}%` : '—'}
        </div>
        <div className="text-ink-secondary">Recommendation: {d.recommendation ?? '—'}</div>
        <div className="text-ink-tertiary text-[9px] mt-1">Larger bubble = higher volatility</div>
      </div>
    </div>
  )
}

type QuadrantPos = 'tl' | 'tr' | 'bl' | 'br'

function quadLabel(pos: QuadrantPos, text: string, sub: string, color: string) {
  return function QuadLabel({
    viewBox,
  }: {
    viewBox?: { x: number; y: number; width: number; height: number }
  }) {
    if (!viewBox) return null
    const { x, y, width, height } = viewBox
    const isRight = pos === 'tr' || pos === 'br'
    const isBottom = pos === 'bl' || pos === 'br'
    const tx = isRight ? x + width - 10 : x + 10
    const ty1 = isBottom ? y + height - 18 : y + 14
    const ty2 = isBottom ? y + height - 6 : y + 24
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

type Props = {
  funds: FundRow[]
  period: Period
  activeFilter: FilterChip
  onFilterChange: (f: FilterChip) => void
  onPeriodChange: (p: Period) => void
}

export function FundBubbleChart({ funds, period, activeFilter, onFilterChange, onPeriodChange }: Props) {
  const router = useRouter()

  // Apply bubble-level filter (subset of FundPageClient's full filter logic)
  const filteredFunds = useMemo(() => {
    if (activeFilter === 'all')         return funds
    if (activeFilter === 'recommended') return funds.filter(f => f.recommendation === 'Recommended')
    if (activeFilter === 'hold')        return funds.filter(f => f.recommendation === 'Hold')
    if (activeFilter === 'leader_nav')  return funds.filter(f => f.nav_state === 'Leader NAV')
    return funds
  }, [funds, activeFilter])

  const data = useMemo<BubblePoint[]>(() => {
    const retKey = PERIOD_RET_KEY[period]
    const pctileKey = PERIOD_PCTILE_KEY[period]
    return filteredFunds.flatMap(f => {
      const retRaw = f[retKey] != null ? parseFloat(f[retKey] as string) : null
      const rsPctileRaw = f[pctileKey] != null ? parseFloat(f[pctileKey] as string) : null

      if (retRaw == null || rsPctileRaw == null) return []
      if (Math.abs(retRaw) > RET_CAP) return []

      const volRaw = f.realized_vol_63 != null ? parseFloat(f.realized_vol_63) * 100 : null
      // Bubble size = volatility. Clamp so all bubbles are visible.
      const z = volRaw != null ? Math.max(10, Math.min(500, volRaw * 8)) : 30

      return [{
        x: rsPctileRaw * 100,   // RS percentile 0–100
        y: retRaw * 100,         // return %
        z,
        mstarId: f.mstar_id,
        schemeName: f.scheme_name,
        amc: f.amc,
        color: recColor(f.recommendation),
        vol: volRaw,
        rsPctile: rsPctileRaw * 100,
        recommendation: f.recommendation,
      }]
    })
  }, [filteredFunds, period])

  // Dynamic Y domain — pad 15%, clamp to [-75, 150]
  const [yMin, yMax] = useMemo(() => {
    if (data.length === 0) return [-50, 80]
    const ys = data.map(d => d.y)
    const lo = Math.min(...ys), hi = Math.max(...ys)
    const pad = Math.max((hi - lo) * 0.15, 8)
    return [
      Math.max(-75, Math.floor((lo - pad) / 10) * 10),
      Math.min(150, Math.ceil((hi + pad) / 10) * 10),
    ]
  }, [data])

  const handleClick = useCallback((point: { payload?: BubblePoint }) => {
    if (point?.payload?.mstarId)
      router.push(`/funds/${point.payload.mstarId}`)
  }, [router])

  if (data.length === 0) {
    return (
      <div className="border border-paper-rule rounded-sm bg-paper">
        {/* Header */}
        <div className="px-5 py-3 border-b border-paper-rule flex flex-wrap items-center gap-4">
          <span className="font-sans text-[10px] font-semibold text-ink-tertiary uppercase tracking-wider">
            Fund Map
          </span>
          <div className="flex gap-1">
            {BUBBLE_FILTERS.map(f => (
              <button key={f.key} type="button" onClick={() => onFilterChange(f.key)}
                className={`px-2 py-0.5 rounded-sm font-sans text-[11px] font-medium transition-colors ${
                  activeFilter === f.key
                    ? 'bg-ink-secondary text-paper'
                    : 'bg-paper-rule/20 text-ink-secondary hover:bg-paper-rule/40'
                }`}>
                {f.label}
              </button>
            ))}
          </div>
        </div>
        <div className="flex items-center justify-center" style={{ height: 480 }}>
          <p className="font-sans text-sm text-ink-tertiary">No funds to display for this filter.</p>
        </div>
      </div>
    )
  }

  return (
    <div className="border border-paper-rule rounded-sm bg-paper">
      {/* Header: title + period selector + filter chips */}
      <div className="px-5 py-3 border-b border-paper-rule flex flex-wrap items-center gap-4">
        <span className="font-sans text-[10px] font-semibold text-ink-tertiary uppercase tracking-wider">
          Fund Map
        </span>
        {/* Period selector — controls Y-axis return + bubble size (RS pctile) */}
        <div className="flex items-center gap-0.5 border border-paper-rule rounded-sm overflow-hidden">
          {(['1M', '3M', '6M', '1Y'] as Period[]).map(p => (
            <button key={p} type="button" onClick={() => onPeriodChange(p)}
              className={`px-2.5 py-0.5 font-sans text-[11px] font-medium transition-colors ${
                period === p
                  ? 'bg-teal text-white'
                  : 'text-ink-secondary hover:bg-paper-rule/30'
              }`}>
              {p}
            </button>
          ))}
        </div>
        <div className="flex gap-1">
          {BUBBLE_FILTERS.map(f => (
            <button key={f.key} type="button" onClick={() => onFilterChange(f.key)}
              className={`px-2 py-0.5 rounded-sm font-sans text-[11px] font-medium transition-colors ${
                activeFilter === f.key
                  ? 'bg-ink-secondary text-paper'
                  : 'bg-paper-rule/20 text-ink-secondary hover:bg-paper-rule/40'
              }`}>
              {f.label}
            </button>
          ))}
        </div>
      </div>

      {/* Description */}
      <div className="px-5 py-2 border-b border-paper-rule/40 bg-paper-rule/5">
        <p className="font-sans text-[11px] text-ink-secondary leading-relaxed">
          X = {period} RS percentile vs universe · Y = {period} return · Bubble size = volatility · Color = recommendation.
          Click bubble for deep-dive.
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
          Bubble size = volatility · {data.length} funds
        </div>
      </div>

      {/* Chart */}
      <div className="px-2 py-4" style={{ height: 480 }}>
        <ResponsiveContainer width="100%" height="100%">
          <ScatterChart margin={{ top: 10, right: 24, bottom: 42, left: 36 }}>

            {/* Quadrant tints — split at RS pctile 50 and return 0 */}
            <ReferenceArea
              x1={50} x2={100} y1={0} y2={yMax}
              fill="#22c55e" fillOpacity={0.04}
              label={quadLabel('tr', 'Leaders', 'high RS · positive return', '#22c55e')}
            />
            <ReferenceArea
              x1={0} x2={50} y1={0} y2={yMax}
              fill="#94a3b8" fillOpacity={0.04}
              label={quadLabel('tl', 'Recovering', 'low RS · positive return', '#94a3b8')}
            />
            <ReferenceArea
              x1={50} x2={100} y1={yMin} y2={0}
              fill="#f59e0b" fillOpacity={0.04}
              label={quadLabel('br', 'Fading', 'high RS · negative return', '#f59e0b')}
            />
            <ReferenceArea
              x1={0} x2={50} y1={yMin} y2={0}
              fill="#ef4444" fillOpacity={0.05}
              label={quadLabel('bl', 'Laggards', 'low RS · negative return', '#ef4444')}
            />

            <XAxis
              type="number"
              dataKey="x"
              domain={[0, 100]}
              tickFormatter={v => `${(v as number).toFixed(0)}th`}
              label={{ value: `${period} RS Percentile vs Universe →`, position: 'insideBottom', offset: -28, fontSize: 10, fill: '#94a3b8' }}
              tick={{ fontSize: 10, fill: '#94a3b8' }}
              ticks={[0, 25, 50, 75, 100]}
            />
            <YAxis
              type="number"
              dataKey="y"
              domain={[yMin, yMax]}
              tickFormatter={v => `${(v as number) >= 0 ? '+' : ''}${(v as number).toFixed(0)}%`}
              label={{ value: `↑ ${period} Return`, angle: -90, position: 'insideLeft', offset: 14, fontSize: 10, fill: '#94a3b8' }}
              tick={{ fontSize: 10, fill: '#94a3b8' }}
              tickCount={6}
            />
            <ZAxis type="number" dataKey="z" range={[4, 600]} />
            <Tooltip content={<CustomTooltip />} cursor={false} />

            {/* Axis dividers */}
            <ReferenceLine
              y={0}
              stroke="#cbd5e1" strokeDasharray="4 3" strokeWidth={1}
            />
            <ReferenceLine
              x={50}
              stroke="#cbd5e1" strokeDasharray="4 3" strokeWidth={1}
              label={{ value: '50th pctile', position: 'insideTopRight', fontSize: 9, fill: '#94a3b8', dy: -4 }}
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
