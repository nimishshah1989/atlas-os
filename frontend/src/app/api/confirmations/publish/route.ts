// POST /api/confirmations/publish — freeze the week and roll the book forward.
// Revalidates server-side against the STORED book, so a stale editor tab cannot
// slip a sell past a position that is no longer there.
import { NextResponse } from 'next/server'

import { PORTFOLIO_CODES, type PortfolioCode } from '@/lib/confirmations'
import { requireAuth } from '@/lib/requireAuth'
import { publish } from '@/lib/queries/confirmations'

export const dynamic = 'force-dynamic'

export async function POST(req: Request) {
  const denied = await requireAuth('publish a confirmation')
  if (denied) return denied

  let body: { code?: unknown; week?: unknown } = {}
  try {
    body = await req.json()
  } catch {
    // fall through to validation
  }
  const { code, week } = body
  if (typeof code !== 'string' || !(PORTFOLIO_CODES as readonly string[]).includes(code)) {
    return NextResponse.json({ error_code: 'bad_request', message: 'unknown portfolio code' }, { status: 400 })
  }
  if (typeof week !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(week)) {
    return NextResponse.json({ error_code: 'bad_request', message: 'week must be YYYY-MM-DD' }, { status: 400 })
  }

  const result = await publish(code as PortfolioCode, week)
  if (!result.ok) {
    return NextResponse.json({ error_code: 'not_publishable', problems: result.problems }, { status: 422 })
  }
  return NextResponse.json({ published: true, book: result.book })
}
