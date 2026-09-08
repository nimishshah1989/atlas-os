// src/app/api/revalidate/route.ts — the publish step. Once every gate has passed, the box's
// orchestrator POSTs {"tag":"eod"} here with the shared bearer (GLOBAL_REVALIDATE_SECRET), and
// every page cached under that tag re-renders on its next request. The middleware lets this
// path through without a session (src/lib/supabase/paths.ts); the bearer is the only gate, and
// it is checked before the body is read. The secret is compared, never logged.
import { revalidateTag } from 'next/cache'
import { NextResponse } from 'next/server'
import { authorizeBearer, checkBody, TAG } from '@/lib/revalidate'

export async function POST(request: Request) {
  const auth = authorizeBearer(request.headers.get('authorization'), process.env.GLOBAL_REVALIDATE_SECRET)
  if (!auth.ok) return NextResponse.json({ error: auth.error }, { status: auth.status })
  const body = checkBody(await request.text())
  if (!body.ok) return NextResponse.json({ error: body.error }, { status: body.status })
  revalidateTag(TAG)
  return NextResponse.json({ revalidated: true, tag: TAG, at: new Date().toISOString() })
}
