// frontend/src/lib/queries/briefs.ts
// SP05 — server query for the latest Claude-authored daily brief.

import 'server-only'
import sql from '@/lib/db'

export type DailyBriefRow = {
  id: string
  as_of_date: Date
  regime_state: string
  regime_delta: string
  narrative: string
  key_themes: string[]
  regime_summary: string
  top_sector_mentions: string[]
  model: string
  prompt_version: string
  input_tokens: number | null
  output_tokens: number | null
  generated_at: Date
}

export async function getLatestBrief(): Promise<DailyBriefRow | null> {
  const rows = await sql<DailyBriefRow[]>`
    SELECT
      id, as_of_date, regime_state, regime_delta, narrative,
      key_themes, regime_summary, top_sector_mentions,
      model, prompt_version, input_tokens, output_tokens, generated_at
    FROM atlas.atlas_daily_briefs
    ORDER BY as_of_date DESC
    LIMIT 1
  `
  return rows[0] ?? null
}
