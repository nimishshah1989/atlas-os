// POST /api/maal/reopen — put a published week back into draft so it can be corrected.
//
// Publish stays one-way by default (ADR 0003): a circulated report must render the
// same forever. Reopening is the deliberate exception, and it is loud — the week
// shows DRAFT until it is published again.
import { NextResponse } from 'next/server'

import { MAAL_CODES, type MaalCode } from '@/lib/maal'
import { reopenConfirmation } from '@/lib/queries/maal'

export const dynamic = 'force-dynamic'

export async function POST(req: Request) {
  const body = await req.json().catch(() => null)
  const code = body?.code
  const week = body?.week
  if (
    typeof code !== 'string' ||
    !(MAAL_CODES as readonly string[]).includes(code) ||
    typeof week !== 'string' ||
    !/^\d{4}-\d{2}-\d{2}$/.test(week)
  ) {
    return NextResponse.json(
      { error_code: 'bad_request', message: 'unknown book or week' },
      { status: 400 },
    )
  }

  const reopened = await reopenConfirmation(code as MaalCode, week)
  if (!reopened) {
    return NextResponse.json(
      { error_code: 'not_published', message: 'this week is not published' },
      { status: 409 },
    )
  }
  return NextResponse.json({ status: 'draft' })
}
