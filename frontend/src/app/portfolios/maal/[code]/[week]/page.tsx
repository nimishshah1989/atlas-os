// Author one week's confirmation for one book. The editor is a client component;
// this shell loads the week and the book it opens from.
export const dynamic = 'force-dynamic'

import { notFound } from 'next/navigation'
import Link from 'next/link'

import { MaalEditor } from '@/components/maal/MaalEditor'
import { MAAL_CODES, MAAL_NAMES, type MaalCode } from '@/lib/maal'
import { getConfirmation, getMaxCap, getOpeningBook } from '@/lib/queries/maal'
import { isAuthed } from '@/lib/requireAuth'
import { formatIST } from '@/lib/format-date'

export const metadata = { title: 'Confirmation · Atlas' }

export default async function MaalEditorPage({
  params,
}: {
  params: Promise<{ code: string; week: string }>
}) {
  const { code, week } = await params
  if (!(MAAL_CODES as readonly string[]).includes(code)) notFound()
  if (!/^\d{4}-\d{2}-\d{2}$/.test(week)) notFound()
  const pf = code as MaalCode

  const [existing, openingBook, maxCapPct, canEdit] = await Promise.all([
    getConfirmation(pf, week),
    getOpeningBook(pf, week),
    getMaxCap(pf),
    isAuthed(),
  ])

  return (
    <div className="mx-auto max-w-[1400px] space-y-5 px-6 py-7">
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <div>
          <Link
            href="/portfolios/maal"
            className="font-num text-[11px] uppercase tracking-[0.14em] text-accent no-underline hover:underline"
          >
            ← All books
          </Link>
          <h1 className="mt-1 font-display text-[26px] font-medium tracking-tight text-txt-1">
            {MAAL_NAMES[pf]}
          </h1>
          <p className="font-sans text-[13px] text-txt-3">Confirmation for {formatIST(week)}</p>
        </div>
        {existing?.status === 'published' && (
          <Link
            href={`/portfolios/maal/${pf}/${week}/report`}
            className="rounded-tile border border-brand/40 bg-brand/10 px-3 py-2 font-sans text-[12.5px] font-semibold text-brand no-underline hover:bg-brand/15"
          >
            View report →
          </Link>
        )}
      </div>

      {!canEdit && (
        <p className="rounded-panel border border-sig-warn/30 bg-sig-warn/[0.06] px-4 py-2.5 font-sans text-[12.5px] text-txt-2">
          Read-only — you can review this week, but saving or publishing needs a sign-in.{' '}
          <a href="/login" className="font-semibold text-accent no-underline hover:underline">
            Sign in
          </a>
          .
        </p>
      )}

      <MaalEditor
        code={pf}
        week={week}
        openingBook={existing?.openingBook ?? openingBook}
        initial={existing}
        maxCapPct={existing?.maxCapPct ?? maxCapPct}
      />
    </div>
  )
}
