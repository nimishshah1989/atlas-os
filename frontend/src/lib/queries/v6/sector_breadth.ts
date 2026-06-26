// frontend/src/lib/queries/v6/sector_breadth.ts
//
// Server-only query for per-sector breadth metrics, derived on-the-fly from
// foundation_staging.atlas_scorecard_daily.features (JSONB).
//
// NOTE: atlas_sector_breadth_daily does NOT exist (confirmed A.0 audit,
// 2026-05-26). Breadth is computed here via aggregation over the scorecard
// snapshot for the latest available date.
//
// Feature key notes (atlas/features/scorecard_writer.py + deep_search_features.py):
//   dist_above_sma50  — present in JSONB (close / sma50 - 1; positive → above)
//   dist_above_sma200 — present in JSONB
//   dist_above_sma20  — NOT in JSONB as of v6.0; SMA20 breadth proxied via
//                       dist_above_sma50 with a TODO for when sma20 lands.
//   rs_residual_1m    — present in JSONB (21-day RS residual vs Nifty 500);
//                       used as the cross-sectional return σ (dispersion).
//
// top3_concentration_pct is hardcoded "0.00": atlas_universe_stocks has no
// market_cap_cr column (migration 002 schema). TODO(v6.1): add mcap column
// and compute top-3 contribution to sector mcap.

import 'server-only'
import sql from '@/lib/db'

// ---------------------------------------------------------------------------
// Public types
// ---------------------------------------------------------------------------

export type SectorBreadth = {
  sector: string
  n_stocks: number
  /** % of sector above SMA20 proxy (stringified Decimal pp, e.g. "74.00") */
  pct_above_sma20: string
  /** % of sector above SMA50 (stringified Decimal pp) */
  pct_above_sma50: string
  /** % of sector above SMA200 (stringified Decimal pp) */
  pct_above_sma200: string
  /**
   * Share of sector's market-cap in top 3 names (0.00 in v6.0 — no mcap column).
   * TODO(v6.1): compute from atlas_universe_stocks.market_cap_cr once column exists.
   */
  top3_concentration_pct: string
  /** Cross-sectional σ of rs_residual_1m within the sector (stringified Decimal) */
  dispersion_sigma: string
  /** ISO date string of the snapshot (MAX(date) from atlas_scorecard_daily) */
  as_of_date: string
}

// ---------------------------------------------------------------------------
// Internal row type
// ---------------------------------------------------------------------------

type BreadthRow = {
  sector: string
  n_stocks: string | number
  pct_above_sma20: string
  pct_above_sma50: string
  pct_above_sma200: string
  top3_concentration_pct: string
  dispersion_sigma: string
  as_of_date: string
}

// ---------------------------------------------------------------------------
// getSectorBreadth
// ---------------------------------------------------------------------------

/**
 * Return per-sector breadth metrics for the latest available scorecard date.
 *
 * Joins atlas_scorecard_daily (JSONB features) with atlas_universe_stocks
 * (sector mapping). Aggregates SMA breadth (% above) and cross-sectional
 * dispersion σ per sector.
 *
 * @param sector  Optional sector name filter. When provided returns at most 1
 *                row — used by /v6/sectors/[name] detail page (D.4) to avoid
 *                fetching all sectors for a single-sector view.
 *
 * NOTE on SMA20 proxy: dist_above_sma20 is not yet in the JSONB feature
 * library. pct_above_sma20 is proxied using dist_above_sma50 (same sign —
 * positive → price above moving average). When the sma20 feature lands
 * in atlas/discovery/deep_search_features.py, update the CASE WHEN below
 * to use features->>'dist_above_sma20'.
 */
export async function getSectorBreadth(sector?: string): Promise<SectorBreadth[]> {
  const rows = sector != null
    ? await sql<BreadthRow[]>`
        WITH latest AS (
          SELECT MAX(date) AS d FROM foundation_staging.atlas_scorecard_daily
        ),
        universe AS (
          SELECT
            sd.instrument_id,
            us.sector,
            -- SMA20 proxy: dist_above_sma50 (TODO: replace with dist_above_sma20 when available)
            CASE
              WHEN (sd.features->>'dist_above_sma50') IS NOT NULL
               AND (sd.features->>'dist_above_sma50')::numeric > 0
              THEN 1 ELSE 0
            END AS above_20_proxy,
            CASE
              WHEN (sd.features->>'dist_above_sma50') IS NOT NULL
               AND (sd.features->>'dist_above_sma50')::numeric > 0
              THEN 1 ELSE 0
            END AS above_50,
            CASE
              WHEN (sd.features->>'dist_above_sma200') IS NOT NULL
               AND (sd.features->>'dist_above_sma200')::numeric > 0
              THEN 1 ELSE 0
            END AS above_200,
            (sd.features->>'rs_residual_1m')::numeric AS rs_residual_1m
          FROM foundation_staging.atlas_scorecard_daily sd
          JOIN foundation_staging.instrument_master us
            ON us.instrument_id = sd.instrument_id
           AND us.is_active
          WHERE sd.date = (SELECT d FROM latest)
        )
        SELECT
          sector,
          COUNT(*)::text                                                        AS n_stocks,
          ROUND(100.0 * SUM(above_20_proxy) / NULLIF(COUNT(*), 0), 2)::text   AS pct_above_sma20,
          ROUND(100.0 * SUM(above_50)       / NULLIF(COUNT(*), 0), 2)::text   AS pct_above_sma50,
          ROUND(100.0 * SUM(above_200)      / NULLIF(COUNT(*), 0), 2)::text   AS pct_above_sma200,
          '0.00'::text                                                          AS top3_concentration_pct,
          ROUND(COALESCE(STDDEV(rs_residual_1m), 0)::numeric * 100, 2)::text  AS dispersion_sigma,
          (SELECT d::text FROM latest)                                          AS as_of_date
        FROM universe
        WHERE sector = ${sector}
        GROUP BY sector
      `
    : await sql<BreadthRow[]>`
        WITH latest AS (
          SELECT MAX(date) AS d FROM foundation_staging.atlas_scorecard_daily
        ),
        universe AS (
          SELECT
            sd.instrument_id,
            us.sector,
            -- SMA20 proxy: dist_above_sma50 (TODO: replace with dist_above_sma20 when available)
            CASE
              WHEN (sd.features->>'dist_above_sma50') IS NOT NULL
               AND (sd.features->>'dist_above_sma50')::numeric > 0
              THEN 1 ELSE 0
            END AS above_20_proxy,
            CASE
              WHEN (sd.features->>'dist_above_sma50') IS NOT NULL
               AND (sd.features->>'dist_above_sma50')::numeric > 0
              THEN 1 ELSE 0
            END AS above_50,
            CASE
              WHEN (sd.features->>'dist_above_sma200') IS NOT NULL
               AND (sd.features->>'dist_above_sma200')::numeric > 0
              THEN 1 ELSE 0
            END AS above_200,
            (sd.features->>'rs_residual_1m')::numeric AS rs_residual_1m
          FROM foundation_staging.atlas_scorecard_daily sd
          JOIN foundation_staging.instrument_master us
            ON us.instrument_id = sd.instrument_id
           AND us.is_active
          WHERE sd.date = (SELECT d FROM latest)
        )
        SELECT
          sector,
          COUNT(*)::text                                                        AS n_stocks,
          ROUND(100.0 * SUM(above_20_proxy) / NULLIF(COUNT(*), 0), 2)::text   AS pct_above_sma20,
          ROUND(100.0 * SUM(above_50)       / NULLIF(COUNT(*), 0), 2)::text   AS pct_above_sma50,
          ROUND(100.0 * SUM(above_200)      / NULLIF(COUNT(*), 0), 2)::text   AS pct_above_sma200,
          '0.00'::text                                                          AS top3_concentration_pct,
          ROUND(COALESCE(STDDEV(rs_residual_1m), 0)::numeric * 100, 2)::text  AS dispersion_sigma,
          (SELECT d::text FROM latest)                                          AS as_of_date
        FROM universe
        GROUP BY sector
        ORDER BY sector
      `

  return rows.map((r): SectorBreadth => ({
    sector: r.sector,
    n_stocks:
      typeof r.n_stocks === 'string' ? parseInt(r.n_stocks, 10) : (r.n_stocks ?? 0),
    pct_above_sma20: r.pct_above_sma20 ?? '0.00',
    pct_above_sma50: r.pct_above_sma50 ?? '0.00',
    pct_above_sma200: r.pct_above_sma200 ?? '0.00',
    top3_concentration_pct: r.top3_concentration_pct ?? '0.00',
    dispersion_sigma: r.dispersion_sigma ?? '0.00',
    as_of_date: r.as_of_date ?? '',
  }))
}
