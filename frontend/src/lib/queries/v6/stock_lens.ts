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
  // RS values are return DIFFERENCES stored as fractions (0.131 = +13.1 percentage points);
  // the matrix renders + colours them as pp, so scale to pp here.
  const num = (v: string | null | undefined) => { const t = v == null ? null : toNumber(v); return t == null ? null : t * 100 }
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

// ── Real numbers behind the scores (the "deep dive": actual inputs, not just 0–100) ──
// Every value traces to a real source row (technical_daily / ohlcv_stock / delivery_daily /
// lens_shareholding / financials_quarterly) — RULE #0. Feeds the lens-card drill-down + VWAP.
export type StockEvidence = {
  as_of: string | null; close: number | null
  ema21: number | null; ema50: number | null; ema200: number | null; rsi: number | null
  dist_ema50: number | null; dist_ema200: number | null
  atr: number | null; bb_width: number | null; vol_ratio_30d: number | null; vol_ratio_60d: number | null; pos_52w: number | null
  rs_1m: number | null; rs_3m: number | null; rs_6m: number | null; rs_sector_3m: number | null
  vwap_252: number | null; vwap_dist: number | null
  delivery_pct: number | null; delivery_30d: number | null; delivery_60d: number | null; delivery_asym: number | null
  promoter_pct: number | null
  pe_ttm: number | null; eps_ttm: number | null
}

export async function getStockEvidence(symbol: string): Promise<StockEvidence | null> {
  const r = await sql<Record<string, string>[]>`
    WITH im AS (SELECT instrument_id FROM foundation_staging.instrument_master WHERE symbol = ${symbol} LIMIT 1),
    td AS (SELECT t.* FROM foundation_staging.technical_daily t, im
           WHERE t.instrument_id = im.instrument_id AND t.asset_class='stock' ORDER BY t.date DESC LIMIT 1),
    px AS (SELECT o.date, o.close FROM foundation_staging.ohlcv_stock o, im
           WHERE o.instrument_id = im.instrument_id AND o.close > 0 ORDER BY o.date DESC LIMIT 1),
    vw AS (SELECT sum(close*volume)/NULLIF(sum(volume),0) AS vwap_252
           FROM (SELECT o.close, o.volume FROM foundation_staging.ohlcv_stock o, im
                 WHERE o.instrument_id = im.instrument_id AND o.close > 0 AND o.volume > 0
                 ORDER BY o.date DESC LIMIT 252) z),
    dl AS (SELECT d.* FROM foundation_staging.delivery_daily d, im
           WHERE d.instrument_id = im.instrument_id ORDER BY d.date DESC LIMIT 1),
    sh AS (SELECT s.promoter_pct FROM foundation_staging.lens_shareholding s, im
           WHERE s.instrument_id = im.instrument_id ORDER BY s.period_end DESC LIMIT 1),
    fin AS (SELECT sum(eps) AS eps_ttm FROM (SELECT f.eps FROM foundation_staging.financials_quarterly f, im
            WHERE f.instrument_id = im.instrument_id AND f.consolidated ORDER BY f.period_end DESC LIMIT 4) q)
    SELECT to_char(px.date,'YYYY-MM-DD') AS as_of, px.close,
      td.ema_21, td.ema_50, td.ema_200, td.rsi_14, td.atr_14, td.bb_width,
      td.vol_ratio_30d, td.vol_ratio_60d, td.pos_52w,
      td.rs_1m_n500, td.rs_3m_n500, td.rs_6m_n500, td.rs_3m_sector,
      (px.close - td.ema_50)  / NULLIF(td.ema_50,0)  * 100 AS dist_ema50,
      (px.close - td.ema_200) / NULLIF(td.ema_200,0) * 100 AS dist_ema200,
      vw.vwap_252, (px.close - vw.vwap_252) / NULLIF(vw.vwap_252,0) * 100 AS vwap_dist,
      dl.delivery_pct, dl.delivery_avg_30d, dl.delivery_avg_60d, dl.delivery_updown_asym,
      sh.promoter_pct, fin.eps_ttm, px.close / NULLIF(fin.eps_ttm,0) AS pe_ttm
    FROM px LEFT JOIN td ON true LEFT JOIN vw ON true LEFT JOIN dl ON true LEFT JOIN sh ON true LEFT JOIN fin ON true`
  if (r.length === 0) return null
  const x = r[0]; const n = (k: string) => (x[k] == null ? null : toNumber(x[k]))
  return {
    as_of: x.as_of, close: n('close'),
    ema21: n('ema_21'), ema50: n('ema_50'), ema200: n('ema_200'), rsi: n('rsi_14'),
    dist_ema50: n('dist_ema50'), dist_ema200: n('dist_ema200'),
    atr: n('atr_14'), bb_width: n('bb_width'), vol_ratio_30d: n('vol_ratio_30d'), vol_ratio_60d: n('vol_ratio_60d'), pos_52w: n('pos_52w'),
    rs_1m: n('rs_1m_n500'), rs_3m: n('rs_3m_n500'), rs_6m: n('rs_6m_n500'), rs_sector_3m: n('rs_3m_sector'),
    vwap_252: n('vwap_252'), vwap_dist: n('vwap_dist'),
    delivery_pct: n('delivery_pct'), delivery_30d: n('delivery_avg_30d'), delivery_60d: n('delivery_avg_60d'), delivery_asym: n('delivery_updown_asym'),
    promoter_pct: n('promoter_pct'), pe_ttm: n('pe_ttm'), eps_ttm: n('eps_ttm'),
  }
}

// ── Last 8 quarters (Screener-style trend table) — XBRL financials_quarterly ──
export type StockQuarter = {
  period_end: string; revenue: number | null; ebitda: number | null; pat: number | null; eps: number | null
  ebitda_margin: number | null; net_margin: number | null; debt_equity: number | null
  rev_yoy: number | null; pat_yoy: number | null
}
export async function getStockFundamentals(symbol: string): Promise<StockQuarter[]> {
  const rows = await sql<Record<string, string>[]>`
    SELECT to_char(f.period_end,'YYYY-MM-DD') AS period_end,
      f.revenue, f.ebitda, f.pat, f.eps, f.ebitda_margin, f.net_margin, f.debt_equity_ratio
    FROM foundation_staging.financials_quarterly f
    JOIN foundation_staging.instrument_master im ON im.instrument_id = f.instrument_id
    WHERE im.symbol = ${symbol} AND f.consolidated
    ORDER BY f.period_end DESC LIMIT 12`
  const n = (v: string | null) => (v == null ? null : toNumber(v))
  const pct = (v: string | null) => { const t = v == null ? null : toNumber(v); return t == null ? null : t * 100 } // margins stored as fractions
  const q = rows.map(r => ({
    period_end: r.period_end, revenue: n(r.revenue), ebitda: n(r.ebitda), pat: n(r.pat), eps: n(r.eps),
    ebitda_margin: pct(r.ebitda_margin), net_margin: pct(r.net_margin), debt_equity: n(r.debt_equity_ratio),
  }))
  // YoY = quarter vs the same quarter a year ago (4 rows back, newest-first).
  const yoy = (cur: number | null, prior: number | null) =>
    cur == null || prior == null || prior === 0 ? null : (cur - prior) / Math.abs(prior) * 100
  return q.slice(0, 8).map((r, i) => ({
    ...r,
    rev_yoy: yoy(r.revenue, q[i + 4]?.revenue ?? null),
    pat_yoy: yoy(r.pat, q[i + 4]?.pat ?? null),
  }))
}

// ── Recent corporate announcements (replaces the empty TV "Top Stories") — lens_filings ──
export type StockFiling = {
  date: string; category: string | null; bucket: string | null; priority: string | null
  subject: string | null; url: string | null
}
export async function getStockAnnouncements(symbol: string, limit = 20): Promise<StockFiling[]> {
  const rows = await sql<Record<string, string>[]>`
    SELECT to_char(f.filing_date,'YYYY-MM-DD') AS date, f.category, f.category_bucket AS bucket,
           f.signal_priority AS priority, f.subject_text AS subject, f.source_url AS url
    FROM foundation_staging.lens_filings f
    JOIN foundation_staging.instrument_master im ON im.instrument_id = f.instrument_id
    WHERE im.symbol = ${symbol}
    ORDER BY f.filing_date DESC, f.nse_seq_id DESC LIMIT ${limit}`
  return rows.map(r => ({
    date: r.date, category: r.category, bucket: r.bucket, priority: r.priority, subject: r.subject, url: r.url,
  }))
}

// Minimal instrument header from foundation_staging (replaces the legacy atlas.* getStockBySymbol
// on the v4 detail path — keeps the page fs-only for the legacy retirement).
export type StockHeader = { instrument_id: string; symbol: string; name: string | null; sector: string | null }
export async function getStockHeader(symbol: string): Promise<StockHeader | null> {
  const r = await sql<StockHeader[]>`
    SELECT instrument_id::text AS instrument_id, symbol, name, sector
    FROM foundation_staging.instrument_master
    WHERE symbol = ${symbol} AND asset_class='stock' LIMIT 1`
  return r[0] ?? null
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
    tdl AS (SELECT max(date) d FROM foundation_staging.technical_daily WHERE asset_class='stock'),  -- RS/ret as-of (asset_class filter uses the class_date index — an unfiltered max(date) seq-scans 6.9M rows)

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
