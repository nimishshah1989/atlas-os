import { NextRequest, NextResponse } from 'next/server'
import sql from '@/lib/db'

export const dynamic = 'force-dynamic'

type StateRow = { date: Date; rs_state: string | null; momentum_state: string | null; risk_state: string | null; volume_state: string | null }

export async function GET(req: NextRequest) {
  const { searchParams } = req.nextUrl
  const symbol = searchParams.get('symbol')
  const ticker = searchParams.get('ticker')
  const rawDays = searchParams.get('days') ?? '90'
  const days = parseInt(rawDays, 10)

  if (isNaN(days) || days < 1 || days > 365) {
    return NextResponse.json({ error: 'days must be 1–365' }, { status: 400 })
  }

  if (!symbol && !ticker) {
    return NextResponse.json({ error: 'symbol or ticker required' }, { status: 400 })
  }

  if (symbol) {
    const rows = await sql<StateRow[]>`
      SELECT s.date, s.rs_state, s.momentum_state, s.risk_state, s.volume_state
      FROM atlas.atlas_stock_states_daily s
      JOIN atlas.atlas_universe_stocks u ON u.instrument_id = s.instrument_id
      WHERE u.symbol = ${symbol}
        AND u.effective_to IS NULL
        AND s.date >= CURRENT_DATE - (${days} || ' days')::interval
      ORDER BY s.date ASC
    `
    return NextResponse.json({ rows })
  }

  const rows = await sql<StateRow[]>`
    SELECT date, rs_state, momentum_state, risk_state, volume_state
    FROM atlas.atlas_etf_states_daily
    WHERE ticker = ${ticker!}
      AND date >= CURRENT_DATE - (${days} || ' days')::interval
    ORDER BY date ASC
  `
  return NextResponse.json({ rows })
}
