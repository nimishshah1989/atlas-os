// GET /api/portfolios/baskets — active FM baskets for the add-to-basket dialog.
import { NextResponse } from 'next/server'
import { listBaskets } from '@/lib/queries/portfolios'

export const dynamic = 'force-dynamic'

export async function GET() {
  return NextResponse.json({ baskets: await listBaskets() })
}
