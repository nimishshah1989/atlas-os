// POST /api/portfolio/create
// Minimal portfolio creation: name + instrument_universe.
// Inserts a new row into atlas.strategy_fm_custom_portfolios with an empty
// instruments JSONB array. The user adds holdings later from the portfolio
// detail page (/portfolios/[id]).
//
// Conventions match /api/portfolio/propose/route.ts:
//   force-dynamic, NextRequest/NextResponse, parameterized sql, Atlas error envelope.

import { NextRequest, NextResponse } from 'next/server'
import sql from '@/lib/db'

export const dynamic = 'force-dynamic'

// ---------------------------------------------------------------------------
// Allowed instrument universe values (whitelist)
// ---------------------------------------------------------------------------

const VALID_UNIVERSES = new Set(['direct_equity', 'etf', 'mutual_fund', 'mixed'])

// ---------------------------------------------------------------------------
// DB row type
// ---------------------------------------------------------------------------

type CreatedPortfolioRow = {
  id: string
  name: string
}

// ---------------------------------------------------------------------------
// POST /api/portfolio/create
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

  const { name, instrument_universe } = body

  // Validate name
  if (!name || typeof name !== 'string' || !name.trim()) {
    return NextResponse.json(
      { error_code: 'validation_error', message: 'name is required' },
      { status: 400 },
    )
  }

  const trimmedName = name.trim()

  // Validate instrument_universe (optional; defaults to 'direct_equity')
  const universe =
    typeof instrument_universe === 'string' && VALID_UNIVERSES.has(instrument_universe)
      ? instrument_universe
      : 'direct_equity'

  try {
    const rows = await sql<CreatedPortfolioRow[]>`
      INSERT INTO atlas.strategy_fm_custom_portfolios
        (name, instruments)
      VALUES
        (${trimmedName}, ${'[]'}::jsonb)
      RETURNING id::text, name
    `

    const row = rows[0]
    if (!row) {
      return NextResponse.json(
        { error_code: 'db_error', message: 'INSERT returned no rows' },
        { status: 500 },
      )
    }

    return NextResponse.json(
      { data: { id: row.id, name: row.name, instrument_universe: universe } },
      { status: 201 },
    )
  } catch (err) {
    const message = err instanceof Error ? err.message : 'Database error'
    // Surface unique-constraint violation as a user-readable message
    if (message.includes('unique') || message.includes('duplicate')) {
      return NextResponse.json(
        { error_code: 'validation_error', message: 'A portfolio with this name already exists' },
        { status: 409 },
      )
    }
    return NextResponse.json({ error_code: 'db_error', message }, { status: 500 })
  }
}
