// Task 3.4 — Act affordance: insert one pending proposed-change row.
// Direct DB write — no FastAPI proxy needed for a simple parameterized INSERT.
// Validates: UUIDs, positive weight. Returns Atlas error envelope on bad input.

import { NextRequest, NextResponse } from 'next/server'
import sql from '@/lib/db'

export const dynamic = 'force-dynamic'

// ---------------------------------------------------------------------------
// UUID validation
// ---------------------------------------------------------------------------

const UUID_RE =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i

function isUUID(s: unknown): s is string {
  return typeof s === 'string' && UUID_RE.test(s)
}

// ---------------------------------------------------------------------------
// DB row type
// ---------------------------------------------------------------------------

type ProposedChangeRow = {
  id: string
  status: string
}

// ---------------------------------------------------------------------------
// POST /api/portfolio/propose
// ---------------------------------------------------------------------------

export async function POST(req: NextRequest): Promise<NextResponse> {
  let body: Record<string, unknown>
  try {
    body = await req.json()
  } catch {
    return NextResponse.json(
      { error_code: 'bad_request', message: 'Request body must be valid JSON' },
      { status: 400 },
    )
  }

  const { portfolio_id, instrument_id, proposed_weight, rationale } = body

  // Validate portfolio_id
  if (portfolio_id === undefined || portfolio_id === null) {
    return NextResponse.json(
      { error_code: 'validation_error', message: 'portfolio_id is required' },
      { status: 400 },
    )
  }
  if (!isUUID(portfolio_id)) {
    return NextResponse.json(
      { error_code: 'validation_error', message: 'portfolio_id must be a valid UUID' },
      { status: 400 },
    )
  }

  // Validate instrument_id
  if (instrument_id === undefined || instrument_id === null) {
    return NextResponse.json(
      { error_code: 'validation_error', message: 'instrument_id is required' },
      { status: 400 },
    )
  }
  if (!isUUID(instrument_id)) {
    return NextResponse.json(
      { error_code: 'validation_error', message: 'instrument_id must be a valid UUID' },
      { status: 400 },
    )
  }

  // Validate proposed_weight: must be a positive number
  if (proposed_weight === undefined || proposed_weight === null) {
    return NextResponse.json(
      { error_code: 'validation_error', message: 'proposed_weight is required' },
      { status: 400 },
    )
  }
  const weightNum = Number(proposed_weight)
  if (isNaN(weightNum) || weightNum <= 0) {
    return NextResponse.json(
      {
        error_code: 'validation_error',
        message: 'proposed_weight must be a positive number',
      },
      { status: 400 },
    )
  }

  // Rationale is optional — accept null/undefined/string
  const rationaleVal: string | null =
    typeof rationale === 'string' ? rationale : null

  try {
    const rows = await sql<ProposedChangeRow[]>`
      INSERT INTO atlas.atlas_portfolio_proposed_change
        (portfolio_id, instrument_id, proposed_weight, status, rationale)
      VALUES
        (${portfolio_id}::uuid, ${instrument_id}::uuid, ${String(weightNum)}, 'pending', ${rationaleVal})
      RETURNING id::text, status
    `

    const row = rows[0]
    if (!row) {
      return NextResponse.json(
        { error_code: 'db_error', message: 'INSERT returned no rows' },
        { status: 500 },
      )
    }

    return NextResponse.json({ data: { id: row.id, status: row.status } }, { status: 201 })
  } catch (err) {
    const message = err instanceof Error ? err.message : 'Database error'
    return NextResponse.json(
      { error_code: 'db_error', message },
      { status: 500 },
    )
  }
}
