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
    idate AS (SELECT MAX(date) d FROM atlas.atlas_index_metrics_daily),
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
      im.index_code,
      im.ret_1d::text  AS ix_1d,  im.ret_1w::text  AS ix_1w,  im.ret_1m::text AS ix_1m,
      im.ret_3m::text  AS ix_3m,  im.ret_6m::text  AS ix_6m,  im.ret_12m::text AS ix_12m,
      bu.bu_1d, bu.bu_1w, bu.bu_1m, bu.bu_3m, bu.bu_6m, bu.bu_12m,
      im.date::text AS as_of
    FROM atlas.atlas_sector_master sm2
    JOIN atlas.atlas_index_metrics_daily im
      ON im.index_code = sm2.primary_nse_index AND im.date = (SELECT d FROM idate)
    LEFT JOIN bu ON bu.sector = sm2.sector_name
    WHERE sm2.is_active = true
      AND LOWER(sm2.sector_name) NOT LIKE '%conglomerate%'
    ORDER BY sm2.sector_name
  `

  const baseRow = await sql<Array<RawSectorRow>>`
    SELECT 'NIFTY 500' AS sector_name, index_code,
      ret_1d::text AS ix_1d, ret_1w::text AS ix_1w, ret_1m::text AS ix_1m,
      ret_3m::text AS ix_3m, ret_6m::text AS ix_6m, ret_12m::text AS ix_12m,
      NULL AS bu_1d, NULL AS bu_1w, NULL AS bu_1m, NULL AS bu_3m, NULL AS bu_6m, NULL AS bu_12m,
      date::text AS as_of
    FROM atlas.atlas_index_metrics_daily
    WHERE index_code = 'NIFTY 500'
      AND date = (SELECT MAX(date) FROM atlas.atlas_index_metrics_daily)
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
