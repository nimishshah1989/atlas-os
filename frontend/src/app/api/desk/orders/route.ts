// POST /api/desk/orders — approve or reject a pending desk order from the board.
// The status flip is the ONLY write here; booking happens in desk_run's next
// settlement through the audited book_trade path (never from the frontend).
import { NextResponse } from 'next/server'

import sql from '@/lib/db'

export const dynamic = 'force-dynamic'

export async function POST(req: Request) {
  let body: { id?: unknown; action?: unknown } = {}
  try {
    body = await req.json()
  } catch {
    // fall through to validation
  }
  const id = body.id
  const action = body.action
  if (!Number.isInteger(id) || (action !== 'approve' && action !== 'reject')) {
    return NextResponse.json(
      { error_code: 'bad_request', message: 'id (int) + action approve|reject required' },
      { status: 400 },
    )
  }
  const status = action === 'approve' ? 'approved' : 'rejected'
  const rows = await sql`
    update atlas_foundation.desk_pending_orders
    set status = ${status}, decided_at = now(), decided_by = 'board'
    where id = ${id as number} and status = 'pending'
    returning id, symbol, status`
  if (rows.length === 0) {
    return NextResponse.json(
      { error_code: 'not_pending', message: 'order not found or already decided' },
      { status: 409 },
    )
  }
  return NextResponse.json(rows[0])
}
