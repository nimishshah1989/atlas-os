// GET /api/instruments/insight?key=stock:BIOCON&benchmark=n50|n500
// The decision panel behind a picked instrument. Read-only, so no auth gate — same
// posture as the rest of the board's read routes.
import { NextResponse } from 'next/server'

import { getInstrumentInsight, type Benchmark } from '@/lib/queries/instrumentInsight'

export const dynamic = 'force-dynamic'

export async function GET(req: Request) {
  const url = new URL(req.url)
  const key = url.searchParams.get('key') ?? ''
  const benchmark: Benchmark = url.searchParams.get('benchmark') === 'n50' ? 'n50' : 'n500'

  if (!/^(stock|etf):[A-Za-z0-9&.\-]+$/.test(key)) {
    return NextResponse.json(
      { error_code: 'bad_request', message: 'key must be stock:SYMBOL or etf:SYMBOL' },
      { status: 400 },
    )
  }

  const insight = await getInstrumentInsight(key, benchmark)
  if (!insight) {
    return NextResponse.json({ error_code: 'not_found', message: 'unknown instrument' }, { status: 404 })
  }
  return NextResponse.json(insight)
}
