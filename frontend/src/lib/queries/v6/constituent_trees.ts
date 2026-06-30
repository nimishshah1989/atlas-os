// Per-constituent lens + sub-component scores — powers the recursive DRILL-TO-ATOM: on a
// sector / fund / ETF tree, a constituent stock expands INLINE into its own lens→sub-component
// mini-tree (no navigation), built from the stored sub-component columns in
// atlas_lens_scores_daily (tech_trend, fund_profitability, flow_promoter, …). One indexed query
// for all the constituents shown on the page.
import 'server-only'
import sql from '@/lib/db'

// Every score is 0–100 (or null when the lens/sub-component wasn't computed). Indexable by column
// name so the builder can read sub-components generically; `symbol` is the only string field.
export type ConstituentLens = { symbol: string; [col: string]: number | null | string }

const COLS = [
  'composite', 'technical', 'fundamental', 'catalyst', 'flow', 'valuation', 'policy',
  'tech_trend', 'tech_rs', 'tech_vol_contraction', 'tech_volume',
  'fund_profitability', 'fund_margin', 'fund_growth', 'fund_balance_sheet', 'fund_op_leverage',
  'cat_earnings_strategy', 'cat_capital_action', 'cat_governance',
  'flow_promoter', 'flow_institutional', 'flow_smart_money', 'flow_accumulation',
  'val_pe_vs_sector', 'val_absolute_pe', 'val_pb', 'val_ev_ebitda', 'val_52w_position',
] as const

export async function getConstituentLensTrees(symbols: string[]): Promise<Record<string, ConstituentLens>> {
  const uniq = Array.from(new Set(symbols.filter(Boolean)))
  if (uniq.length === 0) return {}
  const rows = (await sql.unsafe(
    `SELECT im.symbol, ${COLS.map((c) => `l.${c}::float AS ${c}`).join(', ')}
     FROM foundation_staging.atlas_lens_scores_daily l
     JOIN foundation_staging.instrument_master im ON im.instrument_id = l.instrument_id
     WHERE l.asset_class='stock'
       AND l.date = (SELECT max(date) FROM foundation_staging.atlas_lens_scores_daily WHERE asset_class='stock')
       AND im.symbol = ANY($1)`,
    [uniq],
  )) as unknown as Record<string, number | string | null>[]

  const out: Record<string, ConstituentLens> = {}
  for (const r of rows) {
    const sym = String(r.symbol)
    const c: ConstituentLens = { symbol: sym }
    for (const col of COLS) {
      const v = r[col]
      c[col] = v == null ? null : Number(v)
    }
    out[sym] = c
  }
  return out
}
