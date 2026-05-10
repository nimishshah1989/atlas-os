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
import { navStateChipValue } from '@/lib/fund-formatters'
import { CHART_COLORS } from '@/lib/chart-colors'

// allow-large: single cohesive component — axes, quadrants, tooltip, legend, filter chips all belong together (mirrors StockBubbleChart pattern)

const RET_CAP = 1.5   // 150% — exclude extreme return outliers
const VOL_CAP = 120   // 120% annualized vol

const PERIOD_RET_KEY: Record<Period, keyof FundRow> = {
  '1M': 'ret_1m',
  '3M': 'ret_3m',
  '6M': 'ret_6m',
  '1Y': 'ret_12m',
}

const BUBBLE_FILTERS: { key: FilterChip; label: string }[] = [
  { key: 'all',         label: 'All' },
  { key: 'recommended', label: 'Recommended' },
  { key: 'hold',        label: 'Hold' },
  { key: 'leader_nav',  label: 'Leader NAV' },
]

const LEGEND = [
  { color: CHART_COLORS.rsLeader,    label: 'Leader NAV' },
  { color: CHART_COLORS.rsStrong,    label: 'Strong NAV' },
  { color: CHART_COLORS.rsEmerging,  label: 'Emerging NAV' },
  { color: CHART_COLORS.rsAverage,   label: 'Average NAV' },
  { color: CHART_COLORS.rsWeak,      label: 'Weak/Laggard NAV' },
  { color: CHART_COLORS.inkTertiary, label: 'Suspended/N/A' },
]

type BubblePoint = {
  x: number               // vol %
  y: number               // ret %
  z: number               // bubble size
  mstarId: string
  schemeName: string
  amc: string
  color: string
  rsPctile: number | null
  recommendation: string | null
}

function navStateColor(navState: string | null): string {
  const chip = navStateChipValue(navState)
  switch (chip) {
    case 'Leader':   return CHART_COLORS.rsLeader
    case 'Strong':   return CHART_COLORS.rsStrong
    case 'Emerging': return CHART_COLORS.rsEmerging
    case 'Average':  return CHART_COLORS.rsAverage
    case 'Weak':
    case 'Laggard':  return CHART_COLORS.rsWeak
    default:         return CHART_COLORS.inkTertiary
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
        <div className="text-ink-secondary">Vol (63D): {d.x.toFixed(0)}%</div>
        <div className="text-ink-secondary">
          RS Pctile: {d.rsPctile != null ? `${(d.rsPctile * 100).toFixed(0)}th` : '—'}
        </div>
        <div className="text-ink-secondary">Recommendation: {d.recommendation ?? '—'}</div>
        <div className="text-ink-tertiary text-[9px] mt-1">Larger bubble = lower drawdown ratio</div>
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
}

export function FundBubbleChart({ funds, period, activeFilter, onFilterChange }: Props) {
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
    return filteredFunds.flatMap(f => {
      const retRaw = f[retKey] != null ? parseFloat(f[retKey] as string) : null
      const volRaw = f.realized_vol_63 != null ? parseFloat(f.realized_vol_63) * 100 : null
      const drRaw  = f.drawdown_ratio_252 != null ? parseFloat(f.drawdown_ratio_252) : null

      if (retRaw == null || volRaw == null) return []
      if (Math.abs(retRaw) > RET_CAP || volRaw > VOL_CAP) return []

      // Guard against zero / negative drawdown_ratio — would produce inf or negative z
      const z = (drRaw != null && drRaw > 0)
        ? Math.max(4, Math.min(800, (1 / drRaw) * 400))
        : 20

      const rsPctileRaw = f.rs_pctile_3m != null ? parseFloat(f.rs_pctile_3m) : null

      return [{
        x: volRaw,
        y: retRaw * 100,
        z,
        mstarId: f.mstar_id,
        schemeName: f.scheme_name,
        amc: f.amc,
        color: navStateColor(f.nav_state),
        rsPctile: rsPctileRaw,
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

  // Dynamic X midpoint — median vol rounded to nearest 5
  const volMedian = useMemo(() => {
    if (data.length === 0) return 35
    const xs = [...data.map(d => d.x)].sort((a, b) => a - b)
    const raw = xs[Math.floor(xs.length / 2)]
    return Math.round(raw / 5) * 5
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
      {/* Header: title + filter chips */}
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

      {/* Description */}
      <div className="px-5 py-2 border-b border-paper-rule/40 bg-paper-rule/5">
        <p className="font-sans text-[11px] text-ink-secondary leading-relaxed">
          X = annualized vol · Y = {period} return · Larger bubble = lower drawdown.
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
          {data.length} funds
        </div>
      </div>

      {/* Chart */}
      <div className="px-2 py-4" style={{ height: 480 }}>
        <ResponsiveContainer width="100%" height="100%">
          <ScatterChart margin={{ top: 10, right: 24, bottom: 42, left: 36 }}>

            {/* Quadrant tints */}
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
              tickFormatter={v => `${(v as number).toFixed(0)}%`}
              label={{ value: 'Annualized Volatility % (63-day) →', position: 'insideBottom', offset: -28, fontSize: 10, fill: '#94a3b8' }}
              tick={{ fontSize: 10, fill: '#94a3b8' }}
              tickCount={7}
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
            <ZAxis type="number" dataKey="z" range={[4, 800]} />
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
