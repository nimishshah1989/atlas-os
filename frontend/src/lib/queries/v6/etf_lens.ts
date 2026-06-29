// src/lib/queries/v6/etf_lens.ts
// Native ETF lens roll-up — all from foundation_staging. ETFs are a holdings-weighted roll-up
// of the stock atom (D26/D27): the headline is LEADERSHIP-BREADTH (% of holdings weight that are
// top-decile leaders in ≥2 conviction lenses), NOT a cap-weighted composite. Plus the
// holdings-weighted 6-lens vector (descriptive) and a look-through to each holding's deciles.
//
// IDENTITY: the ETF universe is de_mf_master (Morningstar, is_etf) — fund_name / category /
// expense / ISIN. Holdings look-through is de_etf_holdings.ticker (= de_mf_master.mstar_id) →
// instrument_id → the lens journal (99.5% covered). The ETF's own NSE price ticker (for the TV
// chart) is bridged by a DETERMINISTIC normalized-name join to instrument_master ETF rows
// (UPPER + strip-non-alnum), since neither price table carries the ISIN. ~65% of NSE equity ETFs
// match a priced NSE ticker; the rest render lens-core only (no fabricated price — RULE #0).
import 'server-only'
import sql from '@/lib/db'
import { toNumber, toNumberOr } from '@/lib/v6/decimal'
import type { StockChartRow } from './stock_lens'

// ── ETF price + RS series for the native Lightweight charts (price ÷ Nifty 50/500) ──
// Reuses the StockChartRow shape so the stock-detail StockPriceEMAChart / StockRSChart render
// it directly. From ohlcv_etf (keyed by the bridged NSE ticker) — TV's Advanced-Chart embed
// refuses NSE symbols, so we draw our own (the FM-confirmed "comes out really well" path).
export async function getEtfChartSeries(nseTicker: string, years = 5): Promise<StockChartRow[]> {
  return sql<StockChartRow[]>`
    SELECT to_char(o.date,'YYYY-MM-DD') AS date, o.close::text,
           (o.close / NULLIF(n50.close, 0))::text  AS rs_n50,
           (o.close / NULLIF(n500.close, 0))::text AS rs_n500
    FROM foundation_staging.ohlcv_etf o
    LEFT JOIN foundation_staging.index_prices n50  ON n50.date = o.date  AND n50.index_code = 'NIFTY 50'
    LEFT JOIN foundation_staging.index_prices n500 ON n500.date = o.date AND n500.index_code = 'NIFTY 500'
    WHERE o.ticker = ${nseTicker} AND o.close > 0
      AND o.date >= NOW() - (${years} || ' years')::INTERVAL
    ORDER BY o.date ASC
  `
}

// Per-stock scored CTE (deciles within cap cohort, leadership, strength, raw lens subscores, RS).
// No user input — all literals; shared by the ETF + fund roll-ups via sql.unsafe.
export const SCORED_STOCKS = `
  latest AS (SELECT max(date) d FROM foundation_staging.atlas_lens_scores_daily WHERE asset_class='stock'),
  tdl AS (SELECT max(date) d FROM foundation_staging.technical_daily WHERE asset_class='stock'),  -- asset_class filter uses the class_date index (unfiltered max(date) seq-scans 6.9M rows)
  cap AS (
    SELECT instrument_id,
      CASE WHEN bool_or(index_code='NIFTY 100') THEN 'large'
           WHEN bool_or(index_code='NIFTY MIDCAP 150') THEN 'mid'
           WHEN bool_or(index_code='NIFTY SMLCAP 250') THEN 'small' ELSE 'micro' END AS cap
    FROM foundation_staging.de_index_constituents
    WHERE effective_to IS NULL AND index_code IN ('NIFTY 100','NIFTY MIDCAP 150','NIFTY SMLCAP 250')
    GROUP BY instrument_id),
  rs AS (SELECT instrument_id, rs_3m_n500, rs_1m_n500, ret_1d, ret_1w, ret_1m FROM foundation_staging.technical_daily
         WHERE asset_class='stock' AND date=(SELECT d FROM tdl)),
  j AS (
    SELECT l.instrument_id, im.symbol, COALESCE(c.cap,'micro') AS cap,
           l.technical::float t, l.fundamental::float f, l.catalyst::float ca, l.flow::float fl, l.valuation::float va
    FROM foundation_staging.atlas_lens_scores_daily l
    JOIN foundation_staging.instrument_master im ON im.instrument_id = l.instrument_id
    LEFT JOIN cap c ON c.instrument_id = l.instrument_id
    WHERE l.asset_class='stock' AND l.date=(SELECT d FROM latest)),
  dec AS (
    SELECT instrument_id, symbol, cap, t, f, ca, fl, va,
      CASE WHEN t  IS NULL THEN NULL ELSE ntile(10) OVER (PARTITION BY cap,(t  IS NULL) ORDER BY t)  END d_tech,
      CASE WHEN f  IS NULL THEN NULL ELSE ntile(10) OVER (PARTITION BY cap,(f  IS NULL) ORDER BY f)  END d_fund,
      CASE WHEN ca IS NULL THEN NULL ELSE ntile(10) OVER (PARTITION BY cap,(ca IS NULL) ORDER BY ca) END d_cat,
      CASE WHEN fl IS NULL THEN NULL ELSE ntile(10) OVER (PARTITION BY cap,(fl IS NULL) ORDER BY fl) END d_flow,
      CASE WHEN va IS NULL THEN NULL ELSE ntile(10) OVER (PARTITION BY cap,(va IS NULL) ORDER BY va) END d_val
    FROM j),
  scored AS (
    SELECT d.instrument_id, d.symbol, d.cap, d.t, d.f, d.ca, d.fl, d.va,
      d.d_tech, d.d_fund, d.d_cat, d.d_flow, d.d_val,
      -- LEADER = top-2-decile (D9/D10) in BOTH active conviction lenses (Technical & Flow). lead is
      -- 0..2; a leader has lead = 2. (FM 2-lens model: Fundamental/Catalyst weight 0, so they no
      -- longer count toward leadership.) Roll-ups filter on lead >= 2 = leads both active lenses.
      (COALESCE((d.d_tech>=9)::int,0)+COALESCE((d.d_flow>=9)::int,0)) AS lead,
      -- strength = mean of the ACTIVE-lens deciles (Technical & Flow), matching the 2-lens conviction.
      ((COALESCE(d.d_tech,0)+COALESCE(d.d_flow,0))::float
        / NULLIF((d.d_tech IS NOT NULL)::int+(d.d_flow IS NOT NULL)::int,0)) AS strength,
      rs.rs_1m_n500, rs.rs_3m_n500, rs.ret_1d, rs.ret_1w, rs.ret_1m
    FROM dec d LEFT JOIN rs ON rs.instrument_id = d.instrument_id),
  etf_nse AS (  -- deterministic ETF identity bridge: Morningstar fund_name ⇄ NSE instrument name.
                -- 1 row per mstar_id (min ticker) so a name matching >1 NSE row can't fan out the holdings join.
    SELECT mstar_id, min(nse_ticker) AS nse_ticker FROM (
      SELECT mm.mstar_id, im.symbol AS nse_ticker
      FROM foundation_staging.de_mf_master mm
      JOIN foundation_staging.instrument_master im
        ON im.asset_class='etf'
       AND upper(regexp_replace(im.name,'[^A-Za-z0-9]','','g')) = upper(regexp_replace(mm.fund_name,'[^A-Za-z0-9]','','g'))
      WHERE mm.is_etf) b
    GROUP BY mstar_id)
`

// NSE equity ETFs only (FM scope): drop bond / gold / liquid / debt / silver / international.
const EQUITY_ETF_FILTER = `mm.is_etf
  AND mm.category_name NOT ILIKE ALL(ARRAY['%bond%','%gold%','%liquid%','%debt%','%silver%','%overnight%','%international%','%global%'])`

export type EtfLensRow = {
  fcode: string; name: string; category: string | null; expense: number | null
  nse_ticker: string | null
  n_holdings: number; n_leaders: number; breadth: number | null  // leadership-breadth (weighted)
  v_tech: number | null; v_fund: number | null; v_cat: number | null; v_flow: number | null; v_val: number | null
}

function mapRow(r: Record<string, string>): EtfLensRow {
  const n = (v: string | null) => (v == null ? null : toNumber(v))
  return {
    fcode: r.fcode, name: r.name, category: r.category, expense: n(r.expense), nse_ticker: r.nse_ticker,
    n_holdings: toNumberOr(r.n_holdings, 0), n_leaders: toNumberOr(r.n_leaders, 0), breadth: n(r.breadth),
    v_tech: n(r.v_tech), v_fund: n(r.v_fund), v_cat: n(r.v_cat), v_flow: n(r.v_flow), v_val: n(r.v_val),
  }
}

const ROLLUP_SELECT = `
  mm.mstar_id AS fcode, mm.fund_name AS name, mm.category_name AS category, mm.expense_ratio AS expense,
  max(en.nse_ticker) AS nse_ticker,
  count(h.instrument_id) AS n_holdings,
  count(*) FILTER (WHERE COALESCE(s.lead,0) >= 2) AS n_leaders,
  sum(h.weight) FILTER (WHERE COALESCE(s.lead,0) >= 2) / NULLIF(sum(h.weight),0) AS breadth,
  sum(h.weight*s.t)  FILTER (WHERE s.t  IS NOT NULL) / NULLIF(sum(h.weight) FILTER (WHERE s.t  IS NOT NULL),0) AS v_tech,
  sum(h.weight*s.f)  FILTER (WHERE s.f  IS NOT NULL) / NULLIF(sum(h.weight) FILTER (WHERE s.f  IS NOT NULL),0) AS v_fund,
  sum(h.weight*s.ca) FILTER (WHERE s.ca IS NOT NULL) / NULLIF(sum(h.weight) FILTER (WHERE s.ca IS NOT NULL),0) AS v_cat,
  sum(h.weight*s.fl) FILTER (WHERE s.fl IS NOT NULL) / NULLIF(sum(h.weight) FILTER (WHERE s.fl IS NOT NULL),0) AS v_flow,
  sum(h.weight*s.va) FILTER (WHERE s.va IS NOT NULL) / NULLIF(sum(h.weight) FILTER (WHERE s.va IS NOT NULL),0) AS v_val`

export async function getEtfLensList(): Promise<EtfLensRow[]> {
  const rows = await sql.unsafe(`
    WITH ${SCORED_STOCKS}
    SELECT ${ROLLUP_SELECT}
    FROM foundation_staging.de_mf_master mm
    JOIN foundation_staging.de_etf_holdings h ON h.ticker = mm.mstar_id AND h.weight IS NOT NULL
    JOIN scored s ON s.instrument_id = h.instrument_id   -- INNER: scored, mapped holdings only (cash/unmapped excluded from the breadth base)
    LEFT JOIN etf_nse en ON en.mstar_id = mm.mstar_id
    WHERE ${EQUITY_ETF_FILTER}
    GROUP BY mm.mstar_id, mm.fund_name, mm.category_name, mm.expense_ratio
    HAVING count(h.instrument_id) > 0
    ORDER BY breadth DESC NULLS LAST`) as unknown as Record<string, string>[]
  return rows.map(mapRow)
}

export type EtfHolding = {
  symbol: string; weight: number | null; sector: string | null
  d_tech: number | null; d_fund: number | null; d_cat: number | null; d_flow: number | null; d_val: number | null
  lead: number; strength: number | null; rs_3m: number | null
  ret_1d: number | null; ret_1w: number | null; ret_1m: number | null
}
export type EtfLensDetail = EtfLensRow & {
  isin: string | null; amc: string | null; benchmark: string | null
  holdings: EtfHolding[]
}

export async function getEtfLensDetail(fcode: string): Promise<EtfLensDetail | null> {
  const head = await sql.unsafe(`
    WITH ${SCORED_STOCKS}
    SELECT ${ROLLUP_SELECT}, max(mm.isin) AS isin, max(mm.amc_name) AS amc, max(mm.primary_benchmark) AS benchmark
    FROM foundation_staging.de_mf_master mm
    JOIN foundation_staging.de_etf_holdings h ON h.ticker = mm.mstar_id AND h.weight IS NOT NULL
    JOIN scored s ON s.instrument_id = h.instrument_id   -- same INNER basis as the look-through table below (consistent n_holdings)
    LEFT JOIN etf_nse en ON en.mstar_id = mm.mstar_id
    WHERE mm.mstar_id = $1 AND mm.is_etf
    GROUP BY mm.mstar_id, mm.fund_name, mm.category_name, mm.expense_ratio`,
    [fcode]) as unknown as Record<string, string>[]
  if (head.length === 0) return null

  const hrows = await sql.unsafe(`
    WITH ${SCORED_STOCKS}
    SELECT h.weight, s.symbol, im.sector,
      s.d_tech, s.d_fund, s.d_cat, s.d_flow, s.d_val, COALESCE(s.lead,0) AS lead, s.strength, s.rs_3m_n500,
      s.ret_1d, s.ret_1w, s.ret_1m
    FROM foundation_staging.de_etf_holdings h
    JOIN scored s ON s.instrument_id = h.instrument_id
    JOIN foundation_staging.instrument_master im ON im.instrument_id = h.instrument_id
    WHERE h.ticker = $1 AND h.weight IS NOT NULL
    ORDER BY h.weight DESC`,
    [fcode]) as unknown as Record<string, string>[]

  const n = (v: string | null) => (v == null ? null : toNumber(v))
  const base = mapRow(head[0])
  return {
    ...base,
    isin: head[0].isin, amc: head[0].amc, benchmark: head[0].benchmark,
    holdings: hrows.map(r => ({
      symbol: r.symbol, weight: n(r.weight), sector: r.sector,
      d_tech: n(r.d_tech), d_fund: n(r.d_fund), d_cat: n(r.d_cat), d_flow: n(r.d_flow), d_val: n(r.d_val),
      lead: toNumberOr(r.lead, 0), strength: n(r.strength), rs_3m: n(r.rs_3m_n500),
      ret_1d: n(r.ret_1d), ret_1w: n(r.ret_1w), ret_1m: n(r.ret_1m),
    })),
  }
}
