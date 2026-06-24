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
      (COALESCE((d_technical=10)::int,0)+COALESCE((d_fundamental=10)::int,0)+COALESCE((d_catalyst=10)::int,0)+COALESCE((d_flow=10)::int,0)) AS lead,
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

// ── Universe decile list (the /stocks funnel: leadership strip + 2×2 + table) ──
// The whole scored universe with per-lens deciles cut within cap cohort (D27), leadership,
// strength, compact RS (vs N500 + sector) and a ≈20-session turnover liquidity proxy. Returned
// unfiltered — the screen/filter/sort all run client-side on this single fetch (the universe
// is ~2k rows, well under what's worth re-querying per interaction; matches the pool budget).
export type StockListRow = {
  symbol: string; name: string | null; sector: string | null; cap: string
  d_tech: number | null; d_fund: number | null; d_cat: number | null; d_flow: number | null; d_val: number | null
  lead: number; strength: number | null
  rs_1m: number | null; rs_3m: number | null; rs_6m: number | null; rs_sector_3m: number | null
  ret_3m: number | null; liq_cr: number | null
}

export async function getLensAsOf(): Promise<string | null> {
  const r = await sql<{ d: string | null }[]>`
    SELECT to_char(max(date),'YYYY-MM-DD') AS d
    FROM foundation_staging.atlas_lens_scores_daily WHERE asset_class='stock'`
  return r[0]?.d ?? null
}

export async function getStocksDecileList(): Promise<StockListRow[]> {
  const rows = await sql<Record<string, string>[]>`
    WITH latest AS (SELECT max(date) d FROM foundation_staging.atlas_lens_scores_daily WHERE asset_class='stock'),
    tdl AS (SELECT max(date) d FROM foundation_staging.technical_daily),  -- RS/ret as-of; normally == the lens date (technicals computed first) and matches the detail RS-matrix basis

    cap AS (
      SELECT instrument_id,
        CASE WHEN bool_or(index_code='NIFTY 100') THEN 'large'
             WHEN bool_or(index_code='NIFTY MIDCAP 150') THEN 'mid'
             WHEN bool_or(index_code='NIFTY SMLCAP 250') THEN 'small' ELSE 'micro' END AS cap
      FROM foundation_staging.de_index_constituents
      WHERE effective_to IS NULL AND index_code IN ('NIFTY 100','NIFTY MIDCAP 150','NIFTY SMLCAP 250')
      GROUP BY instrument_id
    ),
    rs AS (
      SELECT instrument_id, rs_1m_n500, rs_3m_n500, rs_6m_n500, rs_3m_sector, ret_3m
      FROM foundation_staging.technical_daily
      WHERE asset_class='stock' AND date=(SELECT d FROM tdl)
    ),
    liq AS (  -- ≈20-session avg traded value (₹ Cr): a 30-calendar-day window ≈ 20 NSE sessions
      SELECT instrument_id, avg(close * volume) / 1e7 AS liq_cr
      FROM foundation_staging.ohlcv_stock
      WHERE date >= (SELECT d FROM tdl) - INTERVAL '30 days' AND close > 0 AND volume > 0
      GROUP BY instrument_id
    ),
    j AS (
      SELECT l.instrument_id, im.symbol, im.name, im.sector, COALESCE(c.cap,'micro') AS cap,
             l.technical::float t, l.fundamental::float f, l.catalyst::float ca, l.flow::float fl, l.valuation::float va
      FROM foundation_staging.atlas_lens_scores_daily l
      JOIN foundation_staging.instrument_master im ON im.instrument_id = l.instrument_id
      LEFT JOIN cap c ON c.instrument_id = l.instrument_id
      WHERE l.asset_class='stock' AND l.date=(SELECT d FROM latest)
    ),
    dec AS (
      SELECT instrument_id, symbol, name, sector, cap,
        CASE WHEN t  IS NULL THEN NULL ELSE ntile(10) OVER (PARTITION BY cap,(t  IS NULL) ORDER BY t)  END d_tech,
        CASE WHEN f  IS NULL THEN NULL ELSE ntile(10) OVER (PARTITION BY cap,(f  IS NULL) ORDER BY f)  END d_fund,
        CASE WHEN ca IS NULL THEN NULL ELSE ntile(10) OVER (PARTITION BY cap,(ca IS NULL) ORDER BY ca) END d_cat,
        CASE WHEN fl IS NULL THEN NULL ELSE ntile(10) OVER (PARTITION BY cap,(fl IS NULL) ORDER BY fl) END d_flow,
        CASE WHEN va IS NULL THEN NULL ELSE ntile(10) OVER (PARTITION BY cap,(va IS NULL) ORDER BY va) END d_val
      FROM j
    )
    SELECT d.symbol, d.name, d.sector, d.cap,
      d.d_tech, d.d_fund, d.d_cat, d.d_flow, d.d_val,
      (COALESCE((d.d_tech=10)::int,0) + COALESCE((d.d_fund=10)::int,0)
        + COALESCE((d.d_cat=10)::int,0) + COALESCE((d.d_flow=10)::int,0)) AS lead,  -- a NULL lens = not-top-decile (0), NOT a NULL-collapse of the whole sum
      ((COALESCE(d.d_tech,0)+COALESCE(d.d_fund,0)+COALESCE(d.d_cat,0)+COALESCE(d.d_flow,0))::float
        / NULLIF((d.d_tech IS NOT NULL)::int+(d.d_fund IS NOT NULL)::int+(d.d_cat IS NOT NULL)::int+(d.d_flow IS NOT NULL)::int,0)) AS strength,
      rs.rs_1m_n500, rs.rs_3m_n500, rs.rs_6m_n500, rs.rs_3m_sector, rs.ret_3m, liq.liq_cr
    FROM dec d
    LEFT JOIN rs  ON rs.instrument_id  = d.instrument_id
    LEFT JOIN liq ON liq.instrument_id = d.instrument_id
    ORDER BY strength DESC NULLS LAST
  `
  const n = (v: string | null) => (v == null ? null : toNumber(v))
  return rows.map(r => ({
    symbol: r.symbol, name: r.name, sector: r.sector, cap: r.cap,
    d_tech: n(r.d_tech), d_fund: n(r.d_fund), d_cat: n(r.d_cat), d_flow: n(r.d_flow), d_val: n(r.d_val),
    lead: toNumberOr(r.lead, 0), strength: n(r.strength),
    rs_1m: n(r.rs_1m_n500), rs_3m: n(r.rs_3m_n500), rs_6m: n(r.rs_6m_n500), rs_sector_3m: n(r.rs_3m_sector),
    ret_3m: n(r.ret_3m), liq_cr: n(r.liq_cr),
  }))
}
