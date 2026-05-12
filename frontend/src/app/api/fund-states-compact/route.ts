import { NextRequest, NextResponse } from 'next/server'
import sql from '@/lib/db'

export const dynamic = 'force-dynamic'

type FundStateRow = {
  date: Date
  nav_state: string | null
  composition_state: string | null
  holdings_state: string | null
}

export async function GET(req: NextRequest) {
  const { searchParams } = req.nextUrl
  const mstarId = searchParams.get('mstar_id')
  const rawDays = searchParams.get('days') ?? '180'
  const days = parseInt(rawDays, 10)

  if (!mstarId) {
    return NextResponse.json({ error: 'mstar_id required' }, { status: 400 })
  }
  if (isNaN(days) || days < 1 || days > 720) {
    return NextResponse.json({ error: 'days must be 1–720' }, { status: 400 })
  }

  const rows = await sql<FundStateRow[]>`
    SELECT date, nav_state, composition_state, holdings_state
    FROM atlas.atlas_fund_states_daily
    WHERE mstar_id = ${mstarId}
      AND date >= CURRENT_DATE - INTERVAL '1 day' * ${days}
    ORDER BY date ASC
  `
  return NextResponse.json({ rows })
}
