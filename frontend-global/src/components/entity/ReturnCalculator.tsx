'use client'
// src/components/entity/ReturnCalculator.tsx — two dates in, four numbers out, on the sessions
// that actually exist.
//
// WHY IT MATTERS THAT IT IS FOUR NUMBERS. "It returned 41 percent" is not a fact anyone can act
// on. The four together are:
//   total      splits and dividends — what a holder actually made
//   price      splits only — the same window without the income, so the gap IS the income
//   SPY        the same two sessions in the benchmark, because the board's whole claim is relative
//   against    the relative form, (1 + r) / (1 + b) − 1, matching the RS columns exactly
//
// NOTHING IS INTERPOLATED. Ask for a Sunday and the answer is computed on the last session at or
// before it, and the header says which two sessions were used. A price for a day the market was
// shut is precisely the kind of number rule #0 keeps off this board.
import { useMemo, useState } from 'react'
import { Section } from '@/components/ui/Section'
import { formatIsoDate, formatPct } from '@/lib/format'
import type { InstrumentSeries } from '@/lib/queries/series'
import { periodReturn } from '@/lib/series'

/** A default window that is real for almost every instrument: the last 252 sessions the spine
 *  holds for THIS one, rather than "a year ago" which a fund listed in March never had. */
const DEFAULT_SESSIONS = 252

export function ReturnCalculator({ series, symbol }: { series: InstrumentSeries; symbol: string }) {
  const bars = series.points
  const first = bars[0]?.date ?? ''
  const last = bars[bars.length - 1]?.date ?? ''
  const defaultFrom = bars[Math.max(0, bars.length - 1 - DEFAULT_SESSIONS)]?.date ?? first

  const [from, setFrom] = useState(defaultFrom)
  const [to, setTo] = useState(last)

  const answer = useMemo(() => periodReturn(bars, series.benchmark, from, to), [bars, series.benchmark, from, to])

  if (bars.length < 2) return null

  const Row = ({ label, value, note }: { label: string; value: number | null; note: string }) => (
    <div className="fact">
      <dt className="text-meta text-ink-3">{label}</dt>
      <dd className="text-body text-ink">
        {value == null ? <span className="text-ink-3">—</span> : <span className="num text-section">{formatPct(String(value), 2)}</span>}
      </dd>
      <dd className="fact-src text-meta text-ink-3">{note}</dd>
    </div>
  )

  return (
    <Section
      title="Any two dates"
      note={`${formatIsoDate(first)} to ${formatIsoDate(last)} is what the spine holds`}
      aside={
        <span className="flex flex-wrap items-center gap-2">
          <label className="text-meta text-ink-3">
            From{' '}
            <input
              type="date"
              className="field"
              value={from}
              min={first}
              max={last}
              onChange={(e) => setFrom(e.target.value)}
              aria-label="Start date"
            />
          </label>
          <label className="text-meta text-ink-3">
            To{' '}
            <input
              type="date"
              className="field"
              value={to}
              min={first}
              max={last}
              onChange={(e) => setTo(e.target.value)}
              aria-label="End date"
            />
          </label>
        </span>
      }
    >
      {answer == null ? (
        <p className="panel px-4 py-3 text-body text-ink-2">
          No two sessions in that window. {symbol} has bars from {formatIsoDate(first)}; pick a
          start on or after it, and an end after the start.
        </p>
      ) : (
        <>
          <dl className="facts">
            <Row label="Total return" value={answer.total} note="splits and dividends — what a holder made" />
            <Row label="Price only" value={answer.price} note="splits only; the gap above is the income" />
            <Row label="SPY, same two sessions" value={answer.benchmark} note="total return" />
            <Row label="Against SPY" value={answer.relative} note="the relative form the RS columns use" />
          </dl>
          <p className="mt-1 text-meta text-ink-3">
            Computed on the sessions {formatIsoDate(answer.from)} and {formatIsoDate(answer.to)} — the
            last trading days at or before the dates asked for. Nothing between sessions is invented.
          </p>
        </>
      )}
    </Section>
  )
}
