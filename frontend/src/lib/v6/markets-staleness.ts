// frontend/src/lib/v6/markets-staleness.ts
//
// Client-safe (NO 'server-only'): pure per-baseline staleness helpers for
// /markets-rs. Deliberately NOT in queries/v6/markets_rs.ts — that module is
// 'server-only' (DB access via sql), and MarketsRsClient is a 'use client'
// component. Importing runtime values from a server-only module into a client
// component breaks the production webpack build ("server-only ... not supported
// in the pages/ directory"). These helpers touch no server state, so they live
// here and are imported by both the server query layer and the client grid.

/**
 * A baseline lagging the freshest by more than this many calendar days is
 * flagged stale in the grid. The normal US/global 1-day timezone lag
 * (NSE closes a day ahead of S&P 500 / MSCI World) stays unflagged; the
 * weeks-stale MSCI EM proxy gets a visible marker so it is never read as
 * current.
 */
export const MARKETS_RS_STALE_THRESHOLD_DAYS = 7

/**
 * Calendar-day lag of a baseline's as_of_date behind the freshest baseline.
 * Returns null when either date is missing or unparseable (explicit NULL
 * handling — never silently treat a missing date as fresh).
 */
export function baselineStalenessDays(
  rowAsOf: string | null,
  freshestAsOf: string | null,
): number | null {
  if (!rowAsOf || !freshestAsOf) return null
  const a = Date.parse(rowAsOf)
  const b = Date.parse(freshestAsOf)
  if (Number.isNaN(a) || Number.isNaN(b)) return null
  return Math.round((b - a) / 86_400_000)
}
