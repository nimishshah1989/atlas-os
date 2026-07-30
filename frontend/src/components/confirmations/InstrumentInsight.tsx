'use client'
// The box that opens when the FM picks an instrument: the price he is acting on, the
// return/RS ladder against a benchmark he can switch, the trend state, and the engine's
// conviction with anything worth cross-checking marked amber.
//
// Nothing here invents a threshold. Amber means the ENGINE said so — a negative return,
// a stored below-EMA boolean, its own weak tier, its own stretched valuation zone, its
// own risk_flags. A metric that is missing renders as "—", never as a neutral zero.
import Link from 'next/link'
import { useEffect, useState } from 'react'

import { DecileMeter } from '@/components/ui/DecileMeter'
import { instrumentHref } from '@/lib/confirmations'
import { decileOf, emaStack, isConcern, weakTier } from '@/lib/insight'
import type { Benchmark, InstrumentInsight as Insight } from '@/lib/queries/instrumentInsight'

const BENCHMARKS: { id: Benchmark; label: string }[] = [
  { id: 'n50', label: 'vs Nifty 50' },
  { id: 'n500', label: 'vs Nifty 500' },
]

const pp = (v: number | null) => (v == null ? '—' : `${v > 0 ? '+' : ''}${v.toFixed(1)}%`)
const tone = (v: number | null) =>
  v == null ? 'text-txt-3' : v > 0 ? 'text-sig-pos' : v < 0 ? 'text-sig-neg' : 'text-txt-2'

export function InstrumentInsight({ instrumentKey }: { instrumentKey: string }) {
  const [benchmark, setBenchmark] = useState<Benchmark>('n500')
  const [data, setData] = useState<Insight | null>(null)
  const [state, setState] = useState<'loading' | 'ready' | 'error'>('loading')

  useEffect(() => {
    let live = true
    setState('loading')
    fetch(`/api/instruments/insight?key=${encodeURIComponent(instrumentKey)}&benchmark=${benchmark}`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((d) => live && (setData(d), setState('ready')))
      .catch(() => live && setState('error'))
    return () => {
      live = false
    }
  }, [instrumentKey, benchmark])

  if (state === 'loading') {
    return <div className="h-24 animate-pulse rounded-tile border border-edge-hair bg-surface-raised" />
  }
  if (state === 'error' || !data) {
    return (
      <p className="rounded-tile border border-edge-hair bg-surface-raised px-3 py-2 font-sans text-[11.5px] text-txt-3">
        Could not load metrics for this instrument.
      </p>
    )
  }

  const c = data.conviction

  return (
    <div className="rounded-tile border border-edge-hair bg-surface-raised p-3">
      <div className="mb-2.5 flex flex-wrap items-baseline justify-between gap-2">
        <div className="flex items-baseline gap-2">
          <Link
            href={instrumentHref(data.key)}
            className="font-num text-[13px] font-semibold text-txt-1 no-underline hover:text-accent hover:underline"
          >
            {data.symbol} →
          </Link>
          <span className="font-sans text-[11px] text-txt-3">{data.sector ?? 'Unmapped'}</span>
        </div>
        <div className="flex items-baseline gap-2.5">
          <span className="font-num text-[13px] tabular-nums text-txt-1">
            {data.lastClose == null
              ? '—'
              : `₹${data.lastClose.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`}
          </span>
          <span className="font-sans text-[10px] text-txt-3">
            close {data.closeAsOf ?? '—'} · EOD, not live
          </span>
        </div>
      </div>

      {/* return + RS ladder */}
      <div className="mb-2 flex flex-wrap items-center gap-1.5">
        {BENCHMARKS.map((b) => (
          <button
            key={b.id}
            type="button"
            onClick={() => setBenchmark(b.id)}
            className={`rounded-sm border px-1.5 py-0.5 font-num text-[10px] uppercase tracking-wide ${
              benchmark === b.id
                ? 'border-brand/40 bg-brand/10 text-brand'
                : 'border-edge-rule bg-surface-base text-txt-3 hover:text-txt-2'
            }`}
          >
            {b.label}
          </button>
        ))}
        <span className="ml-auto font-sans text-[10px] text-txt-3">metrics {data.metricsAsOf ?? '—'}</span>
      </div>

      <div className="mb-3 overflow-x-auto">
        <table className="w-full min-w-[420px] border-collapse font-num text-[11.5px] tabular-nums">
          <thead>
            <tr className="text-right font-num text-[9px] uppercase tracking-wider text-txt-3">
              <th className="py-1 text-left">Window</th>
              {data.ladder.map((l) => (
                <th key={l.window} className="py-1 pl-3">
                  {l.window}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            <tr className="border-t border-edge-hair text-right">
              <td className="py-1 text-left font-sans text-[11px] text-txt-3">Return</td>
              {data.ladder.map((l) => (
                <td key={l.window} className={`py-1 pl-3 ${tone(l.retPp)}`}>
                  {pp(l.retPp)}
                </td>
              ))}
            </tr>
            <tr className="border-t border-edge-hair text-right">
              <td className="py-1 text-left font-sans text-[11px] text-txt-3">
                RS {benchmark === 'n50' ? 'N50' : 'N500'}
              </td>
              {data.ladder.map((l) => (
                <td key={l.window} className={`py-1 pl-3 ${tone(l.rsPp)}`}>
                  {pp(l.rsPp)}
                </td>
              ))}
            </tr>
          </tbody>
        </table>
      </div>

      {/* price vs moving-average stack — the FM's long/short alignment read */}
      <EmaStackRow
        close={data.lastClose}
        ema21={data.ema21}
        ema50={data.ema50}
        ema200={data.ema200}
      />

      {/* trend / technical state */}
      <div className="mb-3 flex flex-wrap gap-x-4 gap-y-1.5 border-t border-edge-hair pt-2.5">
        <Chip label="Above 50 EMA" bool={data.aboveEma50} />
        <Chip label="Above 200 EMA" bool={data.aboveEma200} />
        <Metric label="RSI 14" value={data.rsi14 == null ? '—' : data.rsi14.toFixed(0)} />
        <Metric label="52w position" value={data.pos52w == null ? '—' : `${data.pos52w.toFixed(0)}%`} />
        <Metric
          label="Volume vs 30d"
          value={data.volRatio30d == null ? '—' : `${data.volRatio30d.toFixed(2)}×`}
        />
      </div>

      {/* conviction — stock lens, or the ETF holdings roll-up */}
      <ConvictionBlock c={c} absentReason={data.convictionAbsentReason} />
    </div>
  )
}

/**
 * The stack as a readable chain: 432.45 > 428.51 > 418.60 > 392.20, each inequality
 * coloured by direction. Fully ascending is the FM's long alignment; fully descending is
 * short. A mixed chain shows exactly which link broke instead of hiding it in a verdict.
 */
function EmaStackRow({
  close,
  ema21,
  ema50,
  ema200,
}: {
  close: number | null
  ema21: number | null
  ema50: number | null
  ema200: number | null
}) {
  const { links, verdict } = emaStack(close, ema21, ema50, ema200)
  if (verdict == null) {
    return (
      <div className="mb-3 border-t border-edge-hair pt-2.5">
        <div className="font-num text-[9px] uppercase tracking-wider text-txt-3">EMA stack</div>
        <div className="font-sans text-[11.5px] text-txt-3">
          Not enough moving-average history yet.
        </div>
      </div>
    )
  }

  const num = (v: number | null) => (v == null ? '—' : v.toFixed(2))
  const values = [close, ema21, ema50, ema200]
  const badge =
    verdict === 'aligned-up'
      ? { text: 'Stacked up · long alignment', cls: 'bg-sig-pos/15 text-sig-pos' }
      : verdict === 'aligned-down'
        ? { text: 'Stacked down · short alignment', cls: 'bg-sig-neg/15 text-sig-neg' }
        : { text: 'Mixed', cls: 'bg-sig-warn/15 text-sig-warn' }

  return (
    <div className="mb-3 border-t border-edge-hair pt-2.5">
      <div className="mb-1 flex flex-wrap items-center gap-2">
        <span className="font-num text-[9px] uppercase tracking-wider text-txt-3">EMA stack</span>
        <span
          className={`rounded-sm px-1.5 py-0.5 font-num text-[9px] font-semibold uppercase tracking-wide ${badge.cls}`}
        >
          {badge.text}
        </span>
      </div>
      <div className="flex flex-wrap items-baseline gap-1.5 font-num text-[12.5px] tabular-nums">
        {values.map((v, i) => (
          <span key={i} className="flex items-baseline gap-1.5">
            <span className={i === 0 ? 'font-semibold text-txt-1' : 'text-txt-2'}>
              {num(v)}
              <span className="ml-0.5 font-sans text-[9px] text-txt-3">
                {i === 0 ? 'px' : i === 1 ? '21' : i === 2 ? '50' : '200'}
              </span>
            </span>
            {i < links.length && (
              <span
                aria-label={links[i].up ? 'above' : 'below'}
                className={`font-num text-[14px] font-semibold ${
                  links[i].up ? 'text-sig-pos' : 'text-sig-neg'
                }`}
              >
                {links[i].up ? '>' : '<'}
              </span>
            )}
          </span>
        ))}
      </div>
    </div>
  )
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="font-num text-[9px] uppercase tracking-wider text-txt-3">{label}</div>
      <div className="font-num text-[12.5px] tabular-nums text-txt-1">{value}</div>
    </div>
  )
}

function Chip({ label, bool }: { label: string; bool: boolean | null }) {
  const concern = isConcern({ kind: 'bool', value: bool })
  return (
    <div>
      <div className="font-num text-[9px] uppercase tracking-wider text-txt-3">{label}</div>
      <div
        className={`font-num text-[12.5px] font-semibold ${
          bool == null ? 'text-txt-3' : concern ? 'text-sig-warn' : 'text-sig-pos'
        }`}
      >
        {bool == null ? '—' : bool ? 'Yes' : 'No'}
      </div>
    </div>
  )
}

/** A lens sub-score: the number, plus the board's decile glyph so it reads calibrated. */
function Lens({ label, score }: { label: string; score: number | null }) {
  return (
    <div>
      <div className="font-num text-[9px] uppercase tracking-wider text-txt-3">{label}</div>
      <div className="flex items-center gap-1.5">
        <span className="font-num text-[12.5px] tabular-nums text-txt-1">
          {score == null ? '—' : score.toFixed(0)}
        </span>
        <DecileMeter decile={decileOf(score)} size="sm" />
      </div>
    </div>
  )
}

/**
 * Conviction, by whichever route produced it. A stock shows the engine composite and
 * tier; an ETF shows leadership-breadth, because a basket has no composite of its own.
 */
function ConvictionBlock({
  c,
  absentReason,
}: {
  c: Insight['conviction']
  absentReason: string | null
}) {
  if (!c) {
    return (
      <p className="border-t border-edge-hair pt-2.5 font-sans text-[11px] italic text-txt-3">
        {absentReason}
      </p>
    )
  }
  const isEtf = c.basis === 'etf-holdings-rollup'
  return (
    <div className="border-t border-edge-hair pt-2.5">
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <span className="font-num text-[9px] uppercase tracking-wider text-txt-3">
          {isEtf ? 'Leadership breadth' : 'Conviction'}
        </span>
        <span className="font-num text-[15px] font-semibold tabular-nums text-txt-1">
          {isEtf
            ? c.breadthPct == null
              ? '—'
              : `${c.breadthPct.toFixed(1)}%`
            : c.composite == null
              ? '—'
              : c.composite.toFixed(0)}
        </span>
        <DecileMeter decile={decileOf(isEtf ? c.breadthPct : c.composite)} size="sm" />
        {isEtf && (
          <span className="font-sans text-[10.5px] text-txt-3">
            {c.nLeaders ?? 0} of {c.nHoldings ?? 0} holdings are top-decile leaders
          </span>
        )}
        {c.tier && (
          <span
            className={`rounded-sm px-1.5 py-0.5 font-num text-[9px] font-semibold uppercase tracking-wide ${
              weakTier(c.tier) ? 'bg-sig-warn/15 text-sig-warn' : 'bg-sig-pos/15 text-sig-pos'
            }`}
          >
            {c.tier.replace(/_/g, ' ')}
          </span>
        )}
        {isConcern({ kind: 'zone', value: c.valuationZone }) && (
          <span className="rounded-sm bg-sig-warn/15 px-1.5 py-0.5 font-num text-[9px] font-semibold uppercase tracking-wide text-sig-warn">
            {c.valuationZone}
          </span>
        )}
      </div>
      <div className="flex flex-wrap gap-x-4 gap-y-1.5">
        <Lens label="Technical" score={c.technical} />
        <Lens label="Fundamental" score={c.fundamental} />
        <Lens label="Flow" score={c.flow} />
        <Lens label="Valuation" score={c.valuation} />
        <Lens label="Catalyst" score={c.catalyst} />
      </div>
      {isEtf && (
        <p className="mt-2 font-sans text-[10.5px] text-txt-3">
          Lens values are the holdings-weighted average of the stocks this ETF owns — there is
          no basket-level score.
        </p>
      )}
      {c.riskFlags.length > 0 && (
        <p className="mt-2 font-sans text-[11px] text-sig-neg">Risk flags: {c.riskFlags.join(' · ')}</p>
      )}
    </div>
  )
}
