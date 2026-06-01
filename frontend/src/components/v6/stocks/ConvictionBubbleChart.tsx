// frontend/src/components/v6/stocks/ConvictionBubbleChart.tsx
// Page 05 · Conviction landscape bubble chart
// x = RS 3M vs Nifty500 (pp), y = composite_score, size = liquidity_proxy_cr
// color = action (BUY=pos-green, WATCH=warn-amber, AVOID=neg-red, HOLD=teal)
//
// Wraps a Recharts ScatterChart directly (does not reuse BubbleRiskReturnChart
// which uses risk/return axes — different semantics here).
'use client'

import { useMemo, useState, useCallback } from 'react'
import { useRouter } from 'next/navigation'
import {
  ScatterChart,
  Scatter,
  XAxis,
  YAxis,
  ZAxis,
  CartesianGrid,
  Tooltip,
  ReferenceLine,
  ReferenceArea,
  ResponsiveContainer,
} from 'recharts'
import type { LandscapeRow } from '@/lib/queries/v6/stocks-landscape'

// ---------------------------------------------------------------------------
// Color tokens
// ---------------------------------------------------------------------------

export const ACTION_COLOR: Record<string, string> = {
  BUY: 'var(--color-signal-pos)',
  WATCH: 'var(--color-signal-warn)',
  AVOID: 'var(--color-signal-neg)',
}

/** Map an action string to the CSS color var for that action. Exported for tests. */
export function mapAction(action: string | null): string {
  return ACTION_COLOR[action ?? ''] ?? 'var(--color-ink-4)'
}

/** Classify which quadrant a datum falls in. Exported for tests. */
export function quadrant(rs3mPp: number, composite: number): string {
  if (composite >= 0 && rs3mPp >= 0) return 'clean_buy'
  if (composite >= 0 && rs3mPp < 0) return 'contrarian_buy'
  if (composite < 0 && rs3mPp < 0) return 'clean_avoid'
  return 'rs_holding_composite_down'
}

const ACTION_OPACITY: Record<string, number> = {
  BUY: 0.80,
  WATCH: 0.65,
  AVOID: 0.80,
}

// ---------------------------------------------------------------------------
// Data shaping
// ---------------------------------------------------------------------------

type BubbleDatum = {
  id: string
  symbol: string
  sector: string
  capTier: string
  action: string
  x: number  // rs_3m_nifty500 * 100  (pp)
  y: number  // composite_score
  z: number  // liquidity bucket for ZAxis
  color: string
  opacity: number
}

export function buildDatum(row: LandscapeRow): BubbleDatum | null {
  const x = row.rs_3m_nifty500 != null ? parseFloat(row.rs_3m_nifty500) * 100 : null
  const y = row.composite_score != null ? parseFloat(row.composite_score) : null
  if (x === null || y === null || isNaN(x) || isNaN(y)) return null

  // Use raw liquidity (crore) directly — ZAxis range={[20, 480]} handles scaling.
  // Clamp to [1, 1_000_000] to prevent extreme outliers from dominating the axis.
  const liq = row.liquidity_proxy_cr != null ? Math.max(1, parseFloat(row.liquidity_proxy_cr)) : 1
  const z = Math.min(liq, 1_000_000)

  const action = row.action ?? 'WATCH'

  return {
    id: row.instrument_id,
    symbol: row.symbol,
    sector: row.sector ?? '—',
    capTier: row.cap_tier,
    action,
    x,
    y,
    z,
    color: ACTION_COLOR[action] ?? 'var(--color-ink-4)',
    opacity: ACTION_OPACITY[action] ?? 0.65,
  }
}

// ---------------------------------------------------------------------------
// Custom dot
// ---------------------------------------------------------------------------

type DotProps = {
  cx?: number
  cy?: number
  r?: number
  payload?: BubbleDatum
  onClick?: (symbol: string) => void
}

function BubbleDot({ cx = 0, cy = 0, r = 6, payload, onClick }: DotProps) {
  if (!payload) return null
  return (
    <circle
      cx={cx}
      cy={cy}
      r={r}
      fill={payload.color}
      fillOpacity={payload.opacity}
      stroke={payload.color}
      strokeWidth={0.5}
      style={{ cursor: 'pointer' }}
      data-action={payload.action}
      data-symbol={payload.symbol}
      aria-label={`${payload.symbol}: RS3M ${payload.x.toFixed(1)}pp, composite ${payload.y.toFixed(2)}, action ${payload.action}`}
      onClick={() => onClick?.(payload.symbol)}
    />
  )
}

// ---------------------------------------------------------------------------
// Custom tooltip
// ---------------------------------------------------------------------------

type TipEntry = {
  payload?: BubbleDatum
}

function BubbleTip({ active, payload }: { active?: boolean; payload?: TipEntry[] }) {
  if (!active || !payload?.length) return null
  const d = payload[0].payload
  if (!d) return null
  return (
    <div className="bg-paper border border-paper-rule rounded-sm shadow-sm px-3 py-2 font-sans text-[11px] text-ink-primary min-w-[200px]">
      <div className="font-semibold text-[12px] mb-1 font-mono">{d.symbol}</div>
      <div className="grid gap-0.5 text-ink-tertiary">
        <div>Sector: <span className="text-ink-primary">{d.sector}</span></div>
        <div>Cap: <span className="text-ink-primary">{d.capTier}</span></div>
        <div>
          RS 3M:{' '}
          <span style={{ color: d.x >= 0 ? 'var(--color-signal-pos)' : 'var(--color-signal-neg)' }}>
            {d.x >= 0 ? '+' : ''}{d.x.toFixed(1)}pp
          </span>
        </div>
        <div>
          Composite:{' '}
          <span style={{ color: d.y >= 4 ? 'var(--color-signal-pos)' : d.y <= -4 ? 'var(--color-signal-neg)' : 'var(--color-signal-warn)' }}>
            {d.y >= 0 ? '+' : ''}{d.y.toFixed(2)}
          </span>
        </div>
        <div>
          Action:{' '}
          <span style={{ color: ACTION_COLOR[d.action] ?? 'var(--color-ink-4)' }} className="font-semibold">
            {d.action}
          </span>
        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

type Filter = 'all' | 'buy' | 'large'

const FILTER_OPTIONS: { key: Filter; label: string }[] = [
  { key: 'all',   label: 'All' },
  { key: 'buy',   label: 'BUY only' },
  { key: 'large', label: 'Large only' },
]

export function ConvictionBubbleChart({ data }: { data: LandscapeRow[] }) {
  const router = useRouter()
  const [filter, setFilter] = useState<Filter>('all')

  const handleDotClick = useCallback((symbol: string) => {
    router.push(`/stocks/${encodeURIComponent(symbol)}`)
  }, [router])

  const chartData = useMemo(() => {
    const filtered = data.filter(row => {
      if (filter === 'buy') return row.action === 'BUY'
      if (filter === 'large') return row.cap_tier === 'Large'
      return true
    })
    return filtered.map(buildDatum).filter((d): d is BubbleDatum => d !== null)
  }, [data, filter])

  const counts = useMemo(() => ({
    buy: chartData.filter(d => d.action === 'BUY').length,
    watch: chartData.filter(d => d.action === 'WATCH').length,
    avoid: chartData.filter(d => d.action === 'AVOID').length,
  }), [chartData])

  return (
    <div className="bg-paper border border-paper-rule rounded-sm p-5">
      {/* Header */}
      <div className="flex items-baseline justify-between mb-3">
        <div className="font-serif text-[18px] text-ink-primary">
          RS × Composite · bubble = liquidity · colour = action
        </div>
        <div className="flex gap-[6px] items-center">
          {FILTER_OPTIONS.map(opt => (
            <button
              key={opt.key}
              type="button"
              onClick={() => setFilter(opt.key)}
              className={`px-[10px] py-[4px] text-[11px] border rounded-sm font-medium transition-colors ${
                filter === opt.key
                  ? 'bg-accent text-paper border-accent'
                  : 'bg-paper text-ink-tertiary border-paper-rule hover:text-ink-secondary'
              }`}
            >
              {opt.label}
            </button>
          ))}
        </div>
      </div>

      {/* Legend */}
      <div className="flex items-center gap-4 mb-3 flex-wrap">
        {(['BUY', 'WATCH', 'AVOID'] as const).map(a => (
          <div key={a} className="flex items-center gap-1.5">
            <div
              className="w-2.5 h-2.5 rounded-full shrink-0"
              style={{ background: ACTION_COLOR[a] }}
            />
            <span className="font-sans text-[10px] text-ink-tertiary">
              {a} ({a === 'BUY' ? counts.buy : a === 'WATCH' ? counts.watch : counts.avoid})
            </span>
          </div>
        ))}
        <span className="font-sans text-[10px] text-ink-tertiary ml-auto">
          {chartData.length} instruments shown
        </span>
      </div>

      {/* Quadrant labels overlay — positioned relative to chart area */}
      <div className="relative" style={{ height: 430 }}>
        <div className="absolute top-2 left-12 text-[10px] font-semibold tracking-[0.16em] uppercase text-teal pointer-events-none z-10">
          CONTRARIAN BUY
        </div>
        <div className="absolute top-2 right-4 text-[10px] font-semibold tracking-[0.16em] uppercase text-signal-pos pointer-events-none z-10">
          CLEAN BUY ↗
        </div>
        <div className="absolute bottom-10 left-12 text-[10px] font-semibold tracking-[0.16em] uppercase text-signal-neg pointer-events-none z-10">
          CLEAN AVOID ↙
        </div>
        <div className="absolute bottom-10 right-4 text-[10px] font-semibold tracking-[0.16em] uppercase text-signal-warn pointer-events-none z-10 text-right">
          RS HOLDING, COMPOSITE DOWN
        </div>

        <ResponsiveContainer width="100%" height={430}>
          <ScatterChart margin={{ top: 20, right: 40, bottom: 40, left: 40 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--color-ink-rule)" opacity={0.4} />
            {/* Quadrant tint backgrounds */}
            <ReferenceArea x2={0} y1={0} fill="var(--color-teal)" fillOpacity={0.04} />
            <ReferenceArea x1={0} y1={0} fill="var(--color-signal-pos)" fillOpacity={0.06} />
            <ReferenceArea x2={0} y2={0} fill="var(--color-signal-neg)" fillOpacity={0.06} />
            <ReferenceArea x1={0} y2={0} fill="var(--color-signal-warn)" fillOpacity={0.04} />
            <XAxis
              dataKey="x"
              type="number"
              name="RS 3M (pp)"
              domain={['auto', 'auto']}
              tickFormatter={(v: number) => `${v >= 0 ? '+' : ''}${v.toFixed(0)}`}
              label={{
                value: 'RS 3M vs Nifty500 (pp)',
                position: 'insideBottom',
                offset: -28,
                fontSize: 11,
                fill: 'var(--color-ink-secondary)',
                fontWeight: 600,
              }}
              tick={{ fontSize: 9, fill: 'var(--color-ink-tertiary)', fontFamily: 'JetBrains Mono' }}
            />
            <YAxis
              dataKey="y"
              type="number"
              name="Composite"
              domain={['auto', 'auto']}
              tickFormatter={(v: number) => `${v >= 0 ? '+' : ''}${v.toFixed(0)}`}
              label={{
                value: 'Composite',
                angle: -90,
                position: 'insideLeft',
                offset: 20,
                fontSize: 11,
                fill: 'var(--color-ink-secondary)',
                fontWeight: 600,
              }}
              tick={{ fontSize: 9, fill: 'var(--color-ink-tertiary)', fontFamily: 'JetBrains Mono' }}
            />
            <ZAxis dataKey="z" range={[20, 480]} name="Liquidity (₹ cr)" />
            {/* Quadrant dividers at x=0, y=0 */}
            <ReferenceLine x={0} stroke="var(--color-ink-primary)" strokeWidth={0.7} />
            <ReferenceLine y={0} stroke="var(--color-ink-primary)" strokeWidth={0.7} />
            <Tooltip
              content={<BubbleTip />}
              cursor={{ strokeDasharray: '3 3', stroke: 'var(--color-ink-4)' }}
            />
            <Scatter
              data={chartData}
              isAnimationActive={false}
              shape={(props: DotProps) => <BubbleDot {...props} onClick={handleDotClick} />}
            />
          </ScatterChart>
        </ResponsiveContainer>
      </div>

      {/* How to read */}
      <div className="mt-[10px] pt-2 border-t border-paper-rule font-sans text-[12px] text-ink-tertiary leading-relaxed">
        <strong className="text-ink-secondary">How to read this:</strong> Top-right (positive RS + positive composite) is the{' '}
        <span className="text-signal-pos font-medium">clean-BUY</span> quadrant. Top-left captures contrarian buys (composite positive, RS still negative).
        Bottom-left is the <span className="text-signal-neg font-medium">active avoid</span> zone.
      </div>
    </div>
  )
}
