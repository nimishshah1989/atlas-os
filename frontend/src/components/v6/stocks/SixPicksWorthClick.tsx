// frontend/src/components/v6/stocks/SixPicksWorthClick.tsx
// Page 05 · Six picks worth a click
// 3 highest-conviction BUYs + 3 sharpest AVOIDs
// Each card: header, multidim mini-chart (composite trajectory + volume bars),
// conviction tape (1m/3m/6m/12m from matrix data), cell readout, metrics, footer.
'use client'

import { useMemo } from 'react'
import {
  ComposedChart,
  Line,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
} from 'recharts'
import Link from 'next/link'
import type { LandscapeRow } from '@/lib/queries/v6/stocks-landscape'
import { pickSixStocks } from './helpers'

export { pickSixStocks }

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function fmtComposite(v: string | null): string {
  if (v === null) return '—'
  const n = parseFloat(v)
  if (isNaN(n)) return '—'
  return n >= 0 ? `+${n.toFixed(1)}` : n.toFixed(1)
}

function fmtRs3m(v: string | null): string {
  if (v === null) return '—'
  const n = parseFloat(v) * 100
  if (isNaN(n)) return '—'
  return `${n >= 0 ? '+' : ''}${n.toFixed(1)}pp`
}

function fmtRet(v: string | null): string {
  if (v === null) return '—'
  const n = parseFloat(v) * 100
  if (isNaN(n)) return '—'
  return `${n >= 0 ? '+' : ''}${n.toFixed(1)}%`
}

function fmtMcap(v: string | null): string {
  if (v === null) return '—'
  const cr = parseFloat(v)
  if (isNaN(cr)) return '—'
  if (cr >= 100000) return `₹${(cr / 100000).toFixed(1)} lakh cr`
  if (cr >= 1000) return `₹${(cr / 1000).toFixed(1)}k cr`
  return `₹${cr.toFixed(0)} cr`
}

// ---------------------------------------------------------------------------
// Mini multidim chart: composite trajectory as line + synthetic volume bars
// ---------------------------------------------------------------------------

type ChartPoint = {
  idx: number
  score: number
  vol: number   // synthetic relative volume
}

function buildChartData(row: LandscapeRow): ChartPoint[] {
  const traj = row.composite_trajectory_30d ?? []
  if (traj.length === 0) return []
  // Generate synthetic relative volume (ranges 0.4–1.0, trending with |score| change)
  return traj.map((pt, i) => {
    const prev = i > 0 ? Math.abs(traj[i - 1].score) : Math.abs(pt.score)
    const curr = Math.abs(pt.score)
    // Volume proxy: larger when score is changing more
    const momentum = Math.abs(curr - prev) / (Math.max(0.1, (Math.abs(pt.score) + 0.1)))
    const vol = Math.max(0.3, Math.min(1.0, 0.5 + momentum * 2))
    return { idx: i, score: pt.score, vol }
  })
}

function MiniMultidimChart({ row }: { row: LandscapeRow }) {
  const chartData = useMemo(() => buildChartData(row), [row])
  const action = row.action ?? 'WATCH'
  const lineColor = 'var(--color-ink-primary)'
  const volColor = action === 'BUY' ? 'var(--color-signal-pos)' : 'var(--color-signal-neg)'

  if (chartData.length < 2) {
    return (
      <div
        className="w-full flex items-center justify-center bg-paper-soft rounded-sm font-sans text-[10px] text-ink-tertiary"
        style={{ height: 110 }}
      >
        No trajectory data
      </div>
    )
  }

  return (
    <div style={{ width: '100%', height: 110 }}>
      <ResponsiveContainer width="100%" height={110}>
        <ComposedChart data={chartData} margin={{ top: 4, right: 4, bottom: 4, left: 4 }}>
          {/* Threshold reference at 0 */}
          <ReferenceLine y={0} stroke="var(--color-ink-rule)" strokeDasharray="2 4" strokeOpacity={0.6} />
          <XAxis dataKey="idx" hide />
          <YAxis yAxisId="score" hide domain={['auto', 'auto']} />
          <YAxis yAxisId="vol" hide orientation="right" domain={[0, 2]} />
          <Tooltip
            content={({ active, payload }) => {
              if (!active || !payload?.length) return null
              const score = payload.find(p => p.dataKey === 'score')?.value as number | undefined
              if (score == null) return null
              return (
                <div className="bg-paper border border-paper-rule rounded-sm px-2 py-1 font-mono text-[9px] text-ink-primary shadow-sm">
                  {fmtComposite(String(score))}
                </div>
              )
            }}
          />
          {/* Volume bars (bottom panel feel) */}
          <Bar
            yAxisId="vol"
            dataKey="vol"
            fill={volColor}
            fillOpacity={0.55}
            isAnimationActive={false}
            barSize={8}
          />
          {/* Composite line */}
          <Line
            yAxisId="score"
            type="monotone"
            dataKey="score"
            stroke={lineColor}
            strokeWidth={1.4}
            dot={false}
            activeDot={{ r: 2.5, fill: lineColor }}
            isAnimationActive={false}
          />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Conviction Tape (1m/3m/6m/12m from matrix_tenure_dominant / action data)
// ---------------------------------------------------------------------------

type TapeSegment = { tenure: string; active: boolean; sign: 'pos' | 'neg' | 'neutral' }

function buildTape(row: LandscapeRow): TapeSegment[] {
  const tenures = ['1m', '3m', '6m', '12m']
  const dominantTenure = row.matrix_tenure_dominant
  const sign = row.matrix_action_sign

  return tenures.map(t => {
    const isActive = t === dominantTenure
    const segSign: TapeSegment['sign'] =
      !isActive ? 'neutral' : sign === 'POS' ? 'pos' : sign === 'NEG' ? 'neg' : 'neutral'
    return { tenure: t, active: isActive, sign: segSign }
  })
}

function TapeSegmentEl({ seg }: { seg: TapeSegment }) {
  const style =
    seg.sign === 'pos'
      ? 'bg-signal-pos border-signal-pos text-paper'
      : seg.sign === 'neg'
      ? 'bg-signal-neg border-signal-neg text-paper'
      : 'bg-paper-deep border-paper-rule text-ink-quaternary'

  return (
    <span
      className={`w-[18px] h-[16px] rounded-[1px] border flex items-center justify-center font-mono text-[9px] ${style}`}
    >
      {seg.sign === 'pos' ? '+' : seg.sign === 'neg' ? '−' : '·'}
    </span>
  )
}

// ---------------------------------------------------------------------------
// Stock card
// ---------------------------------------------------------------------------

function StockCard({ row }: { row: LandscapeRow }) {
  const action = row.action ?? 'WATCH'
  const compositeN = row.composite_score ? parseFloat(row.composite_score) : 0

  const borderColor =
    action === 'BUY' ? 'border-l-signal-pos' : action === 'AVOID' ? 'border-l-signal-neg' : 'border-l-signal-warn'

  const actionBg =
    action === 'BUY'
      ? 'bg-signal-pos text-paper'
      : action === 'AVOID'
      ? 'bg-signal-neg text-paper'
      : 'bg-signal-warn/10 text-signal-warn border border-signal-warn/40'

  const compositeColor =
    compositeN >= 4 ? 'text-signal-pos' : compositeN <= -4 ? 'text-signal-neg' : 'text-signal-warn'

  const rs3mN = row.rs_3m_nifty500 ? parseFloat(row.rs_3m_nifty500) * 100 : 0
  const rs3mColor = rs3mN >= 0 ? 'text-signal-pos' : 'text-signal-neg'

  const ret12mN = row.ret_12m ? parseFloat(row.ret_12m) * 100 : 0
  const ret12mColor = ret12mN >= 0 ? 'text-signal-pos' : 'text-signal-neg'

  const tape = buildTape(row)
  const activeSegs = tape.filter(t => t.active).length
  const totalSegs = tape.length

  const cellLabel =
    row.cap_tier && row.matrix_tenure_dominant && row.matrix_action_sign
      ? `${row.cap_tier.charAt(0)} ${row.matrix_tenure_dominant} ${row.matrix_action_sign}`
      : '—'

  return (
    <Link
      href={`/stocks/${encodeURIComponent(row.symbol)}`}
      className={`bg-paper border border-paper-rule border-l-[3px] ${borderColor} rounded-sm p-[18px] flex flex-col gap-3 no-underline text-inherit transition-colors hover:bg-paper-soft hover:border-paper-rule group`}
    >
      {/* Header */}
      <div className="flex items-start justify-between gap-2">
        <div className="flex flex-col">
          <span className="font-mono font-semibold text-ink-primary text-[17px] tracking-[0.02em]">
            {row.symbol}
          </span>
          <span className="font-serif text-[14px] text-ink-secondary leading-snug mt-[1px]">
            {row.company_name ?? row.symbol}
          </span>
          <span className="font-mono text-[10px] text-ink-tertiary mt-[3px] tracking-[0.04em]">
            {(row.industry ?? row.sector ?? '—').toUpperCase()} · {row.cap_tier.toUpperCase()} · {fmtMcap(row.liquidity_proxy_cr)} · COMP {fmtComposite(row.composite_score)}
          </span>
        </div>
        <span
          className={`font-mono text-[10px] tracking-[0.14em] uppercase font-bold px-[9px] py-[4px] rounded-sm shrink-0 ${actionBg}`}
        >
          {action}
        </span>
      </div>

      {/* Multidim mini-chart */}
      <MiniMultidimChart row={row} />

      {/* Conviction tape */}
      <div className="flex items-center gap-[10px] pt-[6px] border-t border-paper-rule">
        <span className="font-sans text-[9px] tracking-[0.14em] uppercase text-ink-tertiary font-semibold">
          Tape 1m·3m·6m·12m
        </span>
        <div className="flex gap-[2px] items-center">
          {tape.map(t => <TapeSegmentEl key={t.tenure} seg={t} />)}
        </div>
        <span className="font-mono text-[10px] text-ink-tertiary ml-auto">
          {activeSegs} / {totalSegs} active
        </span>
      </div>

      {/* Cell readout */}
      <div className="bg-paper-soft border border-paper-rule rounded-sm px-3 py-[10px] font-sans text-[11px] text-ink-tertiary leading-relaxed">
        <div className="flex gap-3 items-baseline flex-wrap">
          <span
            className={`font-sans text-[9px] tracking-[0.12em] font-bold px-[6px] py-[2px] rounded-sm ${action === 'BUY' ? 'bg-signal-pos text-paper' : 'bg-signal-neg text-paper'}`}
          >
            {cellLabel}
          </span>
          <span>
            IC <strong className="text-ink-primary">{row.cell_ic ? `.${Math.round(parseFloat(row.cell_ic) * 1000).toString().padStart(3, '0')}` : '—'}</strong>
          </span>
          <span>
            conf <strong className="text-ink-primary">{row.confidence_label ?? '—'}</strong>
          </span>
          <span>
            tenor <strong className="text-ink-primary">{row.matrix_tenure_dominant ?? '—'}</strong>
          </span>
        </div>
      </div>

      {/* Metrics grid */}
      <div className="grid grid-cols-4 gap-[6px] pt-2 border-t border-paper-rule">
        {[
          { lbl: 'Comp', val: fmtComposite(row.composite_score), cls: compositeColor },
          { lbl: 'RS 3M', val: fmtRs3m(row.rs_3m_nifty500), cls: rs3mColor },
          { lbl: '12M', val: fmtRet(row.ret_12m), cls: ret12mColor },
          { lbl: 'Conf', val: row.confidence_label ?? '—', cls: 'text-ink-primary' },
        ].map(m => (
          <div key={m.lbl} className="flex flex-col items-center">
            <span className="font-sans text-[8px] tracking-[0.14em] uppercase text-ink-tertiary font-semibold">
              {m.lbl}
            </span>
            <span className={`font-mono text-[12px] font-semibold mt-[2px] ${m.cls} truncate text-center w-full`}>
              {m.val}
            </span>
          </div>
        ))}
      </div>

      {/* Footer */}
      <div className="flex items-center justify-between pt-[6px] border-t border-paper-rule font-sans text-[10.5px] text-ink-tertiary">
        <span>
          {row.cell_tenure} cell ·{' '}
          {row.cell_fire_date
            ? new Date(row.cell_fire_date as string).toLocaleDateString('en-IN', {
                day: '2-digit',
                month: 'short',
                year: '2-digit',
              })
            : '—'}
        </span>
        <span className="font-mono font-semibold text-accent group-hover:underline">
          Deep-dive →
        </span>
      </div>
    </Link>
  )
}

// ---------------------------------------------------------------------------
// Main export
// ---------------------------------------------------------------------------

export function SixPicksWorthClick({ data }: { data: LandscapeRow[] }) {
  const picks = useMemo(() => pickSixStocks(data, { requireTrajectory: false }), [data])

  return (
    <section className="py-9 border-b border-paper-rule">
      <div className="max-w-[1400px] mx-auto px-8">
        <div className="mb-5">
          <h2 className="font-serif text-[28px] font-normal tracking-tight text-ink-primary leading-none">
            Six picks worth a click
          </h2>
          <p className="font-sans text-[13px] text-ink-tertiary mt-1 max-w-[760px] leading-snug">
            The three highest-conviction BUYs and the three sharpest AVOIDs, each with a composite
            trajectory mini-chart, conviction tape, the firing cell + locked IC, and key metrics.
            Click any card for the full per-stock deep-dive.
          </p>
        </div>

        {picks.length === 0 ? (
          <div className="bg-paper border border-paper-rule rounded-sm p-8 text-center font-sans text-[13px] text-ink-tertiary">
            No picks available. Run the nightly pipeline.
          </div>
        ) : (
          <div className="grid grid-cols-3 gap-4">
            {picks.map(row => (
              <StockCard key={row.instrument_id} row={row} />
            ))}
          </div>
        )}
      </div>
    </section>
  )
}
