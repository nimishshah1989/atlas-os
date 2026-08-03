// The two action-facing halves of the circulated report: the checklist of what to
// do, and the per-instrument case behind each line of it.
//
// Shape (FM, 2026-08-01): the desk needs to ACT first and read second. The old
// layout split buys and sells into separate tables with the rationales stranded
// underneath, which meant reading the whole document to learn what to trade.
import Link from 'next/link'

import { instrumentHref } from '@/lib/maal'
import type { CallRow } from '@/lib/queries/maal'

const pct1 = (v: number) => `${v.toFixed(1)}%`

// Whole rupees, Indian grouping, no symbol and no paise. The currency never varies
// and paise are below the desk's decision resolution, so both were pure noise repeated
// on every row — the ₹ now sits once in the column header instead.
const inr = (v: number | null) =>
  v == null ? '—' : Math.round(v).toLocaleString('en-IN')

/** BUY / SELL pill. Colour carries the meaning; the word carries it in print. */
function ActionTag({ side }: { side: 'buy' | 'sell' }) {
  const buy = side === 'buy'
  return (
    <span
      className={`inline-block rounded-sm px-1.5 py-px font-num text-[9px] font-semibold uppercase tracking-wider ${
        buy ? 'bg-sig-pos/12 text-sig-pos' : 'bg-sig-neg/12 text-sig-neg'
      }`}
    >
      {buy ? 'Buy' : 'Sell'}
    </span>
  )
}

/** What the row means in plain words — the desk should not have to infer it. */
const actionOf = (k: CallRow) =>
  k.side === 'buy' ? `Take to ${pct1(k.weightPct)}` : `Trim ${pct1(k.weightPct)}`

/**
 * One side's summary — buys or sells, never mixed (FM, 2026-08-01). Keeping them in
 * separate, colour-coded blocks means the desk can see at a glance what it is doing,
 * rather than reading an Action column down a combined list.
 */
export function SideSummary({ side, actions }: { side: 'buy' | 'sell'; actions: CallRow[] }) {
  if (actions.length === 0) return null
  const buy = side === 'buy'
  return (
    <section
      className={`break-inside-avoid rounded-panel border px-5 py-4 ${
        buy ? 'border-sig-pos/35 bg-sig-pos/[0.05]' : 'border-sig-neg/35 bg-sig-neg/[0.05]'
      }`}
    >
      <h2
        className={`mb-3.5 font-num text-[11.5px] font-semibold uppercase tracking-[0.16em] ${
          buy ? 'text-sig-pos' : 'text-sig-neg'
        }`}
      >
        {buy ? `Buy — ${actions.length} to add` : `Sell — ${actions.length} to trim`}
      </h2>
      <table className="w-full table-fixed border-collapse font-sans text-[13px]">
        <colgroup>
          <col className="w-8" />
          <col className="w-[15%]" />
          <col className="w-[15%]" />
          <col className="w-[11%]" />
          {buy && <col className="w-[10%]" />}
          {buy && <col className="w-[10%]" />}
          <col />
        </colgroup>
        <thead>
          <tr className="border-b border-edge-rule text-left font-num text-[9.5px] uppercase tracking-wider text-txt-3">
            <th className="pb-2.5" aria-label="Done" />
            <th className="pb-2.5">Instrument</th>
            <th className="pb-2.5">Sector</th>
            <th className="pb-2.5 text-right">{buy ? 'Target' : 'Trim'}</th>
            {buy && <th className="pb-2.5 text-right">Trigger ₹</th>}
            {buy && <th className="pb-2.5 text-right">Stop ₹</th>}
            <th className="pb-2.5 pl-5">Why</th>
          </tr>
        </thead>
        <tbody>
          {actions.map((k) => (
            <tr key={`${k.side}:${k.key}`} className="border-b border-edge-hair align-top">
              <td className="py-3">
                <span className="inline-block h-3.5 w-3.5 rounded-[3px] border border-edge-strong align-middle" />
              </td>
              <td className="py-3">
              <Link
                href={instrumentHref(k.key)}
                className="font-num font-semibold text-txt-1 no-underline hover:text-accent hover:underline"
              >
                {k.symbol}
              </Link>
            </td>
              <td className="py-3 text-txt-2">{k.sector ?? '—'}</td>
              <td className="py-3 text-right font-num text-[14px] font-semibold tabular-nums text-txt-1">
                {pct1(k.weightPct)}
              </td>
              {buy && (
                <td className="py-3 text-right font-num tabular-nums text-txt-2">
                  {inr(k.triggerPrice)}
                </td>
              )}
              {buy && (
                <td className="py-3 text-right font-num tabular-nums text-txt-2">
                  {inr(k.stopPrice)}
                </td>
              )}
              {/* Wraps rather than truncating. A rationale cut mid-word told the
                  reader nothing and still cost the same row. */}
              <td className="py-3 pl-5 leading-relaxed text-txt-2">
                {k.side === 'sell'
                  ? k.reasons.join(' · ') || '—'
                  : k.comment || '—'}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  )
}

/** One side's detailed cards, under a matching colour-coded heading. */
export function SideDetail({ side, actions }: { side: 'buy' | 'sell'; actions: CallRow[] }) {
  if (actions.length === 0) return null
  const buy = side === 'buy'
  return (
    <section>
      <h2
        className={`mb-3 font-num text-[11.5px] font-semibold uppercase tracking-[0.16em] ${
          buy ? 'text-sig-pos' : 'text-sig-neg'
        }`}
      >
        {buy ? 'Buy — the case' : 'Sell — the case'}
      </h2>
      <div className="space-y-4">
        {actions.map((k) => (
          <InstrumentCard key={`card:${k.side}:${k.key}`} k={k} />
        ))}
      </div>
    </section>
  )
}

/** One instrument: the numbers, the reasoning, and the chart that makes the case. */
function InstrumentCard({ k }: { k: CallRow }) {
  const hasChart = k.hasImage && k.callId != null
  return (
    <article
      className={`break-inside-avoid rounded-panel border-l-[3px] border-y border-r border-edge-hair bg-surface-panel px-5 py-4 ${
        k.side === 'buy' ? 'border-l-sig-pos/60' : 'border-l-sig-neg/60'
      }`}
    >
      <div className="mb-3 flex flex-wrap items-baseline gap-x-3 gap-y-1 border-b border-edge-hair pb-2.5">
        <ActionTag side={k.side} />
        <Link
          href={instrumentHref(k.key)}
          className="font-num text-[16px] font-semibold text-txt-1 no-underline hover:text-accent hover:underline"
        >
          {k.symbol}
        </Link>
        <span className="font-sans text-[12px] text-txt-3">{k.name}</span>
        <span className="ml-auto font-num text-[14px] font-semibold tabular-nums text-txt-1">
          {actionOf(k)}
        </span>
      </div>

      <dl className="mb-3 flex flex-wrap gap-x-8 gap-y-1.5 font-sans text-[12px]">
        <div className="flex gap-1.5">
          <dt className="text-txt-3">Sector</dt>
          <dd className="text-txt-2">{k.sector ?? '—'}</dd>
        </div>
        {k.side === 'buy' && (
          <>
            <div className="flex gap-1.5">
              <dt className="text-txt-3">Trigger ₹</dt>
              <dd className="font-num tabular-nums text-txt-2">{inr(k.triggerPrice)}</dd>
            </div>
            <div className="flex gap-1.5">
              <dt className="text-txt-3">Stop ₹</dt>
              <dd className="font-num tabular-nums text-txt-2">{inr(k.stopPrice)}</dd>
            </div>
          </>
        )}
        {k.side === 'sell' && k.reasons.length > 0 && (
          <div className="flex gap-1.5">
            <dt className="text-txt-3">Reason</dt>
            <dd className="text-txt-2">{k.reasons.join(' · ')}</dd>
          </div>
        )}
      </dl>

      {/* Chart beside the words on screen, stacked on paper — a side-by-side split
          at print width squeezes the chart to unreadable. */}
      <div className={hasChart ? 'grid gap-5 md:grid-cols-[1.1fr_1fr] print:block' : ''}>
        {k.comment ? (
          <p className="font-sans text-[13px] leading-[1.65] text-txt-2">{k.comment}</p>
        ) : (
          <p className="font-sans text-[12px] italic text-txt-3">No written rationale.</p>
        )}
        {hasChart && (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={`/api/maal/image/call/${k.callId}`}
            alt={`${k.symbol} chart`}
            className="max-w-full rounded-tile border border-edge-hair print:mt-2"
          />
        )}
      </div>
    </article>
  )
}
