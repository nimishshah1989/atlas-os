// The MaaL Process tab: one card per model book — what it holds now, and
// the recent reports. Published reports are the book's history, so this is read
// straight from stored snapshots, never re-derived.
export const dynamic = 'force-dynamic'

import Link from 'next/link'

import { PortfolioTabs } from '@/components/maal/PortfolioTabs'
import { BookCard } from '@/components/maal/BookCard'
import { MAAL_CODES, MAAL_NAMES, mondayOf } from '@/lib/maal'
import { getMaxCap, getOpeningBook, listConfirmations } from '@/lib/queries/maal'
import { isAuthed } from '@/lib/requireAuth'

export const metadata = { title: 'MaaL Process · Atlas' }

export default async function ConfirmationsPage() {
  const thisMonday = mondayOf(new Date().toISOString().slice(0, 10))
  const canEdit = await isAuthed()
  const books = await Promise.all(
    MAAL_CODES.map(async (code) => ({
      code,
      name: MAAL_NAMES[code],
      book: await getOpeningBook(code),
      history: await listConfirmations(code),
      maxCapPct: await getMaxCap(code),
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

      <PortfolioTabs active="maal" />

      {!canEdit && (
        <p className="rounded-panel border border-sig-warn/30 bg-sig-warn/[0.06] px-4 py-2.5 font-sans text-[12.5px] text-txt-2">
          You are viewing this read-only — the board is open, but authoring a confirmation needs a
          sign-in.{' '}
          <a href="/login" className="font-semibold text-accent no-underline hover:underline">
            Sign in
          </a>{' '}
          to set a max cap, save a draft or publish.
        </p>
      )}

      <p className="max-w-[860px] font-sans text-[13.5px] text-txt-2">
        Author this week&rsquo;s buy and sell calls against each model portfolio, attach the charts that
        make the case, and publish a report to circulate. Publishing rolls the book forward — next
        week&rsquo;s sell list is whatever the book holds after this one.
      </p>

      <div className="grid gap-4 lg:grid-cols-3">
        {books.map((b) => (
          <BookCard key={b.code} {...b} thisMonday={thisMonday} canEdit={canEdit} />
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
