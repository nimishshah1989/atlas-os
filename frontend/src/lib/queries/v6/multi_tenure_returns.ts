// frontend/src/lib/queries/v6/multi_tenure_returns.ts
//
// Multi-tenure absolute returns for a single stock or a batch.
//
// Source: atlas.atlas_stock_metrics_daily
//   Columns: ret_1d, ret_1w, ret_1m, ret_3m, ret_6m, ret_12m (NUMERIC)
//   One row per (instrument_id, date); we always pull the LATEST date.
//
// The unified view (atlas_stock_signal_unified) does NOT carry return columns —
// those live on atlas_stock_metrics_daily (migration 004). All return values
// are transported as stringified Decimals; callers must NOT call Number() on
// them for financial display (use Intl.NumberFormat instead).

import 'server-only'
import sql from '@/lib/db'

export type MultiTenureReturns = {
  iid: string
  date: string
  ret_1d: string | null
  ret_1w: string | null
  ret_1m: string | null
  ret_3m: string | null
  ret_6m: string | null
  ret_12m: string | null
}

type MetricsRow = {
  iid: string
  date: string
  ret_1d: string | null
  ret_1w: string | null
  ret_1m: string | null
  ret_3m: string | null
  ret_6m: string | null
  ret_12m: string | null
}

/**
 * Return the latest multi-tenure returns row for a single instrument.
 *
 * Returns null when the instrument has no rows in atlas_stock_metrics_daily
 * (e.g. new listing with no history yet, or an invalid iid).
 */
export async function getMultiTenureReturns(
  iid: string,
): Promise<MultiTenureReturns | null> {
  const rows = await sql<MetricsRow[]>`
    SELECT
      instrument_id::text   AS iid,
      date::text            AS date,
      ret_1d::text          AS ret_1d,
      ret_1w::text          AS ret_1w,
      ret_1m::text          AS ret_1m,
      ret_3m::text          AS ret_3m,
      ret_6m::text          AS ret_6m,
      ret_12m::text         AS ret_12m
    FROM atlas.atlas_stock_metrics_daily
    WHERE instrument_id = ${iid}::uuid
    ORDER BY date DESC
    LIMIT 1
  `
  return rows[0] ?? null
}

/**
 * Return the latest multi-tenure returns for a batch of instruments.
 *
 * Uses DISTINCT ON so each iid appears at most once (latest date row).
 * Instruments with no history are silently excluded from the result set —
 * callers must handle missing entries by checking result length or building
 * a lookup map.
 */
export async function getMultiTenureReturnsBatch(
  iids: string[],
): Promise<MultiTenureReturns[]> {
  if (iids.length === 0) return []

  const rows = await sql<MetricsRow[]>`
    SELECT DISTINCT ON (instrument_id)
      instrument_id::text   AS iid,
      date::text            AS date,
      ret_1d::text          AS ret_1d,
      ret_1w::text          AS ret_1w,
      ret_1m::text          AS ret_1m,
      ret_3m::text          AS ret_3m,
      ret_6m::text          AS ret_6m,
      ret_12m::text         AS ret_12m
    FROM atlas.atlas_stock_metrics_daily
    WHERE instrument_id::text = ANY(${iids}::text[])
    ORDER BY instrument_id, date DESC
  `
  return rows
}
