// Author one week's confirmation for one book. The editor is a client component;
// this shell loads the week and the book it opens from.
export const dynamic = 'force-dynamic'

import { notFound } from 'next/navigation'
import Link from 'next/link'

import { ConfirmationEditor } from '@/components/confirmations/ConfirmationEditor'
import { PORTFOLIO_CODES, PORTFOLIO_NAMES, type PortfolioCode } from '@/lib/confirmations'
import { getConfirmation, getMaxCap, getOpeningBook } from '@/lib/queries/confirmations'
import { formatIST } from '@/lib/format-date'

export const metadata = { title: 'Confirmation · Atlas' }

export default async function ConfirmationEditorPage({
  params,
}: {
  params: Promise<{ code: string; week: string }>
}) {
  const { code, week } = await params
  if (!(PORTFOLIO_CODES as readonly string[]).includes(code)) notFound()
  if (!/^\d{4}-\d{2}-\d{2}$/.test(week)) notFound()
  const pf = code as PortfolioCode

  const [existing, openingBook, maxCapPct] = await Promise.all([
    getConfirmation(pf, week),
    getOpeningBook(pf, week),
    getMaxCap(pf),
  ])

  return (
    <div className="mx-auto max-w-[1400px] space-y-5 px-6 py-7">
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <div>
          <Link
            href="/portfolios/confirmations"
            className="font-num text-[11px] uppercase tracking-[0.14em] text-accent no-underline hover:underline"
          >
            ← All books
          </Link>
          <h1 className="mt-1 font-display text-[26px] font-medium tracking-tight text-txt-1">
            {PORTFOLIO_NAMES[pf]}
          </h1>
          <p className="font-sans text-[13px] text-txt-3">Confirmation for {formatIST(week)}</p>
        </div>
        {existing?.status === 'published' && (
          <Link
            href={`/portfolios/confirmations/${pf}/${week}/report`}
            className="rounded-tile border border-brand/40 bg-brand/10 px-3 py-2 font-sans text-[12.5px] font-semibold text-brand no-underline hover:bg-brand/15"
          >
            View report →
          </Link>
        )}
      </div>

      <ConfirmationEditor
        code={pf}
        week={week}
        openingBook={existing?.openingBook ?? openingBook}
        initial={existing}
        maxCapPct={existing?.maxCapPct ?? maxCapPct}
      />
    </div>
  )
}
