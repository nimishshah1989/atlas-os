// One model book on the confirmations tab: what it holds today + recent reports.
import Link from 'next/link'

import { cashPct, type BookPosition, type PortfolioCode } from '@/lib/confirmations'
import type { ConfirmationSummary } from '@/lib/queries/confirmations'
import { formatIST } from '@/lib/format-date'

export function BookCard({
  code,
  name,
  book,
  history,
  thisMonday,
}: {
  code: PortfolioCode
  name: string
  book: BookPosition[]
  history: ConfirmationSummary[]
  thisMonday: string
}) {
  const cash = cashPct(book)
  const started = history.some((h) => h.weekOf === thisMonday)
  const top = book.slice(0, 5)

  return (
    <section className="rounded-panel border border-edge-hair bg-surface-panel p-4 shadow-tile">
      <div className="mb-3 flex items-baseline justify-between gap-2">
        <h2 className="font-display text-[16px] font-semibold text-txt-1">{name}</h2>
        <span className="font-num text-[11px] tabular-nums text-txt-3">
          {book.length} {book.length === 1 ? 'position' : 'positions'}
        </span>
      </div>

      {book.length === 0 ? (
        <p className="mb-3 rounded-tile border border-edge-hair bg-surface-raised px-2.5 py-2 font-sans text-[11.5px] leading-[1.45] text-txt-3">
          No book yet. The first published report seeds it — enter the holdings you run today as buys.
        </p>
      ) : (
        <>
          <ul className="mb-2 space-y-1">
            {top.map((p) => (
              <li key={p.key} className="flex items-baseline justify-between gap-2">
                <span className="truncate font-num text-[12px] text-txt-2">{p.symbol}</span>
                <span className="shrink-0 font-num text-[12px] tabular-nums text-txt-1">
                  {p.weightPct.toFixed(2)}%
                </span>
              </li>
            ))}
          </ul>
          {book.length > top.length && (
            <p className="mb-2 font-sans text-[11px] text-txt-3">+{book.length - top.length} more</p>
          )}
          <div className="mb-3 flex items-baseline justify-between border-t border-edge-hair pt-2">
            <span className="font-num text-[9px] uppercase tracking-wider text-txt-3">Cash</span>
            <span className="font-num text-[12px] tabular-nums text-txt-1">{cash.toFixed(2)}%</span>
          </div>
        </>
      )}

      <Link
        href={`/portfolios/confirmations/${code}/${thisMonday}`}
        className="mb-3 block rounded-tile border border-brand/40 bg-brand/10 px-3 py-2 text-center font-sans text-[12.5px] font-semibold text-brand no-underline hover:bg-brand/15"
      >
        {started ? 'Continue' : 'Start'} {formatIST(thisMonday)}
      </Link>

      {history.length > 0 && (
        <ul className="space-y-1 border-t border-edge-hair pt-2.5">
          {history.map((h) => (
            <li key={h.weekOf} className="flex items-baseline justify-between gap-2">
              <Link
                href={`/portfolios/confirmations/${code}/${h.weekOf}${h.status === 'published' ? '/report' : ''}`}
                className="font-num text-[11.5px] text-accent no-underline hover:underline"
              >
                {formatIST(h.weekOf)}
              </Link>
              <span className="font-sans text-[11px] text-txt-3">
                {h.buys}B · {h.sells}S
                {h.status === 'draft' && <span className="ml-1.5 text-sig-warn">draft</span>}
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
