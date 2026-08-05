// fund_category_curve — SQL for /funds/compare. This module owns queries and nothing else;
// all arithmetic beyond the chain-link itself lives in lib/fundCategoryCurve.ts.
import sql from '@/lib/db'
import { toNumber, toNumberOr } from '@/lib/decimal'

/**
 * Category → the NSE index that category is measured against. A reference mapping, not a
 * methodology number, so it lives here rather than in atlas_thresholds. Every code below
 * was verified present in atlas_foundation.index_prices with 3,795+ days of history.
 *
 * de_mf_master.primary_benchmark is deliberately NOT used: it holds Morningstar display
 * strings ("Nifty Smallcap 250 TR INR", "BSE 500 India TR INR") that join to nothing we
 * store, and its BSE entries have no series in index_prices at all.
 */
export const CATEGORY_INDEX: Record<string, string> = {
  'India Fund Index Funds': 'NIFTY 500',
  'India Fund Flexi Cap': 'NIFTY 500',
  'India Fund ELSS (Tax Savings)': 'NIFTY 500',
  'India Fund Focused Fund': 'NIFTY 500',
  'India Fund Large-Cap': 'NIFTY 100',
  'India Fund Large & Mid-Cap': 'NIFTY LARGEMID250',
  'India Fund Mid-Cap': 'NIFTY MIDCAP 150',
  'India Fund Small-Cap': 'NIFTY SMLCAP 250',
  'India Fund Multi-Cap': 'NIFTY500 MULTICAP',
  'India Fund Value': 'NIFTY500 VALUE 50',
  'India Fund Equity - Consumption': 'NIFTY CONSUMPTION',
  'India Fund Equity - Infrastructure': 'NIFTY INFRA',
  'India Fund Equity - ESG': 'NIFTY100 ESG',
  'India Fund Sector - Financial Services': 'NIFTY FIN SERVICE',
  'India Fund Sector - Healthcare': 'NIFTY HEALTHCARE',
  'India Fund Sector - Technology': 'NIFTY IT',
  'India Fund Sector - Energy': 'NIFTY ENERGY',
  'India Fund Sector - FMCG': 'NIFTY FMCG',
}

export type CategoryOption = {
  category: string
  /** Funds in the category that have any NAV history — the composite's real population. */
  nFunds: number
  /** Latest NAV date across the category; drives the staleness warning. */
  lastNav: string | null
}

export type CompositeRow = {
  d: string
  /** Chain-linked equal-weighted index, 100 at the first date in range. */
  v: number
  /**
   * Funds alive on this date — past their first NAV, not yet past their last. This is the
   * composite's divisor, which is NOT the number of funds that reported: a fund that skipped
   * the day is flat, and counts. 0 on the anchor date by construction.
   */
  n: number
  nifty50: number | null
  nifty500: number | null
  catIndex: number | null
}

export type ConstituentRow = {
  mstarId: string
  name: string
  amc: string | null
  /** Fund size in ₹ crore — a 20% return on ₹50 cr is a different fact from one on ₹20,000 cr. */
  aumCr: number | null
  first: string
  last: string
  /** Simple return over the fund's own span inside the window, in percent. */
  pct: number
  /** False when the fund entered or exited inside the window. */
  full: boolean
}

/**
 * The categories worth offering, with their real fund count and freshness.
 *
 * Scoped to atlas_universe_funds — the curated set — because that is the ONLY set whose
 * NAVs still refresh. ingest_nav.py pulls exactly this join, so the other 361 funds that
 * carry NAV history are frozen leftovers from older backfills. Including them made funds
 * appear to "exit" a composite mid-window when in truth we had merely stopped tracking
 * them (Groww BSE Power ETF FOF was doing exactly that to the Energy category).
 */
export async function getCategoryOptions(): Promise<CategoryOption[]> {
  const rows = await sql<{ category: string; n: string; last_nav: string | null }[]>`
    SELECT m.category_name AS category,
           count(DISTINCT m.mstar_id)::text AS n,
           to_char(max(l.last_d), 'YYYY-MM-DD') AS last_nav
    FROM atlas_foundation.de_mf_master m
    JOIN atlas_foundation.atlas_universe_funds u ON u.mstar_id = m.mstar_id
    JOIN (SELECT mstar_id, max(nav_date) AS last_d
          FROM atlas_foundation.de_mf_nav_daily GROUP BY mstar_id) l
      ON l.mstar_id = m.mstar_id
    WHERE m.category_name IS NOT NULL
    GROUP BY m.category_name
    ORDER BY m.category_name`
  return rows.map((r) => ({
    category: r.category,
    nFunds: toNumberOr(r.n, 0),
    lastNav: r.last_nav,
  }))
}

/**
 * The category's equal-weighted composite, chain-linked, plus the three benchmark closes.
 *
 * Chain-linked, not an average of rebased NAVs: 215 funds' NAV histories start in 2026
 * alone, and averaging levels would let a newcomer rebased at 100 drag the whole curve.
 * Averaging daily returns across the funds alive on each day, then compounding, makes fund
 * entry and exit a non-event.
 *
 * THE DIVISOR IS EVERY FUND ALIVE, NOT EVERY FUND THAT REPORTED. Funds skip days. Averaging
 * over the reporters counted the market's move at full weight on the day the reporters moved,
 * and then a second time inside the multi-day move of each fund that resumed later. The error
 * compounded and always upward: it read Small-Cap at +17.8% over the year against a true
 * +12.0%, and grew with the fund count — which is why single-fund categories were exact.
 *
 * So each fund contributes exactly one day of return per date: its own move on the days it
 * reports, and zero on the days it does not (its NAV is carried forward, never interpolated,
 * so the whole move lands intact on the day it resumes). That keeps each fund's own total
 * return exact and is the standard construction for an equal-weighted index from irregularly
 * reported NAVs. Verified against an independent pandas LOCF panel over the same NAVs.
 *
 * Postgres has no product aggregate, so exp(sum(ln(1+r))) does the compounding. The
 * r > -1 guard keeps ln defined — one NAV collapsing to zero would otherwise abort the
 * whole series.
 *
 * Benchmarks join as-of (last close on or before the NAV date), not on equality —
 * index_prices has no row for 2024-03-31, 2025-03-31 or 2026-03-31 while NAVs do, and an
 * equality join would silently drop those points.
 */
export async function getCategoryComposite(
  category: string,
  from: string,
  to: string,
): Promise<CompositeRow[]> {
  const catIndex = CATEGORY_INDEX[category] ?? 'NIFTY 500'
  const rows = await sql<{
    d: string; v: string; n: string
    n50: string | null; n500: string | null; ncat: string | null
  }[]>`
    WITH nav AS (
      SELECT n.mstar_id, n.nav_date, n.nav,
             lag(n.nav) OVER (PARTITION BY n.mstar_id ORDER BY n.nav_date) AS prev
      FROM atlas_foundation.de_mf_nav_daily n
      JOIN atlas_foundation.de_mf_master m USING (mstar_id)
      JOIN atlas_foundation.atlas_universe_funds u ON u.mstar_id = n.mstar_id
      WHERE m.category_name = ${category}
        AND n.nav_date BETWEEN ${from} AND ${to}
        AND n.nav > 0
    ),
    spans AS (
      SELECT mstar_id, min(nav_date) AS born, max(nav_date) AS died
      FROM nav GROUP BY mstar_id
    ),
    active AS (
      SELECT g.nav_date, count(*)::int AS n
      FROM (SELECT DISTINCT nav_date FROM nav) g
      JOIN spans s ON g.nav_date > s.born AND g.nav_date <= s.died
      GROUP BY g.nav_date
    ),
    moved AS (
      SELECT nav_date, sum(nav / prev - 1) AS total
      FROM nav
      WHERE prev IS NOT NULL AND prev > 0 AND nav / prev - 1 > -1
      GROUP BY nav_date
    ),
    daily AS (
      SELECT a.nav_date, coalesce(m.total, 0) / a.n AS r, a.n
      FROM active a LEFT JOIN moved m USING (nav_date)
    ),
    anchored AS (
      SELECT min(nav_date) AS nav_date, 0::numeric AS r, 0 AS n
      FROM nav HAVING min(nav_date) IS NOT NULL
      UNION ALL
      SELECT nav_date, r, n FROM daily
    ),
    comp AS (
      SELECT nav_date, 100 * exp(sum(ln(1 + r)) OVER (ORDER BY nav_date)) AS v, n
      FROM anchored
    )
    SELECT to_char(c.nav_date, 'YYYY-MM-DD') AS d, c.v::text AS v, c.n::text AS n,
           b50.close::text AS n50, b500.close::text AS n500, bcat.close::text AS ncat
    FROM comp c
    LEFT JOIN LATERAL (
      SELECT close FROM atlas_foundation.index_prices
      WHERE index_code = 'NIFTY 50' AND date <= c.nav_date
      ORDER BY date DESC LIMIT 1) b50 ON true
    LEFT JOIN LATERAL (
      SELECT close FROM atlas_foundation.index_prices
      WHERE index_code = 'NIFTY 500' AND date <= c.nav_date
      ORDER BY date DESC LIMIT 1) b500 ON true
    LEFT JOIN LATERAL (
      SELECT close FROM atlas_foundation.index_prices
      WHERE index_code = ${catIndex} AND date <= c.nav_date
      ORDER BY date DESC LIMIT 1) bcat ON true
    ORDER BY c.nav_date`
  return rows.map((r) => ({
    d: r.d,
    v: toNumberOr(r.v, 0),
    n: toNumberOr(r.n, 0),
    nifty50: toNumber(r.n50),
    nifty500: toNumber(r.n500),
    catIndex: toNumber(r.ncat),
  }))
}

/** One row of the all-categories board. Growth factors, not percentages — the CAGR gate is
 *  applied by growthReturn() so there is one place that decides absolute-vs-annualised. */
export type CategorySummaryRow = {
  category: string
  /** Earliest composite date in the window; a period starting before it is not covered. */
  first: string
  /** exp(sum(ln(1+r))) over each trailing period, or null where history is short. */
  comp: { y1: number | null; y2: number | null; y3: number | null; y5: number | null }
  bench: { y1: number | null; y2: number | null; y3: number | null; y5: number | null }
  indexCode: string
}

/**
 * Trailing 1/2/3/5-year growth for EVERY category and its benchmark, in two queries.
 *
 * The composite is exp(cumsum(ln(1+r))), so the growth between two dates is just
 * exp(sum(ln(1+r))) over the dates in between — an aggregate, no series needed. That turns
 * "15 categories × 4 periods" into one grouped scan (~2s) instead of 15 separate composite
 * queries; another period is one more FILTER over a scan already paid for. Benchmarks are
 * 15 codes × 5 as-of lookups, which is trivial.
 *
 * The daily return is built exactly as getCategoryComposite builds it — divided by the funds
 * ALIVE that day, not the funds that reported. See that function for why; every figure on
 * this board was overstated until it was.
 */
export async function getCategorySummary(
  anchors: { to: string; y1: string; y2: string; y3: string; y5: string },
): Promise<CategorySummaryRow[]> {
  const codes = [...new Set(Object.values(CATEGORY_INDEX))]
  const [comp, bench, births] = await Promise.all([
    sql<{
      cat: string; first_d: string
      g1: string | null; g2: string | null; g3: string | null; g5: string | null
    }[]>`
      WITH nav AS (
        SELECT m.category_name AS cat, n.mstar_id, n.nav_date, n.nav,
               lag(n.nav) OVER (PARTITION BY n.mstar_id ORDER BY n.nav_date) AS prev
        FROM atlas_foundation.de_mf_nav_daily n
        JOIN atlas_foundation.de_mf_master m USING (mstar_id)
        JOIN atlas_foundation.atlas_universe_funds u ON u.mstar_id = n.mstar_id
        WHERE n.nav_date BETWEEN ${anchors.y5} AND ${anchors.to}
          AND n.nav > 0 AND m.category_name IS NOT NULL
      ),
      spans AS (
        SELECT cat, mstar_id, min(nav_date) AS born, max(nav_date) AS died
        FROM nav GROUP BY cat, mstar_id
      ),
      active AS (
        SELECT g.cat, g.nav_date, count(*)::int AS n
        FROM (SELECT DISTINCT cat, nav_date FROM nav) g
        JOIN spans s ON s.cat = g.cat AND g.nav_date > s.born AND g.nav_date <= s.died
        GROUP BY g.cat, g.nav_date
      ),
      moved AS (
        SELECT cat, nav_date, sum(nav / prev - 1) AS total
        FROM nav WHERE prev IS NOT NULL AND prev > 0 AND nav / prev - 1 > -1
        GROUP BY cat, nav_date
      ),
      daily AS (
        SELECT a.cat, a.nav_date, coalesce(m.total, 0) / a.n AS r
        FROM active a LEFT JOIN moved m ON m.cat = a.cat AND m.nav_date = a.nav_date
      )
      SELECT cat, to_char(min(nav_date), 'YYYY-MM-DD') AS first_d,
             (exp(sum(ln(1 + r)) FILTER (WHERE nav_date > ${anchors.y1})))::text AS g1,
             (exp(sum(ln(1 + r)) FILTER (WHERE nav_date > ${anchors.y2})))::text AS g2,
             (exp(sum(ln(1 + r)) FILTER (WHERE nav_date > ${anchors.y3})))::text AS g3,
             (exp(sum(ln(1 + r)) FILTER (WHERE nav_date > ${anchors.y5})))::text AS g5
      FROM daily GROUP BY cat ORDER BY cat`,
    sql<{ code: string; label: string; close: string | null }[]>`
      SELECT c.code, a.label, b.close::text AS close
      FROM unnest(${codes}::text[]) c(code)
      CROSS JOIN (VALUES ('end', ${anchors.to}), ('y1', ${anchors.y1}), ('y2', ${anchors.y2}),
                         ('y3', ${anchors.y3}), ('y5', ${anchors.y5})) a(label, d)
      LEFT JOIN LATERAL (
        SELECT close FROM atlas_foundation.index_prices
        WHERE index_code = c.code AND date <= a.d::date
        ORDER BY date DESC LIMIT 1) b ON true`,
    // Each category's true earliest NAV, unbounded. The composite query is windowed, so its
    // own min(nav_date) is just the first trading day inside the window and says nothing about
    // whether the category existed at the anchor.
    sql<{ cat: string; born: string }[]>`
      SELECT m.category_name AS cat, to_char(min(n.nav_date), 'YYYY-MM-DD') AS born
      FROM atlas_foundation.de_mf_nav_daily n
      JOIN atlas_foundation.de_mf_master m USING (mstar_id)
      JOIN atlas_foundation.atlas_universe_funds u ON u.mstar_id = n.mstar_id
      WHERE m.category_name IS NOT NULL
      GROUP BY m.category_name`,
  ])
  const born = new Map(births.map((b) => [b.cat, b.born]))

  const idx = new Map<string, Record<string, number | null>>()
  for (const r of bench) {
    const e = idx.get(r.code) ?? {}
    e[r.label] = toNumber(r.close)
    idx.set(r.code, e)
  }
  const ratio = (code: string, k: string): number | null => {
    const e = idx.get(code)
    const end = e?.end
    const at = e?.[k]
    return end == null || at == null || at <= 0 ? null : end / at
  }

  return comp.map((r) => {
    const code = CATEGORY_INDEX[r.cat] ?? 'NIFTY 500'
    const first = born.get(r.cat) ?? r.first_d
    // A period beginning before the category existed is not covered by it. Reporting a
    // two-year number in the 5Y column would be the worst kind of wrong: plausible.
    const has = (anchor: string) => first <= anchor
    return {
      category: r.cat,
      first,
      indexCode: code,
      comp: {
        y1: has(anchors.y1) ? toNumber(r.g1) : null,
        y2: has(anchors.y2) ? toNumber(r.g2) : null,
        y3: has(anchors.y3) ? toNumber(r.g3) : null,
        y5: has(anchors.y5) ? toNumber(r.g5) : null,
      },
      bench: {
        y1: has(anchors.y1) ? ratio(code, 'y1') : null,
        y2: has(anchors.y2) ? ratio(code, 'y2') : null,
        y3: has(anchors.y3) ? ratio(code, 'y3') : null,
        y5: has(anchors.y5) ? ratio(code, 'y5') : null,
      },
    }
  })
}

/** Every fund in the composite, with its own return over its own span inside the window. */
export async function getCategoryConstituents(
  category: string,
  from: string,
  to: string,
): Promise<ConstituentRow[]> {
  const rows = await sql<{
    mstar_id: string; name: string; amc: string | null; aum_cr: string | null
    first_d: string; last_d: string
    first_nav: string; last_nav: string; window_first: string; window_last: string
  }[]>`
    WITH nav AS (
      SELECT n.mstar_id, n.nav_date, n.nav
      FROM atlas_foundation.de_mf_nav_daily n
      JOIN atlas_foundation.de_mf_master m USING (mstar_id)
      JOIN atlas_foundation.atlas_universe_funds u ON u.mstar_id = n.mstar_id
      WHERE m.category_name = ${category}
        AND n.nav_date BETWEEN ${from} AND ${to}
        AND n.nav > 0
    ),
    span AS (SELECT min(nav_date) AS w_first, max(nav_date) AS w_last FROM nav),
    ends AS (
      SELECT DISTINCT ON (mstar_id) mstar_id, nav_date AS first_d, nav AS first_nav
      FROM nav ORDER BY mstar_id, nav_date ASC
    ),
    tails AS (
      SELECT DISTINCT ON (mstar_id) mstar_id, nav_date AS last_d, nav AS last_nav
      FROM nav ORDER BY mstar_id, nav_date DESC
    )
    SELECT e.mstar_id, m.fund_name AS name, u.amc, u.aum_cr::text AS aum_cr,
           to_char(e.first_d, 'YYYY-MM-DD') AS first_d,
           to_char(t.last_d, 'YYYY-MM-DD') AS last_d,
           e.first_nav::text AS first_nav, t.last_nav::text AS last_nav,
           to_char(s.w_first, 'YYYY-MM-DD') AS window_first,
           to_char(s.w_last, 'YYYY-MM-DD') AS window_last
    FROM ends e
    JOIN tails t USING (mstar_id)
    JOIN atlas_foundation.de_mf_master m ON m.mstar_id = e.mstar_id
    JOIN atlas_foundation.atlas_universe_funds u ON u.mstar_id = e.mstar_id
    CROSS JOIN span s
    WHERE e.first_d < t.last_d`
  return rows
    .map((r) => ({
      mstarId: r.mstar_id,
      name: r.name,
      amc: r.amc,
      aumCr: toNumber(r.aum_cr),
      first: r.first_d,
      last: r.last_d,
      pct: (toNumberOr(r.last_nav, 0) / toNumberOr(r.first_nav, 1) - 1) * 100,
      full: r.first_d === r.window_first && r.last_d === r.window_last,
    }))
    .sort((a, b) => b.pct - a.pct)
}
