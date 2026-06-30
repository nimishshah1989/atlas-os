// Fund performance metrics for the /funds table — all REAL, computed fresh (no stale scorecard):
//  • RS matrix: NAV return vs Nifty 50 AND Nifty 500 over 1m/3m/6m/12m, calendar-anchored (the
//    fund's stated TR benchmark isn't in our price data, so we use the two market indices — the
//    SAME baselines as stock RS). RS = fund NAV return − index return over the same window.
//  • Holdings EMA breadth: how many of the fund's holdings sit above their 21/50/200-day EMA.
// Both keyed by mstar_id and threaded into FundLensTable. Fast (LATERAL index lookups on
// de_mf_nav_daily(mstar_id, nav_date); a single GROUP BY join for EMA breadth).
import 'server-only'
import sql from '@/lib/db'
import { toNumber } from '@/lib/v6/decimal'

type Win = { m1: number | null; m3: number | null; m6: number | null; m12: number | null }
export type FundRsMatrix = { asof: string | null; ret: Win; n500: Win; n50: Win }

const EQUITY = `mm.is_active AND NOT mm.is_etf
  AND mm.broad_category NOT ILIKE ALL(ARRAY['%debt%','%liquid%','%money%','%overnight%','%gilt%','%bond%'])
  AND mm.fund_name NOT ILIKE '%Direct%' AND mm.fund_name NOT ILIKE '%Dir Gr%' AND mm.fund_name NOT ILIKE '%IDCW%'`

// RS = fund NAV return − index return, per window, vs Nifty 50 and Nifty 500.
export async function getFundRsMatrix(): Promise<Map<string, FundRsMatrix>> {
  const rows = (await sql.unsafe(`
    WITH asof AS (SELECT max(nav_date) d FROM foundation_staging.de_mf_nav_daily),
    ic AS (  -- index close at the as-of date and each look-back anchor (one scan per point)
      SELECT
        ${idxClose("NIFTY 500", 0)} p500_0, ${idxClose("NIFTY 500", 1)} p500_1, ${idxClose("NIFTY 500", 3)} p500_3, ${idxClose("NIFTY 500", 6)} p500_6, ${idxClose("NIFTY 500", 12)} p500_12,
        ${idxClose("NIFTY 50", 0)} p50_0,  ${idxClose("NIFTY 50", 1)} p50_1,  ${idxClose("NIFTY 50", 3)} p50_3,  ${idxClose("NIFTY 50", 6)} p50_6,  ${idxClose("NIFTY 50", 12)} p50_12
    )
    SELECT mm.mstar_id, to_char((SELECT d FROM asof),'YYYY-MM-DD') AS asof,
      n.r0, n.r1, n.r3, n.r6, n.r12,
      ic.p500_0, ic.p500_1, ic.p500_3, ic.p500_6, ic.p500_12,
      ic.p50_0, ic.p50_1, ic.p50_3, ic.p50_6, ic.p50_12
    FROM foundation_staging.de_mf_master mm
    CROSS JOIN ic
    CROSS JOIN LATERAL (
      SELECT ${navAt(0)} r0, ${navAt(1)} r1, ${navAt(3)} r3, ${navAt(6)} r6, ${navAt(12)} r12
    ) n
    WHERE ${EQUITY}
  `)) as unknown as Record<string, string>[]

  const out = new Map<string, FundRsMatrix>()
  for (const r of rows) {
    const num = (v: string | null) => (v == null ? null : toNumber(v))
    const navNow = num(r.r0)
    if (navNow == null) continue
    // fund return over a window = navNow / navThen − 1
    const fret = (then: number | null) => (then == null || then === 0 || navNow == null ? null : navNow / then - 1)
    const iret = (now: string | null, then: string | null) => {
      const a = num(now), b = num(then)
      return a == null || b == null || b === 0 ? null : a / b - 1
    }
    const rs = (f: number | null, i: number | null) => (f == null || i == null ? null : f - i)
    const ret: Win = { m1: fret(num(r.r1)), m3: fret(num(r.r3)), m6: fret(num(r.r6)), m12: fret(num(r.r12)) }
    const i500: Win = { m1: iret(r.p500_0, r.p500_1), m3: iret(r.p500_0, r.p500_3), m6: iret(r.p500_0, r.p500_6), m12: iret(r.p500_0, r.p500_12) }
    const i50: Win = { m1: iret(r.p50_0, r.p50_1), m3: iret(r.p50_0, r.p50_3), m6: iret(r.p50_0, r.p50_6), m12: iret(r.p50_0, r.p50_12) }
    out.set(r.mstar_id, {
      asof: r.asof,
      ret,
      n500: { m1: rs(ret.m1, i500.m1), m3: rs(ret.m3, i500.m3), m6: rs(ret.m6, i500.m6), m12: rs(ret.m12, i500.m12) },
      n50: { m1: rs(ret.m1, i50.m1), m3: rs(ret.m3, i50.m3), m6: rs(ret.m6, i50.m6), m12: rs(ret.m12, i50.m12) },
    })
  }
  return out
}

// NAV nearest to (as-of − N months), per fund, via the (mstar_id, nav_date) index.
function navAt(months: number): string {
  const back = months === 0 ? '' : ` - interval '${months} months'`
  return `(SELECT v.nav FROM foundation_staging.de_mf_nav_daily v
           WHERE v.mstar_id = mm.mstar_id AND v.nav_date <= (SELECT d FROM asof)${back}
           ORDER BY v.nav_date DESC LIMIT 1)`
}
function idxClose(code: string, months: number): string {
  const back = months === 0 ? '' : ` - interval '${months} months'`
  return `(SELECT close FROM foundation_staging.index_prices
           WHERE index_code = '${code}' AND date <= (SELECT d FROM asof)${back}
           ORDER BY date DESC LIMIT 1)`
}

export type FundEma = { n_priced: number; a21: number; a50: number; a200: number }

// How many of each fund's latest-snapshot holdings sit above their 21/50/200-day EMA.
// Counted over the SAME SCORED holdings as the "Holdings" column (INNER JOIN the lens journal), and
// DISTINCT by instrument (de_mf_holdings can carry the same name in >1 row) — so the counts can
// never exceed the fund's holdings count (the earlier bug: a50 > Holdings, because EMA was over ALL
// technically-priced names while Holdings counts only lens-scored ones).
export async function getFundHoldingsEma(): Promise<Map<string, FundEma>> {
  const rows = (await sql`
    WITH snap AS (SELECT max(as_of_date) d FROM foundation_staging.de_mf_holdings),
    ld AS (SELECT max(date) d FROM foundation_staging.atlas_lens_scores_daily WHERE asset_class='stock'),
    tdl AS (SELECT max(date) d FROM foundation_staging.technical_daily WHERE asset_class='stock')
    SELECT h.mstar_id,
      count(DISTINCT h.instrument_id) FILTER (WHERE t.instrument_id IS NOT NULL)::int AS n_priced,
      count(DISTINCT h.instrument_id) FILTER (WHERE t.above_ema_21)::int  AS a21,
      count(DISTINCT h.instrument_id) FILTER (WHERE t.above_ema_50)::int  AS a50,
      count(DISTINCT h.instrument_id) FILTER (WHERE t.above_ema_200)::int AS a200
    FROM foundation_staging.de_mf_holdings h
    JOIN foundation_staging.atlas_lens_scores_daily l
      ON l.instrument_id = h.instrument_id AND l.asset_class='stock' AND l.date = (SELECT d FROM ld)
    LEFT JOIN foundation_staging.technical_daily t
      ON t.instrument_id = h.instrument_id AND t.asset_class='stock' AND t.date = (SELECT d FROM tdl)
    WHERE h.as_of_date = (SELECT d FROM snap) AND h.weight_pct > 0
    GROUP BY h.mstar_id
  `) as unknown as { mstar_id: string; n_priced: number; a21: number; a50: number; a200: number }[]
  const out = new Map<string, FundEma>()
  for (const r of rows) out.set(r.mstar_id, { n_priced: r.n_priced, a21: r.a21, a50: r.a50, a200: r.a200 })
  return out
}
