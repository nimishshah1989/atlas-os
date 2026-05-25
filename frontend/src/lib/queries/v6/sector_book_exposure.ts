// frontend/src/lib/queries/v6/sector_book_exposure.ts
//
// Server-only query for per-sector book exposure vs Nifty 500 benchmark.
//
// Sources:
//   atlas.atlas_paper_portfolio  (migration 084) — open positions
//   atlas.atlas_universe_stocks  (migration 002) — instrument → sector mapping
//   public.de_index_constituents (JIP table)      — Nifty 500 sector benchmark
//
// v6.0 weight approximation
// -------------------------
// atlas_paper_portfolio has no weight_pct column (migration 084). Each open
// position is treated as equal-weight within the book:
//   book_weight_sector = count(positions in sector) / count(all open positions) × 100
// TODO(v6.1): replace with notional-based weights once weight_pct lands.
//
// v6.0 benchmark approximation
// -----------------------------
// de_index_constituents carries no market-cap weight column — the JIP table
// stores membership only (instrument_id, index_code, effective_to). Benchmark
// weight is derived as equal-weight per sector constituent:
//   bench_weight_sector = count(NIFTY500 members in sector) / total(NIFTY500) × 100
// TODO(v6.1): replace when JIP adds constituent weight column.
//
// Active membership filter: effective_to IS NULL (per stocks.py + preflight.py
// usage — there is no is_active column on de_index_constituents).
//
// Empty-book behaviour
// --------------------
// When atlas_paper_portfolio is empty (the v6.0 launch state), the book CTE
// produces zero rows. The FULL OUTER JOIN still returns all benchmark sectors
// with book_weight="0.00" and delta_pp="-<bench_weight>". Returns [] only
// when de_index_constituents itself has no NIFTY500 rows.
//
// Multi-user readiness
// --------------------
// Service-role connection (@/lib/db) bypasses RLS. v6.0 single-user assumption;
// no user_id filter. When multi-user lands (v6.1+) add a user_id parameter.

import 'server-only'
import sql from '@/lib/db'

// ---------------------------------------------------------------------------
// Public types
// ---------------------------------------------------------------------------

export type SectorBookExposure = {
  sector_name: string
  /** % of book in this sector (equal-weight approximation, v6.0). Stringified Decimal. */
  book_weight: string
  /** Nifty 500 sector weight % (equal-weight approximation, v6.0). Stringified Decimal. */
  benchmark_weight: string
  /** book_weight - benchmark_weight in percentage points. Signed stringified Decimal. */
  delta_pp: string
  /** Distinct iids held in this sector (0 for benchmark-only sectors). */
  holding_count: number
}

// ---------------------------------------------------------------------------
// Internal row type
// ---------------------------------------------------------------------------

type ExposureRow = {
  sector_name: string
  book_weight: string
  benchmark_weight: string
  delta_pp: string
  holding_count: string | number
}

// ---------------------------------------------------------------------------
// getSectorBookExposure
// ---------------------------------------------------------------------------

/**
 * Return per-sector book weight vs Nifty 500 benchmark weight for the paper
 * portfolio, ordered by ABS(delta_pp) DESC (largest over/under first).
 *
 * @param sectorName  Optional sector filter. When provided returns at most 1
 *                    row — used by the sector detail page (D.4) to avoid
 *                    fetching all 30 sectors for a single-sector view.
 *
 * When the book is empty (v6.0 launch state) all rows will have
 * book_weight="0.00" and delta_pp equal to the negative benchmark weight.
 */
export async function getSectorBookExposure(
  sectorName?: string,
): Promise<SectorBookExposure[]> {
  // -------------------------------------------------------------------------
  // book_cte: count open positions per sector via atlas_universe_stocks join.
  // Equal-weight approximation (v6.0): each position = 1/total_positions.
  // -------------------------------------------------------------------------
  // bench_cte: equal-weight Nifty 500 sector distribution from JIP table.
  // Membership filter: effective_to IS NULL (no is_active column on JIP table).
  // -------------------------------------------------------------------------
  // FULL OUTER JOIN ensures:
  //   - sectors held but not in benchmark → benchmark_weight = 0
  //   - sectors in benchmark but not held → book_weight = 0, holding_count = 0
  // -------------------------------------------------------------------------

  const rows = sectorName != null
    ? await sql<ExposureRow[]>`
        WITH book_cte AS (
          SELECT
            u.sector,
            COUNT(DISTINCT p.instrument_id)                          AS held_count,
            COUNT(DISTINCT p.instrument_id)::numeric
              / NULLIF(SUM(COUNT(DISTINCT p.instrument_id)) OVER (), 0) * 100 AS book_pct
          FROM atlas.atlas_paper_portfolio p
          JOIN atlas.atlas_universe_stocks u
            ON u.instrument_id = p.instrument_id
           AND u.effective_to IS NULL
          WHERE p.exit_date IS NULL
          GROUP BY u.sector
        ),
        bench_cte AS (
          SELECT
            i.sector,
            COUNT(*)::numeric
              / NULLIF(SUM(COUNT(*)) OVER (), 0) * 100               AS bench_pct
          FROM public.de_index_constituents ic
          JOIN public.de_instrument i
            ON i.id = ic.instrument_id
           AND i.is_active = TRUE
          WHERE ic.index_code = 'NIFTY500'
            AND (ic.effective_to IS NULL OR ic.effective_to > CURRENT_DATE)
            AND i.sector IS NOT NULL
          GROUP BY i.sector
        )
        SELECT
          COALESCE(bk.sector, bn.sector)              AS sector_name,
          ROUND(COALESCE(bk.book_pct, 0), 2)::text   AS book_weight,
          ROUND(COALESCE(bn.bench_pct, 0), 2)::text  AS benchmark_weight,
          ROUND(
            COALESCE(bk.book_pct, 0) - COALESCE(bn.bench_pct, 0),
            2
          )::text                                     AS delta_pp,
          COALESCE(bk.held_count, 0)::int             AS holding_count
        FROM book_cte bk
        FULL OUTER JOIN bench_cte bn ON bn.sector = bk.sector
        WHERE COALESCE(bk.sector, bn.sector) = ${sectorName}
        ORDER BY ABS(
          COALESCE(bk.book_pct, 0) - COALESCE(bn.bench_pct, 0)
        ) DESC
      `
    : await sql<ExposureRow[]>`
        WITH book_cte AS (
          SELECT
            u.sector,
            COUNT(DISTINCT p.instrument_id)                          AS held_count,
            COUNT(DISTINCT p.instrument_id)::numeric
              / NULLIF(SUM(COUNT(DISTINCT p.instrument_id)) OVER (), 0) * 100 AS book_pct
          FROM atlas.atlas_paper_portfolio p
          JOIN atlas.atlas_universe_stocks u
            ON u.instrument_id = p.instrument_id
           AND u.effective_to IS NULL
          WHERE p.exit_date IS NULL
          GROUP BY u.sector
        ),
        bench_cte AS (
          SELECT
            i.sector,
            COUNT(*)::numeric
              / NULLIF(SUM(COUNT(*)) OVER (), 0) * 100               AS bench_pct
          FROM public.de_index_constituents ic
          JOIN public.de_instrument i
            ON i.id = ic.instrument_id
           AND i.is_active = TRUE
          WHERE ic.index_code = 'NIFTY500'
            AND (ic.effective_to IS NULL OR ic.effective_to > CURRENT_DATE)
            AND i.sector IS NOT NULL
          GROUP BY i.sector
        )
        SELECT
          COALESCE(bk.sector, bn.sector)              AS sector_name,
          ROUND(COALESCE(bk.book_pct, 0), 2)::text   AS book_weight,
          ROUND(COALESCE(bn.bench_pct, 0), 2)::text  AS benchmark_weight,
          ROUND(
            COALESCE(bk.book_pct, 0) - COALESCE(bn.bench_pct, 0),
            2
          )::text                                     AS delta_pp,
          COALESCE(bk.held_count, 0)::int             AS holding_count
        FROM book_cte bk
        FULL OUTER JOIN bench_cte bn ON bn.sector = bk.sector
        ORDER BY ABS(
          COALESCE(bk.book_pct, 0) - COALESCE(bn.bench_pct, 0)
        ) DESC
      `

  return rows.map((r): SectorBookExposure => ({
    sector_name: r.sector_name,
    book_weight: r.book_weight,
    benchmark_weight: r.benchmark_weight,
    delta_pp: r.delta_pp,
    holding_count:
      typeof r.holding_count === 'string'
        ? parseInt(r.holding_count, 10)
        : (r.holding_count ?? 0),
  }))
}
