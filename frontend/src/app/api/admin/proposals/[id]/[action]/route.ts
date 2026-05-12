// SP04 Stage 4a — Next.js → FastAPI proxy for proposal admin actions.
// The browser-side ProposalActionBar fetches /api/admin/proposals/{id}/{action}
// on the Next.js host; this route forwards the body to the FastAPI app at
// ATLAS_INTERNAL_API_BASE_URL so the persistence transaction runs there.
import { NextRequest, NextResponse } from 'next/server'

export const dynamic = 'force-dynamic'

const ALLOWED_ACTIONS = new Set(['approve', 'reject', 'snooze'])

export async function POST(
  req: NextRequest,
  { params }: { params: Promise<{ id: string; action: string }> },
) {
  const { id, action } = await params
  if (!ALLOWED_ACTIONS.has(action)) {
    return NextResponse.json(
      { error: `action must be one of ${[...ALLOWED_ACTIONS].join(', ')}` },
      { status: 400 },
    )
  }
  const apiBase = process.env.ATLAS_INTERNAL_API_BASE_URL
  if (!apiBase) {
    return NextResponse.json(
      { error: 'ATLAS_INTERNAL_API_BASE_URL not set on frontend host' },
      { status: 500 },
    )
  }

  const body = await req.text()
  const upstream = await fetch(`${apiBase}/api/admin/proposals/${id}/${action}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body,
  })
  const text = await upstream.text()
  return new NextResponse(text, {
    status: upstream.status,
    headers: { 'Content-Type': upstream.headers.get('Content-Type') ?? 'application/json' },
  })
}
