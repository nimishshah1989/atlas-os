// Desk v2 approval queue — pending trade cards from atlas_foundation.desk_pending_orders.
// RULE #0: every number here is engine output (EXECUTION TRADER plan re-verified in code
// by desk_run) — this file only joins and formats.
import 'server-only'

import sql from '@/lib/db'

export type PendingOrder = {
  id: number
  portfolio: string
  cycleDate: string
  side: 'buy' | 'sell'
  symbol: string
  entryRef: number | null
  stop: number | null
  target: number | null
  rr: number | null
  planBasis: string | null
  thesis: string
  invalidation: string
}

export async function getPendingOrders(): Promise<PendingOrder[]> {
  const rows = await sql`
    select o.id, m.name as portfolio, o.cycle_date::text as cycle_date, o.side, o.symbol,
           o.entry_ref, o.stop, o.target, o.rr, o.plan_basis, o.thesis, o.invalidation
    from atlas_foundation.desk_pending_orders o
    join atlas_foundation.portfolio_master m using (portfolio_id)
    where o.status = 'pending'
    order by o.cycle_date desc, o.id`
  return rows.map((r) => ({
    id: Number(r.id),
    portfolio: String(r.portfolio),
    cycleDate: String(r.cycle_date),
    side: r.side as 'buy' | 'sell',
    symbol: String(r.symbol),
    entryRef: r.entry_ref === null ? null : Number(r.entry_ref),
    stop: r.stop === null ? null : Number(r.stop),
    target: r.target === null ? null : Number(r.target),
    rr: r.rr === null ? null : Number(r.rr),
    planBasis: r.plan_basis === null ? null : String(r.plan_basis),
    thesis: String(r.thesis),
    invalidation: String(r.invalidation),
  }))
}
