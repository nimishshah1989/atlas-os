// One model book on the MaaL tab: what it holds today, which positions are
// maxed out, and the recent reports. Every ticker links to its deep dive.
import Link from 'next/link'

import {
  CAP_TOLERANCE_PCT,
  cashPct,
  instrumentHref,
  type BookPosition,
  type MaalCode,
} from '@/lib/maal'
import type { ConfirmationSummary } from '@/lib/queries/maal'
import { formatIST } from '@/lib/format-date'
import { MaxCapField } from './MaxCapField'

const TOP_N = 6

export function BookCard({
  code,
  name,
  book,
  history,
  thisMonday,
  maxCapPct,
}: {
  code: MaalCode
  name: string
  book: BookPosition[]
  history: ConfirmationSummary[]
  thisMonday: string
  maxCapPct: number
}) {
  const cash = cashPct(book)
  const top = book.slice(0, TOP_N)
  const started = history.some((h) => h.weekOf === thisMonday)
  const capFloor = maxCapPct > 0 ? maxCapPct - CAP_TOLERANCE_PCT : null
  const atCap = capFloor == null ? 0 : book.filter((p) => p.weightPct >= capFloor).length
  const latestPublished = history.find((h) => h.status === 'published')

  return (
    <section className="flex flex-col rounded-panel border border-edge-hair bg-surface-panel p-4 shadow-tile">
      <div className="mb-1 flex items-start justify-between gap-2">
        <h2 className="font-display text-[18px] font-semibold leading-tight text-txt-1">{name}</h2>
        <span className="shrink-0 rounded-tile border border-edge-hair bg-surface-raised px-2 py-0.5 font-num text-[10px] tabular-nums text-txt-2">
          {book.length} {book.length === 1 ? 'position' : 'positions'}
        </span>
      </div>

      <div className="mb-3 border-b border-edge-hair pb-2.5">
        <MaxCapField code={code} capPct={maxCapPct} />
      </div>

      {book.length === 0 ? (
        <p className="mb-3 rounded-tile border border-edge-hair bg-surface-raised px-2.5 py-2 font-sans text-[11.5px] leading-[1.45] text-txt-3">
          No book yet. The first published report seeds it — enter the holdings you run today as buys.
        </p>
      ) : (
        <>
          <ul className="mb-1.5 space-y-1">
            {top.map((p) => {
              const maxed = capFloor != null && p.weightPct >= capFloor
              return (
                <li key={p.key} className="flex items-baseline justify-between gap-2">
                  <Link
                    href={instrumentHref(p.key)}
                    className="truncate font-num text-[12.5px] text-txt-2 no-underline hover:text-accent hover:underline"
                  >
                    {p.symbol}
                  </Link>
                  <span className="flex shrink-0 items-baseline gap-1.5">
                    {maxed && (
                      <span
                        title={`at or within ${CAP_TOLERANCE_PCT}% of the ${maxCapPct.toFixed(1)}% cap`}
                        className="rounded-sm bg-sig-warn/15 px-1 font-num text-[9px] font-semibold uppercase tracking-wide text-sig-warn"
                      >
                        cap
                      </span>
                    )}
                    <span
                      className={`font-num text-[13px] font-semibold tabular-nums ${maxed ? 'text-sig-warn' : 'text-txt-1'}`}
                    >
                      {p.weightPct.toFixed(1)}%
                    </span>
                  </span>
                </li>
              )
            })}
          </ul>

          {book.length > TOP_N && (
            <Link
              href={
                latestPublished
                  ? `/portfolios/maal/${code}/${latestPublished.weekOf}/report`
                  : `/portfolios/maal/${code}/${thisMonday}`
              }
              className="mb-1.5 inline-block font-sans text-[11px] text-accent no-underline hover:underline"
            >
              +{book.length - TOP_N} more →
            </Link>
          )}

          <div className="mb-3 flex items-baseline justify-between border-t border-edge-hair pt-2">
            <span className="font-num text-[9px] uppercase tracking-wider text-txt-3">Cash</span>
            <span className="font-num text-[13px] tabular-nums text-txt-2">{cash.toFixed(1)}%</span>
          </div>
        </>
      )}

      <Link
        href={`/portfolios/maal/${code}/${thisMonday}`}
        className="mb-3 block rounded-tile border border-brand/40 bg-brand/10 px-3 py-2 text-center font-sans text-[13px] font-semibold text-brand no-underline hover:bg-brand/15"
      >
        {started ? 'Continue' : 'Start'} {formatIST(thisMonday)}
      </Link>

      {atCap > 0 && (
        <p className="mb-2.5 font-sans text-[11px] text-txt-3">
          <span className="font-semibold text-sig-warn">{atCap}</span> position{atCap === 1 ? '' : 's'} at
          cap — pre-filled on the sell side
        </p>
      )}

      {history.length > 0 && (
        <ul className="mt-auto space-y-1 border-t border-edge-hair pt-2.5">
          {history.map((h) => (
            <li key={h.weekOf} className="flex items-baseline justify-between gap-2">
              <Link
                href={`/portfolios/maal/${code}/${h.weekOf}${h.status === 'published' ? '/report' : ''}`}
                className="font-num text-[11.5px] text-accent no-underline hover:underline"
              >
                {formatIST(h.weekOf)}
              </Link>
              <span className="font-num text-[11px] tabular-nums text-txt-3">
                <span className="text-sig-pos">{h.buys}B</span> · <span className="text-sig-neg">{h.sells}S</span>
                {h.status === 'draft' && (
                  <span className="ml-1.5 rounded-sm bg-sig-warn/15 px-1 font-sans text-[9px] font-semibold uppercase tracking-wide text-sig-warn">
                    draft
                  </span>
                )}
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
