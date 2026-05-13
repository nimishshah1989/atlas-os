// SP08/SP10 — Next.js → FastAPI proxy for intraday endpoints.
import { NextRequest, NextResponse } from 'next/server'

export const dynamic = 'force-dynamic'

const ALLOWED = new Set(['rs-leaders', 'status', 'nifty', 'sector-movers', 'prices'])

export async function GET(req: NextRequest): Promise<NextResponse> {
  const apiBase = process.env.ATLAS_INTERNAL_API_BASE_URL
  if (!apiBase) {
    return NextResponse.json(
      { error: 'ATLAS_INTERNAL_API_BASE_URL not set' },
      { status: 500 },
    )
  }
  const secret = process.env.ATLAS_INTERNAL_SECRET ?? ''

  const { searchParams } = new URL(req.url)
  const endpoint = searchParams.get('endpoint') ?? 'rs-leaders'

  if (!ALLOWED.has(endpoint)) {
    return NextResponse.json({ error: 'unknown endpoint' }, { status: 400 })
  }

  // Forward all query params except 'endpoint' to upstream
  const upstreamParams = new URLSearchParams()
  for (const [k, v] of searchParams.entries()) {
    if (k !== 'endpoint') upstreamParams.set(k, v)
  }
  const paramStr = upstreamParams.toString()
  const path = `/api/v1/intraday/${endpoint}${paramStr ? '?' + paramStr : ''}`

  const upstream = await fetch(`${apiBase}${path}`, {
    headers: { ...(secret ? { Authorization: `Bearer ${secret}` } : {}) },
    next: { revalidate: 30 },
  })
  const text = await upstream.text()
  return new NextResponse(text, {
    status: upstream.status,
    headers: {
      'Content-Type': upstream.headers.get('Content-Type') ?? 'application/json',
    },
  })
}
