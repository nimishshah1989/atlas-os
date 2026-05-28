// frontend/src/app/api/portfolios/[id]/tv-export/route.ts
//
// TV-06: Next.js → FastAPI proxy for TradingView CSV export.
// The <a download> link in PortfolioAnalyticsClient points here so the
// browser can reach the FastAPI backend without knowing its host/port.

import { NextRequest, NextResponse } from 'next/server'
import 'server-only'

export const dynamic = 'force-dynamic'

type RouteParams = { params: Promise<{ id: string }> }

export async function GET(_req: NextRequest, { params }: RouteParams): Promise<NextResponse> {
  const { id } = await params

  const apiBase = process.env.ATLAS_INTERNAL_API_BASE_URL
  if (!apiBase) {
    return NextResponse.json({ error: 'ATLAS_INTERNAL_API_BASE_URL not set' }, { status: 500 })
  }
  const secret = process.env.ATLAS_INTERNAL_SECRET
  if (!secret) {
    return NextResponse.json({ error: 'ATLAS_INTERNAL_SECRET not set' }, { status: 500 })
  }

  const upstream = `${apiBase}/v1/portfolios/${encodeURIComponent(id)}/tv-export.csv`
  let res: Response
  try {
    res = await fetch(upstream, {
      headers: { Authorization: `Bearer ${secret}` },
      cache: 'no-store',
    })
  } catch {
    return NextResponse.json({ error: 'upstream_error' }, { status: 502 })
  }

  if (!res.ok) {
    return NextResponse.json({ error: 'not_found' }, { status: res.status })
  }

  const csvBytes = await res.arrayBuffer()
  return new NextResponse(csvBytes, {
    status: 200,
    headers: {
      'Content-Type': 'text/csv',
      'Content-Disposition': `attachment; filename=portfolio-${id}.csv`,
    },
  })
}
