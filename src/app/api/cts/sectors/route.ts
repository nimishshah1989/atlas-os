import { NextResponse } from 'next/server'
import sql from '@/lib/db'

export const dynamic = 'force-dynamic'

type SectorPivotRow = {
  sector: string
  ppc_count: number
  npc_count: number
  total_tradeable: number
  pivot_balance: string | null
  stage2_count: number
  stage2_pct: string | null
  avg_ppc_conviction: string | null
  action_alert_count: number
}

export async function GET() {
  const rows = await sql<SectorPivotRow[]>`
    SELECT
      sector,
      ppc_count,
      npc_count,
      total_tradeable,
      pivot_balance::text   AS pivot_balance,
      stage2_count,
      stage2_pct::text      AS stage2_pct,
      avg_ppc_conviction::text AS avg_ppc_conviction,
      action_alert_count
    FROM atlas.atlas_cts_sector_pivot_daily
    WHERE date = (SELECT MAX(date) FROM atlas.atlas_cts_sector_pivot_daily)
    ORDER BY COALESCE(pivot_balance, -99) DESC
  `
  return NextResponse.json({ rows, as_of: new Date().toISOString() })
}
