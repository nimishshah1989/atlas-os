'use client'

// frontend/src/components/v6/etfs/PremiumDiscountScatter.tsx
//
// NAV vs market price premium/discount scatter chart.
// X = premium_bps (NAV deviation in basis points)
// Y = log10(adv_20d_inr / 1e7) → ADV in crore on log scale
//
// Zone tints:
//   Green zone: |premium_bps| <= 25 AND adv_20d_inr >= 3e7
//   Red zones: premium_bps > 25 OR premium_bps < -25
//
// Recharts ScatterChart — no SVG raw drawing.
// NULL premium_bps: render at x=0 with grey color (scatter_zone = 'premium_unknown').

import {
  ScatterChart,
  Scatter,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ReferenceLine,
  ReferenceArea,
  ResponsiveContainer,
} from 'recharts'
import type { EtfListV6Row } from '@/lib/queries/v6/etfs'

type TooltipPayloadItem = { payload?: ScatterPoint }
type ScatterTooltipProps = { active?: boolean; payload?: TooltipPayloadItem[] }

// ── Data shaping ──────────────────────────────────────────────────────────────

type ScatterPoint = {
  ticker: string
  x: number          // premium_bps (null → 0)
  y: number          // log10(adv_20d_inr / 1e7) clamped ≥ 0
  action: string | null
  scatter_zone: string | null
  adv_cr: number
  premium_bps: number | null
  etf_category: string | null
}

function toScatterPoints(etfs: EtfListV6Row[]): ScatterPoint[] {
  return etfs
    .filter((e) => e.adv_20d_inr != null && e.adv_20d_inr > 0)
    .map((e) => {
      const adv_cr = (e.adv_20d_inr ?? 0) / 1e7
      const y = adv_cr > 0 ? Math.log10(adv_cr) : 0
      return {
        ticker: e.ticker,
        x: e.premium_bps ?? 0,
        y: Math.max(0, y),
        action: e.action,
        scatter_zone: e.scatter_zone,
        adv_cr,
        premium_bps: e.premium_bps,
        etf_category: e.etf_category,
      }
    })
}

// ── Tooltip ───────────────────────────────────────────────────────────────────

function ScatterTooltipContent({ active, payload }: ScatterTooltipProps) {
  if (!active || !payload?.length) return null
  const pt = payload[0]?.payload
  if (!pt) return null

  return (
    <div className="bg-paper border border-paper-rule rounded-sm p-2.5 shadow-sm text-[11px]">
      <div className="font-mono font-semibold text-ink-primary mb-1">{pt.ticker}</div>
      <div className="text-ink-secondary">
        Premium: {pt.premium_bps != null ? `${pt.premium_bps > 0 ? '+' : ''}${pt.premium_bps.toFixed(0)} bps` : 'N/A'}
      </div>
      <div className="text-ink-secondary">
        ADV: ₹{pt.adv_cr.toFixed(1)} cr
      </div>
      {pt.etf_category && (
        <div className="text-ink-tertiary mt-0.5">{pt.etf_category}</div>
      )}
      {pt.action && (
        <div
          className={`font-mono font-semibold mt-1 ${pt.action === 'BUY' ? 'text-signal-pos' : pt.action === 'AVOID' ? 'text-signal-neg' : 'text-signal-warn'}`}
        >
          {pt.action}
        </div>
      )}
    </div>
  )
}

// ── Y-axis tick (log ADV in Cr) ───────────────────────────────────────────────

function yAxisTickFormatter(value: number): string {
  const cr = Math.pow(10, value)
  if (cr >= 100) return `₹${cr.toFixed(0)}cr`
  if (cr >= 10) return `₹${cr.toFixed(0)}cr`
  if (cr >= 1) return `₹${cr.toFixed(1)}cr`
  return `₹${(cr * 10).toFixed(0)}L`
}

// ── Legend ────────────────────────────────────────────────────────────────────

function ScatterLegend() {
  return (
    <div className="flex flex-wrap gap-4 justify-center text-[11px] mt-2">
      {[
        { color: '#2F6B43', label: 'BUY' },
        { color: '#B8860B', label: 'WATCH' },
        { color: '#B0492C', label: 'AVOID' },
        { color: '#9A8F82', label: 'NAV unknown / low-ADV' },
      ].map(({ color, label }) => (
        <span key={label} className="flex items-center gap-1.5 font-sans text-ink-tertiary">
          <span
            className="inline-block w-2.5 h-2.5 rounded-full"
            style={{ background: color }}
            aria-hidden="true"
          />
          {label}
        </span>
      ))}
    </div>
  )
}

// ── Main component ────────────────────────────────────────────────────────────

export interface PremiumDiscountScatterProps {
  etfs: EtfListV6Row[]
}

export function PremiumDiscountScatter({ etfs }: PremiumDiscountScatterProps) {
  const points = toScatterPoints(etfs)

  // Split by color for separate Scatter series (Recharts doesn't support per-point fill natively)
  const buyPoints  = points.filter((p) => p.action === 'BUY' && p.scatter_zone !== 'low_adv' && p.scatter_zone !== 'premium_unknown')
  const watchPoints = points.filter((p) => p.action === 'WATCH' && p.scatter_zone !== 'low_adv' && p.scatter_zone !== 'premium_unknown')
  const avoidPoints = points.filter((p) => p.action === 'AVOID' && p.scatter_zone !== 'low_adv' && p.scatter_zone !== 'premium_unknown')
  const grayPoints = points.filter((p) => p.scatter_zone === 'low_adv' || p.scatter_zone === 'premium_unknown')

  const hasData = points.length > 0

  if (!hasData) {
    return (
      <div className="h-72 flex items-center justify-center font-sans text-[12px] text-ink-tertiary">
        Premium/discount data not yet available — run iNAV ingest first.
      </div>
    )
  }

  return (
    <div data-testid="premium-discount-scatter">
      <div className="font-sans text-[11px] text-ink-tertiary mb-3">
        Each dot = one ETF. X = premium/discount to NAV (bps). Y = 20d avg ADV on log scale.{' '}
        <strong className="text-ink-secondary">Green zone (±25 bps + high ADV)</strong> is the clean-entry region.
      </div>

      <ResponsiveContainer width="100%" height={340}>
        <ScatterChart margin={{ top: 16, right: 24, bottom: 32, left: 40 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#DDD3BF" strokeOpacity={0.5} />

          {/* Zone tints */}
          <ReferenceArea
            x1={-25}
            x2={25}
            y1={Math.log10(0.3)}
            y2={Math.log10(300)}
            fill="#2F6B43"
            fillOpacity={0.05}
          />
          <ReferenceArea
            x1={-150}
            x2={-25}
            fill="#B0492C"
            fillOpacity={0.04}
          />
          <ReferenceArea
            x1={25}
            x2={150}
            fill="#B0492C"
            fillOpacity={0.04}
          />

          <XAxis
            type="number"
            dataKey="x"
            name="Premium/discount (bps)"
            domain={[-100, 100]}
            tickFormatter={(v: number) => `${v > 0 ? '+' : ''}${v}`}
            label={{
              value: 'Premium / discount to NAV (bps)',
              position: 'insideBottom',
              offset: -18,
              style: { fontSize: 11, fill: '#3D362E', fontWeight: 600 },
            }}
            tick={{ fontSize: 10, fill: '#6B6157', fontFamily: 'JetBrains Mono, monospace' }}
          />
          <YAxis
            type="number"
            dataKey="y"
            name="20d avg ADV (log)"
            domain={[0, Math.log10(200)]}
            tickFormatter={yAxisTickFormatter}
            label={{
              value: '20d avg ADV (log scale)',
              angle: -90,
              position: 'insideLeft',
              offset: -24,
              style: { fontSize: 11, fill: '#3D362E', fontWeight: 600 },
            }}
            tick={{ fontSize: 10, fill: '#6B6157', fontFamily: 'JetBrains Mono, monospace' }}
          />

          {/* Center line at 0 bps */}
          <ReferenceLine
            x={0}
            stroke="#1A1714"
            strokeWidth={0.8}
            label={{ value: '0 bps · NAV-fair', position: 'top', style: { fontSize: 9, fill: '#1A1714', fontWeight: 600 } }}
          />
          {/* ±25 bps threshold lines */}
          <ReferenceLine
            x={25}
            stroke="#9A8F82"
            strokeWidth={0.6}
            strokeDasharray="3 3"
            label={{ value: '+25', position: 'top', style: { fontSize: 9, fill: '#6B6157' } }}
          />
          <ReferenceLine
            x={-25}
            stroke="#9A8F82"
            strokeWidth={0.6}
            strokeDasharray="3 3"
            label={{ value: '−25', position: 'top', style: { fontSize: 9, fill: '#6B6157' } }}
          />

          <Tooltip content={<ScatterTooltipContent />} />

          <Scatter name="BUY" data={buyPoints} fill="#2F6B43" r={5} opacity={0.85} />
          <Scatter name="WATCH" data={watchPoints} fill="#B8860B" r={5} opacity={0.85} />
          <Scatter name="AVOID" data={avoidPoints} fill="#B0492C" r={5} opacity={0.85} />
          <Scatter name="Gray" data={grayPoints} fill="#9A8F82" r={4} opacity={0.7} />
        </ScatterChart>
      </ResponsiveContainer>

      <ScatterLegend />

      {/* Summary line */}
      <div className="mt-3 p-3 bg-paper-soft border border-paper-rule rounded-sm font-sans text-[12px] text-ink-secondary leading-relaxed">
        <strong className="text-ink-primary">
          {buyPoints.filter((p) => Math.abs(p.x) <= 25).length} clean BUYs
        </strong>{' '}
        in the NAV-fair + liquid zone ·{' '}
        <strong className="text-ink-primary">
          {points.filter((p) => Math.abs(p.premium_bps ?? 0) > 25).length} outliers
        </strong>{' '}
        outside ±25 bps ·{' '}
        <strong className="text-ink-primary">
          {grayPoints.filter((p) => p.scatter_zone === 'low_adv').length} low-ADV ETFs
        </strong>{' '}
        below ₹3 cr ADV.
      </div>
    </div>
  )
}

export default PremiumDiscountScatter
