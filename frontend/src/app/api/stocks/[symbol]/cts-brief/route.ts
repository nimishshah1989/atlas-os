import { NextRequest, NextResponse } from 'next/server'

export const dynamic = 'force-dynamic'

export async function POST(
  _req: NextRequest,
  { params }: { params: Promise<{ symbol: string }> },
) {
  const { symbol } = await params
  const apiBase = process.env.ATLAS_INTERNAL_API_BASE_URL
  if (!apiBase) {
    return NextResponse.json(
      { error: 'ATLAS_INTERNAL_API_BASE_URL not configured' },
      { status: 500 },
    )
  }
  const secret = process.env.ATLAS_INTERNAL_SECRET ?? ''
  const upstream = await fetch(
    `${apiBase}/api/v1/stocks/${encodeURIComponent(symbol)}/cts_brief`,
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(secret ? { Authorization: `Bearer ${secret}` } : {}),
      },
    },
  )
  const text = await upstream.text()
  return new NextResponse(text, {
    status: upstream.status,
    headers: {
      'Content-Type': upstream.headers.get('Content-Type') ?? 'application/json',
    },
  })
}
