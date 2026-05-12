// SP07 — Next.js → FastAPI proxy for specialist-agent invocations.
// Browser POSTs /api/agents/invoke; this route forwards to the
// internal_recompute service on the compute EC2, attaching the
// ATLAS_INTERNAL_SECRET bearer.
import { NextRequest, NextResponse } from 'next/server'

export const dynamic = 'force-dynamic'

const ALLOWED_ACTIONS = new Set(['invoke', 'list'])

async function forward(
  req: NextRequest,
  action: string,
  method: 'GET' | 'POST',
) {
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
  const secret = process.env.ATLAS_INTERNAL_SECRET ?? ''
  // FastAPI router lives at /api/agents (no /list/invoke suffix — the
  // shape is GET /api/agents for list, POST /api/agents/invoke for invoke).
  const path = action === 'list' ? '/api/agents' : '/api/agents/invoke'

  const init: RequestInit = {
    method,
    headers: {
      'Content-Type': 'application/json',
      ...(secret ? { Authorization: `Bearer ${secret}` } : {}),
    },
  }
  if (method === 'POST') {
    init.body = await req.text()
  }
  const upstream = await fetch(`${apiBase}${path}`, init)
  const text = await upstream.text()
  return new NextResponse(text, {
    status: upstream.status,
    headers: {
      'Content-Type': upstream.headers.get('Content-Type') ?? 'application/json',
    },
  })
}

export async function GET(
  req: NextRequest,
  { params }: { params: Promise<{ action: string }> },
) {
  const { action } = await params
  return forward(req, action, 'GET')
}

export async function POST(
  req: NextRequest,
  { params }: { params: Promise<{ action: string }> },
) {
  const { action } = await params
  return forward(req, action, 'POST')
}
