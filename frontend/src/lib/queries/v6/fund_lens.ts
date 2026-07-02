// src/lib/queries/v6/fund_lens.ts
// Native mutual-fund lens roll-up — all from atlas_foundation. Funds are a holdings-weighted
// roll-up of the stock atom (D26/D27/D21b): the headline is LEADERSHIP-BREADTH (% of holdings
// weight that are top-decile leaders in ≥2 conviction lenses), ranked WITHIN the SEBI category —
// NOT a composite. The fund-specific differentiator is ACTIVE-MOVEMENT: the month-over-month
// holdings delta (is the manager adding leaders?), from the append-only de_mf_holdings snapshots.
// Roll-ups are a TRANSPARENCY view (what's held, how it scores) — not an outperformance predictor.
import 'server-only'
import sql from '@/lib/db'
import { toNumber, toNumberOr } from '@/lib/v6/decimal'
import { fundComposite, rankFundsInCategory } from '@/lib/v6/fundScore'
import type { LensWeightMap } from '@/lib/v6/sectorScore'
import { getLensWeights } from './lens_weights'
import { SCORED_STOCKS } from './etf_lens'

const LATEST = `(SELECT max(as_of_date) FROM atlas_foundation.de_mf_holdings)`
// Universe (D21b): Regular plan · Equity · Growth option. Drop debt/liquid/gilt, and the Direct-plan
// + dividend (IDCW) duplicates of the same portfolio so each scheme appears once.
const EQUITY_FUND_FILTER = `NOT mm.is_etf AND mm.is_active
  AND mm.broad_category NOT ILIKE ALL(ARRAY['%debt%','%liquid%','%money%','%overnight%','%gilt%','%bond%'])
  AND mm.fund_name NOT ILIKE '%Direct%' AND mm.fund_name NOT ILIKE '%Dir Gr%' AND mm.fund_name NOT ILIKE '%IDCW%'`

export type FundLensRow = {
  mstar_id: string; name: string; amc: string | null; category: string | null; benchmark: string | null; expense: number | null
  aum_cr: number | null
  n_holdings: number; n_leaders: number; breadth: number | null
  v_tech: number | null; v_fund: number | null; v_cat: number | null; v_flow: number | null; v_val: number | null
  // Fund composite = the SAME glass-box lens blend as sectors/stocks (fundScore.ts), over the fund's
  // holdings-weighted lens vector — derived, not a standalone scorecard. cat_rank/cat_size are
  // computed below over the DISPLAYED cohort so "N / M" matches this list.
  composite: number | null; cat_rank: number | null; cat_size: number | null
  has_12m: boolean // ≥12 months of NAV history — funds younger than this are NOT ranked (FM)
}
function mapRow(r: Record<string, string>, weights?: LensWeightMap): FundLensRow {
  const n = (v: string | null) => (v == null ? null : toNumber(v))
  const v_tech = n(r.v_tech), v_fund = n(r.v_fund), v_cat = n(r.v_cat), v_flow = n(r.v_flow)
  return {
    mstar_id: r.mstar_id, name: r.name, amc: r.amc, category: r.category, benchmark: r.benchmark, expense: n(r.expense),
    aum_cr: n(r.aum_cr),
    n_holdings: toNumberOr(r.n_holdings, 0), n_leaders: toNumberOr(r.n_leaders, 0), breadth: n(r.breadth),
    v_tech, v_fund, v_cat, v_flow, v_val: n(r.v_val),
    composite: fundComposite({ v_tech, v_fund, v_flow, v_cat }, weights),
    cat_rank: null, cat_size: null, // assigned per-category after fetch (see getFundLensList)
    has_12m: r.has_12m === 't' || r.has_12m === 'true' || (r.has_12m as unknown) === true,
  }
}

// weight_pct is a PERCENT (6.17 = 6.17%); the breadth/vector ratios normalise the unit either way.
const ROLLUP = `
  mm.mstar_id AS mstar_id, mm.fund_name AS name, mm.amc_name AS amc, mm.category_name AS category,
  mm.primary_benchmark AS benchmark, mm.expense_ratio AS expense,
  count(h.instrument_id) AS n_holdings,
  count(*) FILTER (WHERE COALESCE(s.lead,0) >= 1) AS n_leaders,
  sum(h.weight_pct) FILTER (WHERE COALESCE(s.lead,0) >= 1) / NULLIF(sum(h.weight_pct),0) AS breadth,
  sum(h.weight_pct*s.t)  FILTER (WHERE s.t  IS NOT NULL) / NULLIF(sum(h.weight_pct) FILTER (WHERE s.t  IS NOT NULL),0) AS v_tech,
  sum(h.weight_pct*s.f)  FILTER (WHERE s.f  IS NOT NULL) / NULLIF(sum(h.weight_pct) FILTER (WHERE s.f  IS NOT NULL),0) AS v_fund,
  sum(h.weight_pct*s.ca) FILTER (WHERE s.ca IS NOT NULL) / NULLIF(sum(h.weight_pct) FILTER (WHERE s.ca IS NOT NULL),0) AS v_cat,
  sum(h.weight_pct*s.fl) FILTER (WHERE s.fl IS NOT NULL) / NULLIF(sum(h.weight_pct) FILTER (WHERE s.fl IS NOT NULL),0) AS v_flow,
  sum(h.weight_pct*s.va) FILTER (WHERE s.va IS NOT NULL) / NULLIF(sum(h.weight_pct) FILTER (WHERE s.va IS NOT NULL),0) AS v_val`

// AUM (₹ crore) for the size filter/column — from atlas_universe_funds, joined by Morningstar F-code.
export async function getFundLensList(): Promise<FundLensRow[]> {
  const rows = await sql.unsafe(`
    WITH ${SCORED_STOCKS},
    navlife AS (  -- ≥12 months of NAV history? funds younger than a year are not ranked
      SELECT mstar_id, (min(nav_date) <= (SELECT max(nav_date) FROM atlas_foundation.de_mf_nav_daily) - interval '12 months') AS has_12m
      FROM atlas_foundation.de_mf_nav_daily GROUP BY mstar_id)
    SELECT ${ROLLUP}, max(uf.aum_cr) AS aum_cr, (bool_or(nl.has_12m))::text AS has_12m
    FROM atlas_foundation.de_mf_master mm
    JOIN atlas_foundation.de_mf_holdings h ON h.mstar_id = mm.mstar_id AND h.as_of_date = ${LATEST} AND h.weight_pct > 0
    JOIN scored s ON s.instrument_id = h.instrument_id
    LEFT JOIN atlas_foundation.atlas_universe_funds uf ON uf.mstar_id = mm.mstar_id
    LEFT JOIN navlife nl ON nl.mstar_id = mm.mstar_id
    WHERE ${EQUITY_FUND_FILTER}
    GROUP BY mm.mstar_id, mm.fund_name, mm.amc_name, mm.category_name, mm.primary_benchmark, mm.expense_ratio
    HAVING count(h.instrument_id) >= 5
    ORDER BY breadth DESC NULLS LAST`) as unknown as Record<string, string>[]
  // Composite + within-category rank are DERIVED from the lens vector (fundScore.ts) — no dependency
  // on the standalone atlas_fund_scorecard pipeline, so the rank is always as fresh as the lenses.
  const weights = await getLensWeights()
  return rankFundsInCategory(rows.map((r) => mapRow(r, weights)))
}

export type FundHolding = {
  symbol: string; weight: number | null; sector: string | null
  d_tech: number | null; d_fund: number | null; d_cat: number | null; d_flow: number | null; d_val: number | null
  lead: number; rs_3m: number | null
  ret_1d: number | null; ret_1w: number | null; ret_1m: number | null
}
export type FundMove = { symbol: string; name: string | null; weight: number | null; lead: number }
export type FundActiveMovement = {
  prior_date: string | null; leaders_added: number; leaders_dropped: number
  added: FundMove[]; exited: FundMove[]
}
export type FundLensDetail = FundLensRow & {
  isin: string | null; nav: number | null; nav_date: string | null; nav_1y: number | null
  holdings: FundHolding[]; movement: FundActiveMovement | null
}

export async function getFundLensDetail(mstarId: string): Promise<FundLensDetail | null> {
  const head = await sql.unsafe(`
    WITH ${SCORED_STOCKS}
    SELECT ${ROLLUP}, max(mm.isin) AS isin
    FROM atlas_foundation.de_mf_master mm
    JOIN atlas_foundation.de_mf_holdings h ON h.mstar_id = mm.mstar_id AND h.as_of_date = ${LATEST} AND h.weight_pct > 0
    JOIN scored s ON s.instrument_id = h.instrument_id
    WHERE mm.mstar_id = $1 AND ${EQUITY_FUND_FILTER}
    GROUP BY mm.mstar_id, mm.fund_name, mm.amc_name, mm.category_name, mm.primary_benchmark, mm.expense_ratio`,
    [mstarId]) as unknown as Record<string, string>[]
  if (head.length === 0) return null

  const [hrows, nav, movement] = await Promise.all([
    sql.unsafe(`
      WITH ${SCORED_STOCKS}
      SELECT h.weight_pct AS weight, s.symbol, im.sector,
        s.d_tech, s.d_fund, s.d_cat, s.d_flow, s.d_val, COALESCE(s.lead,0) AS lead, s.rs_3m_n500,
        s.ret_1d, s.ret_1w, s.ret_1m
      FROM atlas_foundation.de_mf_holdings h
      JOIN scored s ON s.instrument_id = h.instrument_id
      JOIN atlas_foundation.instrument_master im ON im.instrument_id = h.instrument_id
      WHERE h.mstar_id = $1 AND h.as_of_date = ${LATEST} AND h.weight_pct > 0
      ORDER BY h.weight_pct DESC`, [mstarId]) as unknown as Promise<Record<string, string>[]>,
    sql<Record<string, string>[]>`
      SELECT nav, to_char(nav_date,'YYYY-MM-DD') AS nav_date, nav_change_pct
      FROM atlas_foundation.de_mf_nav_daily WHERE mstar_id = ${mstarId} ORDER BY nav_date DESC LIMIT 1`,
    getFundActiveMovement(mstarId),
  ])

  const n = (v: string | null) => (v == null ? null : toNumber(v))
  const base = mapRow(head[0], await getLensWeights())
  return {
    ...base, isin: head[0].isin,
    nav: nav[0] ? n(nav[0].nav) : null, nav_date: nav[0]?.nav_date ?? null, nav_1y: null,
    holdings: hrows.map(r => ({
      symbol: r.symbol, weight: n(r.weight), sector: r.sector,
      d_tech: n(r.d_tech), d_fund: n(r.d_fund), d_cat: n(r.d_cat), d_flow: n(r.d_flow), d_val: n(r.d_val),
      lead: toNumberOr(r.lead, 0), rs_3m: n(r.rs_3m_n500),
      ret_1d: n(r.ret_1d), ret_1w: n(r.ret_1w), ret_1m: n(r.ret_1m),
    })),
    movement,
  }
}

// Active-movement: the latest holdings snapshot vs the prior one — what the manager bought/sold,
// and whether the net move added top-decile leaders (the D27 fund differentiator).
export async function getFundActiveMovement(mstarId: string): Promise<FundActiveMovement | null> {
  const snaps = await sql<{ d: string }[]>`
    SELECT to_char(as_of_date,'YYYY-MM-DD') AS d FROM atlas_foundation.de_mf_holdings
    WHERE mstar_id = ${mstarId} GROUP BY as_of_date ORDER BY as_of_date DESC LIMIT 2`
  if (snaps.length < 2) return null
  const [curD, prvD] = [snaps[0].d, snaps[1].d]
  const rows = await sql.unsafe(`
    WITH ${SCORED_STOCKS},
    cur AS (SELECT instrument_id, weight_pct, holding_name FROM atlas_foundation.de_mf_holdings WHERE mstar_id=$1 AND as_of_date=$2 AND weight_pct > 0),
    prv AS (SELECT instrument_id, weight_pct FROM atlas_foundation.de_mf_holdings WHERE mstar_id=$1 AND as_of_date=$3 AND weight_pct > 0)
    SELECT 'added' AS kind, s.symbol, c.holding_name AS name, c.weight_pct AS weight, COALESCE(s.lead,0) AS lead
    FROM cur c LEFT JOIN prv p ON p.instrument_id=c.instrument_id
    LEFT JOIN scored s ON s.instrument_id=c.instrument_id
    WHERE p.instrument_id IS NULL AND c.instrument_id IS NOT NULL
    UNION ALL
    SELECT 'exited' AS kind, s.symbol, NULL AS name, p.weight_pct AS weight, COALESCE(s.lead,0) AS lead
    FROM prv p LEFT JOIN cur c ON c.instrument_id=p.instrument_id
    LEFT JOIN scored s ON s.instrument_id=p.instrument_id
    WHERE c.instrument_id IS NULL AND p.instrument_id IS NOT NULL`,
    [mstarId, curD, prvD]) as unknown as Record<string, string>[]
  const n = (v: string | null) => (v == null ? null : toNumber(v))
  const mk = (r: Record<string, string>): FundMove => ({ symbol: r.symbol, name: r.name, weight: n(r.weight), lead: toNumberOr(r.lead, 0) })
  const added = rows.filter(r => r.kind === 'added' && r.symbol).map(mk).sort((a, b) => (b.weight ?? 0) - (a.weight ?? 0))
  const exited = rows.filter(r => r.kind === 'exited' && r.symbol).map(mk).sort((a, b) => (b.weight ?? 0) - (a.weight ?? 0))
  return {
    prior_date: prvD,
    leaders_added: added.filter(m => m.lead >= 2).length,
    leaders_dropped: exited.filter(m => m.lead >= 2).length,
    added: added.slice(0, 12), exited: exited.slice(0, 12),
  }
}

// Month-end NAV series (one point per calendar month, ascending) for the risk/return ratios on the
// fund detail page. The full history is small (a few hundred points at most), so we fetch it all.
export type FundNavPoint = { d: string; nav: number }
export async function getFundNavMonthly(mstarId: string): Promise<FundNavPoint[]> {
  const rows = await sql<{ d: string; nav: string }[]>`
    SELECT to_char(nav_date,'YYYY-MM-DD') AS d, nav::text AS nav FROM (
      SELECT DISTINCT ON (date_trunc('month', nav_date)) nav_date, nav
      FROM atlas_foundation.de_mf_nav_daily
      WHERE mstar_id = ${mstarId} AND nav > 0
      ORDER BY date_trunc('month', nav_date), nav_date DESC
    ) q ORDER BY nav_date ASC`
  return rows.map((r) => ({ d: r.d, nav: toNumberOr(r.nav, 0) }))
}

// DAILY fund NAV + Nifty 50 + Nifty 500 closes over the fund's last 5 years, aligned on the
// trading date — the parent series for the equity-curve + RS chart. NAV is published every
// business day, so the chart is plotted daily (not month-end). Same two baselines the /funds RS
// matrix uses. Rebasing/RS happen in the tested pure builder (buildFundCurves).
export type FundEquityPoint = { d: string; fund: number; nifty50: number | null; nifty500: number | null }
export async function getFundEquityCurve(mstarId: string): Promise<FundEquityPoint[]> {
  const rows = await sql<{ d: string; fund: string; nifty50: string | null; nifty500: string | null }[]>`
    WITH range AS (
      SELECT (max(nav_date) - interval '5 years')::date AS start
      FROM atlas_foundation.de_mf_nav_daily WHERE mstar_id = ${mstarId}
    )
    SELECT to_char(v.nav_date,'YYYY-MM-DD') AS d, v.nav::text AS fund,
      i50.close::text  AS nifty50,
      i500.close::text AS nifty500
    FROM atlas_foundation.de_mf_nav_daily v
    LEFT JOIN atlas_foundation.index_prices i50  ON i50.index_code='NIFTY 50'  AND i50.date  = v.nav_date
    LEFT JOIN atlas_foundation.index_prices i500 ON i500.index_code='NIFTY 500' AND i500.date = v.nav_date
    WHERE v.mstar_id = ${mstarId} AND v.nav > 0 AND v.nav_date >= (SELECT start FROM range)
    ORDER BY v.nav_date ASC`
  return rows.map((r) => ({
    d: r.d,
    fund: toNumberOr(r.fund, 0),
    nifty50: r.nifty50 == null ? null : toNumber(r.nifty50),
    nifty500: r.nifty500 == null ? null : toNumber(r.nifty500),
  }))
}

// Holdings sector composition for the last (up to 6) disclosed snapshots — to show how the fund's
// sector mix has shifted. Sector comes from the mapped instrument (instrument_master.sector); the
// weights are the raw holding weights summed per sector per snapshot.
export async function getFundSectorHistory(mstarId: string): Promise<{ d: string; sector: string; w: number }[]> {
  const rows = await sql<{ d: string; sector: string; w: string }[]>`
    WITH snaps AS (
      SELECT DISTINCT as_of_date FROM atlas_foundation.de_mf_holdings
      WHERE mstar_id = ${mstarId} ORDER BY as_of_date DESC LIMIT 6)
    SELECT to_char(h.as_of_date,'YYYY-MM-DD') AS d,
           COALESCE(im.sector,'Unclassified') AS sector,
           sum(h.weight_pct)::text AS w
    FROM atlas_foundation.de_mf_holdings h
    JOIN snaps s ON s.as_of_date = h.as_of_date
    LEFT JOIN atlas_foundation.instrument_master im ON im.instrument_id = h.instrument_id
    WHERE h.mstar_id = ${mstarId} AND h.weight_pct > 0
    GROUP BY h.as_of_date, COALESCE(im.sector,'Unclassified')`
  return rows.map((r) => ({ d: r.d, sector: r.sector, w: toNumberOr(r.w, 0) }))
}

// Data-as-of date for the /funds page banner = the latest MF-holdings snapshot the roll-up
// is computed from (weekly cadence). Single source of the page's freshness stamp.
export async function getFundsAsOf(): Promise<string | null> {
  const rows = await sql<{ d: string | null }[]>`
    SELECT to_char(max(as_of_date),'YYYY-MM-DD') AS d FROM atlas_foundation.de_mf_holdings`
  return rows[0]?.d ?? null
}
