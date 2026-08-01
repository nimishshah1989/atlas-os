// GET /api/maal?code=alpha&week=YYYY-MM-DD — one week of the FM's
// Monday document, plus the book it opens from. Feeds both editor and report.
// Without ?week, returns the book's report history.
import { NextResponse } from 'next/server'

import { MAAL_CODES, type MaalCode } from '@/lib/maal'
import { getConfirmation, getOpeningBook, listConfirmations } from '@/lib/queries/maal'

export const dynamic = 'force-dynamic'

const isCode = (v: string | null): v is MaalCode =>
  v != null && (MAAL_CODES as readonly string[]).includes(v)

export async function GET(req: Request) {
  const url = new URL(req.url)
  const code = url.searchParams.get('code')
  const week = url.searchParams.get('week')
  if (!isCode(code)) {
    return NextResponse.json(
      { error_code: 'bad_request', message: `code must be one of ${MAAL_CODES.join(', ')}` },
      { status: 400 },
    )
  }

  if (!week) {
    const [history, book] = await Promise.all([listConfirmations(code), getOpeningBook(code)])
    return NextResponse.json({ code, history, book })
  }
  if (!/^\d{4}-\d{2}-\d{2}$/.test(week)) {
    return NextResponse.json(
      { error_code: 'bad_request', message: 'week must be YYYY-MM-DD' },
      { status: 400 },
    )
  }

  const confirmation = await getConfirmation(code, week)
  if (!confirmation) {
    // Not started yet — hand back the opening book so the editor can render empty.
    return NextResponse.json({ code, week, confirmation: null, openingBook: await getOpeningBook(code, week) })
  }
  return NextResponse.json({ code, week, confirmation })
}
