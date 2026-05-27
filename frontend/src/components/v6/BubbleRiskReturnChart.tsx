// frontend/src/components/v6/BubbleRiskReturnChart.tsx
// Recharts ScatterChart — risk-X, return-Y, log-size bubble, Atlas-state color.
// v2 refs: components/stocks/StockBubbleChart.tsx, components/etfs/ETFBubbleChart.tsx
'use client'

import { useMemo } from 'react'
import {
  ScatterChart, Scatter, XAxis, YAxis, ZAxis,
  CartesianGrid, Tooltip, ResponsiveContainer, ReferenceLine,
} from 'recharts'
import { toNumber } from '@/lib/v6/decimal'

// ── Public types ──────────────────────────────────────────────────────────────

export type BubbleDatum = {
  id: string
  label: string
  risk: string   // stringified Decimal — volatility or beta
  ret: string    // stringified Decimal — return %
  size: string   // stringified Decimal — AUM / market cap / log-volume
  state: 'POSITIVE' | 'NEUTRAL' | 'NEGATIVE'
}

export interface BubbleRiskReturnChartProps {
  data: BubbleDatum[]
  xLabel?: string
  yLabel?: string
  sizeLabel?: string
  className?: string
  highlightId?: string
}

// ── Color tokens — hex matches globals.css signal-* CSS variables ────────────

const STATE_COLOR: Record<BubbleDatum['state'], string> = {
  POSITIVE: '#2F6B43',  // --color-signal-pos
  NEUTRAL:  '#B8860B',  // --color-signal-warn
  NEGATIVE: '#B0492C',  // --color-signal-neg
}

// ── Log-size helper — maps to ZAxis area range [48, 1024] (≈7–32px radius) ──

function logSize(sizeStr: string): number {
  const n = toNumber(sizeStr)
  if (n === null || n <= 0) return 48
  const normalised = Math.min(1, Math.log10(Math.max(1, n)) / 8)
  return Math.round(48 + normalised * 976)
}

// ── Custom dot — carries aria-label + data-* attrs (DOM-testable in jsdom) ──

type DotProps = {
  cx?: number; cy?: number; r?: number
  payload?: BubbleDatum & { _risk: number; _ret: number; _size: number }
  highlightId?: string
}

function BubbleDot({ cx = 0, cy = 0, r = 8, payload, highlightId }: DotProps) {
  if (!payload) return null
  const color = STATE_COLOR[payload.state]
  const hi = payload.id === highlightId
  return (
    <circle
      cx={cx} cy={cy} r={r}
      fill={color} fillOpacity={0.7}
      stroke={hi ? '#1e293b' : color} strokeWidth={hi ? 2 : 0.5}
      data-state={payload.state} data-id={payload.id}
      data-highlighted={hi ? 'true' : undefined}
      aria-label={`${payload.label}: risk ${payload.risk}, return ${payload.ret}, size ${payload.size}, state ${payload.state}`}
    />
  )
}

// ── Tooltip ───────────────────────────────────────────────────────────────────

type TipPayload = { payload?: BubbleDatum & { _risk: number; _ret: number } }
function BubbleTip({ active, payload }: { active?: boolean; payload?: TipPayload[] }) {
  if (!active || !payload?.length) return null
  const d = payload[0].payload
  if (!d) return null
  const retN = toNumber(d.ret) ?? 0
  return (
    <div className="bg-paper border border-paper-rule rounded-sm shadow-sm px-3 py-2 font-sans text-[11px] text-ink-primary" style={{ minWidth: 200, maxWidth: 280 }}>
      <div className="font-semibold text-[12px] mb-1">{d.label}</div>
      <div className="border-t border-paper-rule/40 pt-1.5 grid gap-0.5">
        <div className="text-ink-tertiary">Risk: <span className="text-ink-primary">{toNumber(d.risk)?.toFixed(2) ?? '—'}</span></div>
        <div className="text-ink-tertiary">Return: <span style={{ color: retN >= 0 ? '#2F6B43' : '#B0492C' }}>{retN >= 0 ? '+' : ''}{retN.toFixed(2)}%</span></div>
        <div className="text-ink-tertiary">State: <span className="text-ink-primary">{d.state}</span></div>
      </div>
    </div>
  )
}

// ── Quadrant corner labels ────────────────────────────────────────────────────

const QUADS = [
  { x: '5%',  y: '8%',  anchor: 'start' as const, label: 'SWEET SPOT',   color: '#2F6B43' },
  { x: '95%', y: '8%',  anchor: 'end'   as const, label: 'GROWTH',       color: '#B8860B' },
  { x: '5%',  y: '94%', anchor: 'start' as const, label: 'UNDERPERFORM', color: '#64748b' },
  { x: '95%', y: '94%', anchor: 'end'   as const, label: 'TRAP',         color: '#B0492C' },
]

// ── Main component ────────────────────────────────────────────────────────────

export function BubbleRiskReturnChart({
  data, xLabel = 'Risk (σ)', yLabel = 'Return (%)', sizeLabel = 'Log size', className = '', highlightId,
}: BubbleRiskReturnChartProps) {
  // Hooks run unconditionally (rules-of-hooks)
  const chartData = useMemo(
    () => data.map(d => ({ ...d, _risk: toNumber(d.risk) ?? 0, _ret: toNumber(d.ret) ?? 0, _size: logSize(d.size) })),
    [data],
  )
  const midRisk = useMemo(() => {
    if (!chartData.length) return 0
    const v = chartData.map(d => d._risk).sort((a, b) => a - b)
    return v[Math.floor(v.length / 2)] ?? 0
  }, [chartData])
  const midRet = useMemo(() => {
    if (!chartData.length) return 0
    const v = chartData.map(d => d._ret).sort((a, b) => a - b)
    return v[Math.floor(v.length / 2)] ?? 0
  }, [chartData])

  if (data.length === 0) {
    return (
      <div className={`flex items-center justify-center h-64 bg-paper border border-paper-rule rounded-sm text-ink-tertiary font-sans text-[13px] ${className}`} role="img" aria-label="Bubble chart — no data available">
        No data available
      </div>
    )
  }

  return (
    <div className={`bg-paper border border-paper-rule rounded-sm ${className}`}>
      {/* Hidden roster: each datum as a list item — DOM-accessible in jsdom for testing */}
      <ul aria-hidden data-testid="bubble-roster" style={{ display: 'none' }}>
        {data.map(d => (
          <li key={d.id} data-id={d.id} data-state={d.state}
            aria-label={`${d.label}: risk ${d.risk}, return ${d.ret}, size ${d.size}, state ${d.state}`}
          />
        ))}
      </ul>

      {/* Legend */}
      <div className="px-4 py-2 border-b border-paper-rule/40 flex flex-wrap items-center gap-3">
        {(['POSITIVE', 'NEUTRAL', 'NEGATIVE'] as const).map(s => (
          <div key={s} className="flex items-center gap-1.5">
            <div className="w-2.5 h-2.5 rounded-full shrink-0" style={{ background: STATE_COLOR[s] }} />
            <span className="font-sans text-[10px] text-ink-tertiary capitalize">{s.toLowerCase()}</span>
          </div>
        ))}
        <div className="ml-auto font-sans text-[10px] text-ink-tertiary">
          {`Bubble size = ${sizeLabel} · ${data.length} instruments`}
        </div>
      </div>

      {/* Chart + quadrant labels */}
      <div className="relative px-4 pt-3 pb-1">
        <svg className="absolute inset-x-4 top-3 pointer-events-none" style={{ height: 40, zIndex: 1 }} aria-hidden>
          {QUADS.map(q => (
            <text key={q.label} x={q.x} y={q.y} textAnchor={q.anchor} fontSize={8} fontWeight={700} letterSpacing={1.2} fill={q.color} opacity={0.55}>{q.label}</text>
          ))}
        </svg>
        <ResponsiveContainer width="100%" height={380}>
          <ScatterChart margin={{ top: 20, right: 32, bottom: 40, left: 32 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" opacity={0.5} />
            <XAxis dataKey="_risk" type="number" name={xLabel}
              tickFormatter={(v: number) => v.toFixed(2)}
              label={{ value: xLabel, position: 'insideBottom', offset: -28, fontSize: 10, fill: '#64748b' }}
              tick={{ fontSize: 9, fill: '#94a3b8' }}
            />
            <YAxis dataKey="_ret" type="number" name={yLabel}
              tickFormatter={(v: number) => `${v >= 0 ? '+' : ''}${v.toFixed(0)}%`}
              label={{ value: yLabel, angle: -90, position: 'insideLeft', offset: 16, fontSize: 10, fill: '#64748b' }}
              tick={{ fontSize: 9, fill: '#94a3b8' }}
            />
            <ZAxis dataKey="_size" range={[48, 1024]} name={sizeLabel} />
            <ReferenceLine x={midRisk} stroke="#94a3b8" strokeDasharray="4 3" strokeWidth={1} />
            <ReferenceLine y={midRet}  stroke="#94a3b8" strokeDasharray="4 3" strokeWidth={1} />
            <Tooltip content={<BubbleTip />} cursor={{ strokeDasharray: '3 3' }} />
            <Scatter data={chartData} isAnimationActive={false}
              shape={(props: DotProps) => <BubbleDot {...props} highlightId={highlightId} />}
            />
          </ScatterChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}
