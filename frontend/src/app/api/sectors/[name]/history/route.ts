import { NextRequest, NextResponse } from 'next/server'
import { getSectorMetricHistory } from '@/lib/queries/sectors'

export async function GET(
  req: NextRequest,
  { params }: { params: Promise<{ name: string }> },
) {
  const { name } = await params
  const daysParam = req.nextUrl.searchParams.get('days')
  const days = daysParam != null && /^\d+$/.test(daysParam)
    ? Math.min(Math.max(parseInt(daysParam, 10), 1), 3650)
    : 180
  try {
    const data = await getSectorMetricHistory(decodeURIComponent(name), days)
    return NextResponse.json(data)
  } catch (e) {
    const msg = e instanceof Error ? e.message : 'Query failed'
    return NextResponse.json({ error: msg }, { status: 500 })
  }
}
