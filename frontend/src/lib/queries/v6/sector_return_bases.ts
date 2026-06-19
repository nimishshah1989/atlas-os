// frontend/src/lib/queries/v6/sector_return_bases.ts
//
// Dual-basis sector returns for the Index ⟷ Bottom-up toggle.
//
//   index    — official cap-weighted NSE sector index (atlas_index_metrics_daily)
//   bottomup — FREE-FLOAT cap-weighted aggregate of Atlas's constituents
//              (Σ(ret·w)/Σw, w = float_shares × price from tv_metrics)
//
// Both across 1d/1w/1m/3m/6m/12m. The previous "absolute return" was an
// equal-weighted constituent mean — a few micro-caps swamped the megacaps
// (Defence read +113% vs the index's +7.4%). This replaces that.
//
// RS vs Nifty 500 (per window) = basis_return − nifty500_return, computed in
// the component so the toggle needs no refetch.
//
// All values are decimal fractions (0.074 = +7.4%) — multiply by 100 at display.

import 'server-only'
import sql from '@/lib/db'
import { toNumber } from '@/lib/v6/decimal'
import { NULL_RETURN_SET, type ReturnSet, type ReturnBasesPayload } from './sector_return_bases_shared'

// Re-export shared types/helpers so server callers have a single import surface.
export * from './sector_return_bases_shared'

type RawSectorRow = {
  sector_name: string
  index_code: string | null
  // index-level
  ix_1d: string | null; ix_1w: string | null; ix_1m: string | null
  ix_3m: string | null; ix_6m: string | null; ix_12m: string | null
  // free-float cap-weighted bottom-up
  bu_1d: string | null; bu_1w: string | null; bu_1m: string | null
  bu_3m: string | null; bu_6m: string | null; bu_12m: string | null
  as_of: string | null
}

/**
 * Per-sector returns under both bases (index + free-float bottom-up) across all
 * windows, plus the Nifty 500 baseline. One round trip.
 */
export async function getSectorReturnBases(): Promise<ReturnBasesPayload> {
  const rows = await sql<RawSectorRow[]>`
    WITH sdate AS (SELECT MAX(date) d FROM atlas.atlas_stock_metrics_daily),
    -- Index codes we need returns for: each sector's primary index + Nifty 500.
    idx_codes AS (
      SELECT DISTINCT primary_nse_index AS code
      FROM atlas.atlas_sector_master
      WHERE is_active = true AND LOWER(sector_name) NOT LIKE '%conglomerate%'
      UNION SELECT 'NIFTY 500'
    ),
    idx_latest AS (
      SELECT c.code, lp.date AS d, lp.close AS c0
      FROM idx_codes c
      JOIN LATERAL (
        SELECT date, close FROM public.de_index_prices
        WHERE index_code = c.code AND close > 0 ORDER BY date DESC LIMIT 1
      ) lp ON true
    ),
    -- Index returns from RAW de_index_prices. atlas_index_metrics_daily is buggy
    -- for sparse indices — it reaches back to a stale price (e.g. FMCG 3m showed
    -- +249.8%). Staleness guard: NULL a window when no close exists near the
    -- target date, so we never show a wrong number (just "—").
    idx_ret AS (
      SELECT l.code, l.d,
        (l.c0 / NULLIF((SELECT close FROM public.de_index_prices WHERE index_code=l.code AND close>0 AND date <  l.d       AND date >= l.d - 5   ORDER BY date DESC LIMIT 1),0) - 1) AS r1d,
        (l.c0 / NULLIF((SELECT close FROM public.de_index_prices WHERE index_code=l.code AND close>0 AND date <= l.d - 7   AND date >= l.d - 13  ORDER BY date DESC LIMIT 1),0) - 1) AS r1w,
        (l.c0 / NULLIF((SELECT close FROM public.de_index_prices WHERE index_code=l.code AND close>0 AND date <= l.d - 30  AND date >= l.d - 38  ORDER BY date DESC LIMIT 1),0) - 1) AS r1m,
        (l.c0 / NULLIF((SELECT close FROM public.de_index_prices WHERE index_code=l.code AND close>0 AND date <= l.d - 91  AND date >= l.d - 103 ORDER BY date DESC LIMIT 1),0) - 1) AS r3m,
        (l.c0 / NULLIF((SELECT close FROM public.de_index_prices WHERE index_code=l.code AND close>0 AND date <= l.d - 182 AND date >= l.d - 194 ORDER BY date DESC LIMIT 1),0) - 1) AS r6m,
        (l.c0 / NULLIF((SELECT close FROM public.de_index_prices WHERE index_code=l.code AND close>0 AND date <= l.d - 365 AND date >= l.d - 380 ORDER BY date DESC LIMIT 1),0) - 1) AS r12m
      FROM idx_latest l
    ),
    -- free-float weighted bottom-up, per sector per window (weight = float_shares × price)
    con AS (
      SELECT u.sector,
             sm.ret_1d::numeric  AS r1d, sm.ret_1w::numeric  AS r1w, sm.ret_1m::numeric AS r1m,
             sm.ret_3m::numeric  AS r3m, sm.ret_6m::numeric  AS r6m, sm.ret_12m::numeric AS r12m,
             (NULLIF(tv.float_shares, 0)::numeric * NULLIF(tv.price, 0)::numeric) AS w
      FROM atlas.atlas_universe_stocks u
      JOIN atlas.atlas_stock_metrics_daily sm
        ON sm.instrument_id = u.instrument_id AND sm.date = (SELECT d FROM sdate)
      LEFT JOIN atlas.tv_metrics tv ON tv.symbol = u.symbol
      WHERE u.effective_to IS NULL
    ),
    bu AS (
      SELECT sector,
        (sum(r1d*w)  FILTER (WHERE r1d  IS NOT NULL) / NULLIF(sum(w) FILTER (WHERE r1d  IS NOT NULL),0))::text  AS bu_1d,
        (sum(r1w*w)  FILTER (WHERE r1w  IS NOT NULL) / NULLIF(sum(w) FILTER (WHERE r1w  IS NOT NULL),0))::text  AS bu_1w,
        (sum(r1m*w)  FILTER (WHERE r1m  IS NOT NULL) / NULLIF(sum(w) FILTER (WHERE r1m  IS NOT NULL),0))::text  AS bu_1m,
        (sum(r3m*w)  FILTER (WHERE r3m  IS NOT NULL) / NULLIF(sum(w) FILTER (WHERE r3m  IS NOT NULL),0))::text  AS bu_3m,
        (sum(r6m*w)  FILTER (WHERE r6m  IS NOT NULL) / NULLIF(sum(w) FILTER (WHERE r6m  IS NOT NULL),0))::text  AS bu_6m,
        (sum(r12m*w) FILTER (WHERE r12m IS NOT NULL) / NULLIF(sum(w) FILTER (WHERE r12m IS NOT NULL),0))::text AS bu_12m
      FROM con WHERE w IS NOT NULL GROUP BY sector
    )
    SELECT
      sm2.sector_name,
      sm2.primary_nse_index AS index_code,
      ir.r1d::text  AS ix_1d,  ir.r1w::text  AS ix_1w,  ir.r1m::text AS ix_1m,
      ir.r3m::text  AS ix_3m,  ir.r6m::text  AS ix_6m,  ir.r12m::text AS ix_12m,
      bu.bu_1d, bu.bu_1w, bu.bu_1m, bu.bu_3m, bu.bu_6m, bu.bu_12m,
      ir.d::text AS as_of
    FROM atlas.atlas_sector_master sm2
    LEFT JOIN idx_ret ir ON ir.code = sm2.primary_nse_index
    LEFT JOIN bu ON bu.sector = sm2.sector_name
    WHERE sm2.is_active = true
      AND LOWER(sm2.sector_name) NOT LIKE '%conglomerate%'
    ORDER BY sm2.sector_name
  `

  const baseRow = await sql<Array<RawSectorRow>>`
    WITH l AS (
      SELECT date AS d, close AS c0 FROM public.de_index_prices
      WHERE index_code = 'NIFTY 500' AND close > 0 ORDER BY date DESC LIMIT 1
    )
    SELECT 'NIFTY 500' AS sector_name, 'NIFTY 500' AS index_code,
      (l.c0 / NULLIF((SELECT close FROM public.de_index_prices WHERE index_code='NIFTY 500' AND close>0 AND date <  l.d       AND date >= l.d - 5   ORDER BY date DESC LIMIT 1),0) - 1)::text AS ix_1d,
      (l.c0 / NULLIF((SELECT close FROM public.de_index_prices WHERE index_code='NIFTY 500' AND close>0 AND date <= l.d - 7   AND date >= l.d - 13  ORDER BY date DESC LIMIT 1),0) - 1)::text AS ix_1w,
      (l.c0 / NULLIF((SELECT close FROM public.de_index_prices WHERE index_code='NIFTY 500' AND close>0 AND date <= l.d - 30  AND date >= l.d - 38  ORDER BY date DESC LIMIT 1),0) - 1)::text AS ix_1m,
      (l.c0 / NULLIF((SELECT close FROM public.de_index_prices WHERE index_code='NIFTY 500' AND close>0 AND date <= l.d - 91  AND date >= l.d - 103 ORDER BY date DESC LIMIT 1),0) - 1)::text AS ix_3m,
      (l.c0 / NULLIF((SELECT close FROM public.de_index_prices WHERE index_code='NIFTY 500' AND close>0 AND date <= l.d - 182 AND date >= l.d - 194 ORDER BY date DESC LIMIT 1),0) - 1)::text AS ix_6m,
      (l.c0 / NULLIF((SELECT close FROM public.de_index_prices WHERE index_code='NIFTY 500' AND close>0 AND date <= l.d - 365 AND date >= l.d - 380 ORDER BY date DESC LIMIT 1),0) - 1)::text AS ix_12m,
      NULL AS bu_1d, NULL AS bu_1w, NULL AS bu_1m, NULL AS bu_3m, NULL AS bu_6m, NULL AS bu_12m,
      l.d::text AS as_of
    FROM l
  `

  const ixSet = (r: RawSectorRow): ReturnSet => ({
    ret_1d: toNumber(r.ix_1d), ret_1w: toNumber(r.ix_1w), ret_1m: toNumber(r.ix_1m),
    ret_3m: toNumber(r.ix_3m), ret_6m: toNumber(r.ix_6m), ret_12m: toNumber(r.ix_12m),
  })
  const buSet = (r: RawSectorRow): ReturnSet => ({
    ret_1d: toNumber(r.bu_1d), ret_1w: toNumber(r.bu_1w), ret_1m: toNumber(r.bu_1m),
    ret_3m: toNumber(r.bu_3m), ret_6m: toNumber(r.bu_6m), ret_12m: toNumber(r.bu_12m),
  })

  return {
    sectors: rows.map((r) => ({
      sector_name: r.sector_name,
      index_code: r.index_code,
      index: ixSet(r),
      bottomup: buSet(r),
    })),
    nifty500: baseRow[0] ? ixSet(baseRow[0]) : NULL_RETURN_SET,
    as_of: rows[0]?.as_of ?? baseRow[0]?.as_of ?? null,
  }
}
