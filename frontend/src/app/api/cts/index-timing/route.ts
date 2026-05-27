import { NextResponse } from 'next/server'
import sql from '@/lib/db'

export const dynamic = 'force-dynamic'

type IndexTimingRow = {
  index_name: string
  plus_a: number
  plus_b: number
  neutral: number
  minus_b: number
  minus_a: number
  total: number
}

export async function GET() {
  const rows = await sql<IndexTimingRow[]>`
    WITH latest AS (
      SELECT instrument_id, stage, is_npc, cts_action_confidence
      FROM atlas.atlas_cts_signals_daily
      WHERE date = (SELECT MAX(date) FROM atlas.atlas_cts_signals_daily)
    ),
    graded AS (
      SELECT
        u.in_nifty_50,
        u.in_nifty_100,
        u.in_nifty_500,
        CASE
          WHEN l.cts_action_confidence = true                        THEN 'plus_a'
          WHEN l.stage = 2                                           THEN 'plus_b'
          WHEN l.stage = 4 OR (l.stage = 3 AND l.is_npc = true)    THEN 'minus_a'
          WHEN l.stage = 3                                           THEN 'minus_b'
          ELSE 'neutral'
        END AS grade
      FROM atlas.atlas_universe_stocks u
      LEFT JOIN latest l ON l.instrument_id = u.instrument_id
    )
    SELECT
      idx.name                                                   AS index_name,
      COUNT(*) FILTER (WHERE grade = 'plus_a')::int             AS plus_a,
      COUNT(*) FILTER (WHERE grade = 'plus_b')::int             AS plus_b,
      COUNT(*) FILTER (WHERE grade = 'neutral')::int            AS neutral,
      COUNT(*) FILTER (WHERE grade = 'minus_b')::int            AS minus_b,
      COUNT(*) FILTER (WHERE grade = 'minus_a')::int            AS minus_a,
      COUNT(*)::int                                              AS total
    FROM graded
    CROSS JOIN (VALUES
      ('Nifty 50',      'n50'),
      ('Nifty 100',     'n100'),
      ('Nifty 500',     'n500'),
      ('All Tradeable', 'all')
    ) AS idx(name, key)
    WHERE (idx.key = 'n50'  AND in_nifty_50  = true)
       OR (idx.key = 'n100' AND in_nifty_100 = true)
       OR (idx.key = 'n500' AND in_nifty_500 = true)
       OR  idx.key = 'all'
    GROUP BY idx.name, idx.key
    ORDER BY ARRAY_POSITION(ARRAY['n50','n100','n500','all'], idx.key)
  `
  return NextResponse.json({ rows, as_of: new Date().toISOString() })
}
