// POST /api/maal/cap — set a book's max position cap %. Stored in
// atlas_thresholds (rule #4: methodology numbers live there, editable from
// /admin/thresholds too), clamped server-side. 0 clears the cap.
import { NextResponse } from 'next/server'

import { MAAL_CODES, type MaalCode } from '@/lib/maal'
import { requireAuth } from '@/lib/requireAuth'
import { setMaxCap } from '@/lib/queries/maal'

export const dynamic = 'force-dynamic'

export async function POST(req: Request) {
  const denied = await requireAuth('set the max position cap')
  if (denied) return denied

  let body: { code?: unknown; capPct?: unknown } = {}
  try {
    body = await req.json()
  } catch {
    // fall through to validation
  }
  const { code, capPct } = body
  if (typeof code !== 'string' || !(MAAL_CODES as readonly string[]).includes(code)) {
    return NextResponse.json({ error_code: 'bad_request', message: 'unknown portfolio code' }, { status: 400 })
  }
  if (typeof capPct !== 'number' || !Number.isFinite(capPct)) {
    return NextResponse.json({ error_code: 'bad_request', message: 'capPct must be a number' }, { status: 400 })
  }

  const saved = await setMaxCap(code as MaalCode, capPct)
  return NextResponse.json({ capPct: saved })
}
