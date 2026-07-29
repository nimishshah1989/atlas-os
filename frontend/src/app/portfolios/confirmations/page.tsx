// The Monday confirmations tab: one card per model book — what it holds now, and
// the recent reports. Published reports are the book's history, so this is read
// straight from stored snapshots, never re-derived.
export const dynamic = 'force-dynamic'

import Link from 'next/link'

import { PortfolioTabs } from '@/components/confirmations/PortfolioTabs'
import { BookCard } from '@/components/confirmations/BookCard'
import { PORTFOLIO_CODES, PORTFOLIO_NAMES, mondayOf } from '@/lib/confirmations'
import { getOpeningBook, listConfirmations } from '@/lib/queries/confirmations'

export const metadata = { title: 'Monday confirmations · Atlas' }

export default async function ConfirmationsPage() {
  const thisMonday = mondayOf(new Date().toISOString().slice(0, 10))
  const books = await Promise.all(
    PORTFOLIO_CODES.map(async (code) => ({
      code,
      name: PORTFOLIO_NAMES[code],
      book: await getOpeningBook(code),
      history: await listConfirmations(code),
    })),
  )

  return (
    <div className="mx-auto max-w-[1400px] space-y-6 px-6 py-7">
      <div>
        <p className="font-num text-[9px] uppercase tracking-[0.14em] text-txt-3">
          Weekly buy / sell document · one report per book
        </p>
        <h1 className="font-display text-[28px] font-medium tracking-tight text-txt-1">Portfolios</h1>
      </div>

      <PortfolioTabs active="confirmations" />

      <p className="max-w-[860px] font-sans text-[13.5px] text-txt-2">
        Author this week&rsquo;s buy and sell calls against each model portfolio, attach the charts that
        make the case, and publish a report to circulate. Publishing rolls the book forward — next
        week&rsquo;s sell list is whatever the book holds after this one.
      </p>

      <div className="grid gap-4 lg:grid-cols-3">
        {books.map((b) => (
          <BookCard key={b.code} {...b} thisMonday={thisMonday} />
        ))}
      </div>

      <p className="font-sans text-[12px] italic text-txt-3">
        Showing the three most recent reports per book. Older reports stay in the database.{' '}
        <Link href="/portfolios" className="text-accent no-underline hover:underline">
          Engine-run books →
        </Link>
      </p>
    </div>
  )
}
