// src/lib/queries/v6/stock_lens.ts
// Native stock detail lens data — all from foundation_staging:
//  - getStockRSMatrix(): RS vs Nifty 50 / Nifty 500 / Sector across timeframes (technical_daily)
//  - getStockDecile(): the stock's per-lens DECILE (cut within cap cohort, universe-wide, D27)
//    + leadership + strength + raw lens scores + sub-components + evidence (for the drill-down)
import 'server-only'
import sql from '@/lib/db'
import { toNumber, toNumberOr } from '@/lib/v6/decimal'

// ── RS matrix ─────────────────────────────────────────────────────────────
export type RSMatrix = {
  as_of: string | null
  // [baseline][window] in pp
  rows: { baseline: string; cells: { window: string; v: number | null }[] }[]
}
const WINDOWS = ['1d', '1w', '1m', '3m', '6m', '12m']

export async function getStockRSMatrix(symbol: string): Promise<RSMatrix | null> {
  const r = await sql<Record<string, string>[]>`
    SELECT to_char(t.date,'YYYY-MM-DD') AS as_of,
           t.rs_1d_n50, t.rs_1w_n50, t.rs_1m_n50, t.rs_3m_n50, t.rs_6m_n50, t.rs_12m_n50,
           t.rs_1d_n500, t.rs_1w_n500, t.rs_1m_n500, t.rs_3m_n500, t.rs_6m_n500, t.rs_12m_n500,
           t.rs_1m_sector, t.rs_3m_sector, t.rs_6m_sector, t.rs_12m_sector
    FROM foundation_staging.technical_daily t
    JOIN foundation_staging.instrument_master im ON im.instrument_id = t.instrument_id
    WHERE im.symbol = ${symbol} AND t.asset_class='stock'
    ORDER BY t.date DESC LIMIT 1
  `
  if (r.length === 0) return null
  const x = r[0]
  const num = (v: string | null | undefined) => (v == null ? null : toNumber(v))
  const cells = (prefix: string, windows: string[]) =>
    windows.map(w => ({ window: w.toUpperCase(), v: num(x[`rs_${w}_${prefix}`]) }))
  return {
    as_of: x.as_of,
    rows: [
      { baseline: 'Nifty 50', cells: cells('n50', WINDOWS) },
      { baseline: 'Nifty 500', cells: cells('n500', WINDOWS) },
      { baseline: 'Sector', cells: cells('sector', ['1m', '3m', '6m', '12m']) },
    ],
  }
}

// ── Chart series (price + RS ratios) for our Lightweight EMA charts ───────
export type StockChartRow = {
  date: string
  close: string | null
  rs_n50: string | null   // close ÷ Nifty 50
  rs_n500: string | null  // close ÷ Nifty 500
}

export async function getStockChartSeries(symbol: string, years = 5): Promise<StockChartRow[]> {
  return sql<StockChartRow[]>`
    SELECT to_char(o.date,'YYYY-MM-DD') AS date, o.close::text,
           (o.close / NULLIF(n50.close, 0))::text  AS rs_n50,
           (o.close / NULLIF(n500.close, 0))::text AS rs_n500
    FROM foundation_staging.ohlcv_stock o
    JOIN foundation_staging.instrument_master im ON im.instrument_id = o.instrument_id
    LEFT JOIN foundation_staging.index_prices n50  ON n50.date = o.date  AND n50.index_code = 'NIFTY 50'
    LEFT JOIN foundation_staging.index_prices n500 ON n500.date = o.date AND n500.index_code = 'NIFTY 500'
    WHERE im.symbol = ${symbol} AND o.close > 0
      AND o.date >= NOW() - (${years} || ' years')::INTERVAL
    ORDER BY o.date ASC
  `
}

// ── Decile card + sub-components + evidence ───────────────────────────────
export type StockDecile = {
  symbol: string; name: string | null; sector: string | null; cap: string
  lens: { key: string; label: string; score: number | null; decile: number | null; subs: { label: string; v: number | null }[] }[]
  lead: number; strength: number | null
  evidence: unknown
}

const SUBS: Record<string, [string, string][]> = {
  technical: [['tech_trend', 'Trend'], ['tech_rs', 'Rel. strength'], ['tech_vol_contraction', 'Vol contraction'], ['tech_volume', 'Volume']],
  fundamental: [['fund_profitability', 'Profitability'], ['fund_margin', 'Margin'], ['fund_growth', 'Growth'], ['fund_balance_sheet', 'Balance sheet']],
  valuation: [['val_pe_vs_sector', 'PE vs sector'], ['val_absolute_pe', 'Absolute PE'], ['val_pb', 'P/B'], ['val_52w_position', '52w position']],
  catalyst: [['cat_earnings_strategy', 'Earnings'], ['cat_capital_action', 'Capital action'], ['cat_governance', 'Governance']],
  flow: [['flow_promoter', 'Promoter'], ['flow_institutional', 'Institutional'], ['flow_smart_money', 'Smart money'], ['flow_accumulation', 'Accumulation (delivery)']],
  policy: [['policy_tailwind', 'Sector tailwind']],
}
const LENS_LABEL: Record<string, string> = {
  technical: 'Technical', fundamental: 'Fundamental', valuation: 'Valuation',
  catalyst: 'Catalyst', flow: 'Flow', policy: 'Policy',
}
const SUB_COLS = Object.values(SUBS).flat().map(([c]) => c)

export async function getStockDecile(symbol: string): Promise<StockDecile | null> {
  const rows = await sql<Record<string, string>[]>`
    WITH latest AS (SELECT max(date) d FROM foundation_staging.atlas_lens_scores_daily WHERE asset_class='stock'),
    cap AS (
      SELECT instrument_id,
        CASE WHEN bool_or(index_code='NIFTY 100') THEN 'large'
             WHEN bool_or(index_code='NIFTY MIDCAP 150') THEN 'mid'
             WHEN bool_or(index_code='NIFTY SMLCAP 250') THEN 'small' ELSE 'micro' END AS cap
      FROM foundation_staging.de_index_constituents
      WHERE effective_to IS NULL AND index_code IN ('NIFTY 100','NIFTY MIDCAP 150','NIFTY SMLCAP 250')
      GROUP BY instrument_id
    ),
    j AS (
      SELECT l.*, im.symbol, im.name, im.sector, COALESCE(c.cap,'micro') AS cap,
             l.technical::float t, l.fundamental::float f, l.catalyst::float ca, l.flow::float fl, l.valuation::float va
      FROM foundation_staging.atlas_lens_scores_daily l
      JOIN foundation_staging.instrument_master im ON im.instrument_id = l.instrument_id
      LEFT JOIN cap c ON c.instrument_id = l.instrument_id
      WHERE l.asset_class='stock' AND l.date=(SELECT d FROM latest)
    ),
    dec AS (
      SELECT *,
        CASE WHEN t  IS NULL THEN NULL ELSE ntile(10) OVER (PARTITION BY cap,(t  IS NULL) ORDER BY t)  END d_technical,
        CASE WHEN f  IS NULL THEN NULL ELSE ntile(10) OVER (PARTITION BY cap,(f  IS NULL) ORDER BY f)  END d_fundamental,
        CASE WHEN ca IS NULL THEN NULL ELSE ntile(10) OVER (PARTITION BY cap,(ca IS NULL) ORDER BY ca) END d_catalyst,
        CASE WHEN fl IS NULL THEN NULL ELSE ntile(10) OVER (PARTITION BY cap,(fl IS NULL) ORDER BY fl) END d_flow,
        CASE WHEN va IS NULL THEN NULL ELSE ntile(10) OVER (PARTITION BY cap,(va IS NULL) ORDER BY va) END d_valuation
      FROM j
    )
    SELECT symbol, name, sector, cap,
      technical, fundamental, valuation, catalyst, flow, policy,
      d_technical, d_fundamental, d_valuation, d_catalyst, d_flow,
      ${sql(SUB_COLS)}, evidence,
      ((d_technical=10)::int+(d_fundamental=10)::int+(d_catalyst=10)::int+(d_flow=10)::int) AS lead,
      ((COALESCE(d_technical,0)+COALESCE(d_fundamental,0)+COALESCE(d_catalyst,0)+COALESCE(d_flow,0))::float
        / NULLIF((d_technical IS NOT NULL)::int+(d_fundamental IS NOT NULL)::int+(d_catalyst IS NOT NULL)::int+(d_flow IS NOT NULL)::int,0)) AS strength
    FROM dec WHERE symbol = ${symbol} LIMIT 1
  `
  if (rows.length === 0) return null
  const x = rows[0]
  const num = (v: string | null | undefined) => (v == null ? null : toNumber(v))
  const lens = Object.keys(SUBS).map(key => ({
    key, label: LENS_LABEL[key],
    score: num(x[key]),
    decile: num(x[`d_${key}`]),
    subs: SUBS[key].map(([col, label]) => ({ label, v: num(x[col]) })),
  }))
  return {
    symbol: x.symbol, name: x.name, sector: x.sector, cap: x.cap, lens,
    lead: toNumberOr(x.lead, 0), strength: num(x.strength),
    evidence: parseEvidence(x.evidence),
  }
}

// JSONB usually arrives pre-parsed from the driver; guard the string case so a malformed
// evidence payload renders as "no evidence" rather than crashing the page.
function parseEvidence(e: unknown): unknown {
  if (e == null) return null
  if (typeof e !== 'string') return e
  try { return JSON.parse(e) } catch { return null }
}
