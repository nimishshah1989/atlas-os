// frontend/src/lib/queries/v6/policy_alerts.ts
//
// Policy is NOT a scored conviction lens (FM 2026-06-26). It surfaces as a RAG
// sector-policy ALERT on the stock detail page: which active government policies
// are a tailwind (or headwind) for this stock's sector, with a one-line description.
//
// Match logic mirrors the backend score_policy (_policy_matches): a policy applies
// when any beneficiary_sector bidirectionally substring-matches the stock's sector,
// or any beneficiary_keyword appears in the sector text. Single-schema: reads
// foundation_staging.policy_registry (mirrored by consolidate_tables.py).
import 'server-only'
import sql from '@/lib/db'

export type PolicyAlert = {
  policy_id: string
  policy_name: string
  description: string
  impact: string            // HIGH | MEDIUM | LOW
  stance: 'tailwind' | 'headwind'
  rag: 'green' | 'amber' | 'red'
}

type Row = {
  policy_id: string
  policy_name: string
  description: string | null
  impact: string | null
}

/** Active policies relevant to a stock's sector (tailwinds today; the registry
 *  currently holds beneficiary policies). Empty array when none apply. */
export async function getPolicyAlertsForStock(sector: string | null): Promise<PolicyAlert[]> {
  if (!sector) return []
  const rows = await sql<Row[]>`
    SELECT policy_id, policy_name, description, impact
    FROM foundation_staging.policy_registry
    WHERE is_active AND (
      -- Exact match always; loose bidirectional substring ONLY when the sector name is
      -- ≥4 chars — else short names like "IT" spuriously match "utIlities"/"capItal goods".
      EXISTS (
        SELECT 1 FROM jsonb_array_elements_text(beneficiary_sectors) bs
        WHERE lower(bs) = lower(${sector})
           OR (length(${sector}) >= 4 AND (
                 lower(bs) LIKE '%' || lower(${sector}) || '%'
              OR lower(${sector}) LIKE '%' || lower(bs) || '%'))
      )
      OR EXISTS (
        -- WORD-BOUNDARY match (\m…\M) — a plain LIKE '%api%' wrongly fires the Pharma
        -- "api" keyword on "cAPItal Markets". Keywords are curated (no regex metachars).
        SELECT 1 FROM jsonb_array_elements_text(beneficiary_keywords) bk
        WHERE length(${sector}) >= 4 AND lower(${sector}) ~ ('\m' || lower(bk) || '\M')
      )
    )
    ORDER BY CASE impact WHEN 'HIGH' THEN 1 WHEN 'MEDIUM' THEN 2 ELSE 3 END
    LIMIT 6
  `
  return rows.map((r): PolicyAlert => ({
    policy_id: r.policy_id,
    policy_name: r.policy_name,
    description: r.description ?? '',
    impact: r.impact ?? 'LOW',
    // The registry holds beneficiary (tailwind) policies today; RAG by impact.
    stance: 'tailwind',
    rag: r.impact === 'HIGH' ? 'green' : r.impact === 'MEDIUM' ? 'amber' : 'green',
  }))
}
