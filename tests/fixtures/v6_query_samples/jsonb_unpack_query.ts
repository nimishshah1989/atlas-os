// Fixture: query using JSONB unpack — the function argument is a column,
// not a table reference. The audit must NOT flag this as a missing table.
// Used by test_v6_data_availability_audit.py Case 3.

import sql from '@/lib/db'

export async function getFundHoldings(schemeCode: string) {
  const rows = await sql`
    SELECT
      s.scheme_code,
      h.isin,
      h.weight_pct
    FROM atlas.atlas_fund_scorecard s
    CROSS JOIN LATERAL jsonb_to_recordset(s.top_holdings)
      AS h(isin text, weight_pct numeric, company_name text)
    WHERE s.scheme_code = ${schemeCode}
  `
  return rows
}
