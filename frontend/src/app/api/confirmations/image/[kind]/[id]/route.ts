// GET /api/confirmations/image/call|evidence/<id> — serve an attached chart.
// no-store: drafts mutate, and a cached stale chart on a published report would
// be worse than a slow one.
import { NextResponse } from 'next/server'

import { getCallImage, getEvidenceImage } from '@/lib/queries/confirmations'

export const dynamic = 'force-dynamic'

export async function GET(_req: Request, ctx: { params: Promise<{ kind: string; id: string }> }) {
  const { kind, id } = await ctx.params
  const numericId = Number(id)
  if (!Number.isInteger(numericId) || numericId <= 0 || (kind !== 'call' && kind !== 'evidence')) {
    return NextResponse.json({ error_code: 'bad_request', message: 'bad image reference' }, { status: 400 })
  }

  const img = kind === 'call' ? await getCallImage(numericId) : await getEvidenceImage(numericId)
  if (!img) return NextResponse.json({ error_code: 'not_found', message: 'no chart attached' }, { status: 404 })

  return new NextResponse(new Uint8Array(img.bytes), {
    headers: { 'Content-Type': img.mime, 'Cache-Control': 'private, no-store' },
  })
}
