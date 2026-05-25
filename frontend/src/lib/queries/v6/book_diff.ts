// frontend/src/lib/queries/v6/book_diff.ts
//
// Portfolio-level diff: held stocks that flipped conviction overnight + held
// stocks whose cells received a drift_warn in the last 24h.
// Verdict: atlas_conviction_daily.verdict (POSITIVE/NEUTRAL/NEGATIVE), migration 092.
// Empty book shortcut: held set empty → both arrays [] with no SQL queries.

import 'server-only'
import sql from '@/lib/db'
import { getHeldIidSet } from './portfolio_holdings'

// ---------------------------------------------------------------------------
// Public types
// ---------------------------------------------------------------------------

export type StockFlip = {
  instrument_id: string
  ticker: string
  yesterday_action: 'POSITIVE' | 'NEUTRAL' | 'NEGATIVE' | null
  today_action: 'POSITIVE' | 'NEUTRAL' | 'NEGATIVE' | null
  /** ISO date (YYYY-MM-DD) — the most recent snapshot_date */
  date_changed: string
}

export type BookDiff = {
  /** Held positions where conviction flipped overnight */
  held_iids_flipped: StockFlip[]
  /** Held positions in cells that drifted to drift_warn in last 24h */
  held_drift_warns: StockFlip[]
}

// ---------------------------------------------------------------------------
// Internal row types
// ---------------------------------------------------------------------------

type DateRow = { d: string | null; d_prev: string | null }

type FlipRow = {
  instrument_id: string
  ticker: string | null
  yesterday_action: string | null
  today_action: string | null
  date_changed: string
}

type DriftRow = {
  instrument_id: string
  ticker: string | null
  today_action: string | null
  date_changed: string
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function toStockFlip(r: FlipRow): StockFlip {
  return {
    instrument_id: r.instrument_id,
    ticker: r.ticker ?? r.instrument_id,
    yesterday_action: (r.yesterday_action as StockFlip['yesterday_action']) ?? null,
    today_action: (r.today_action as StockFlip['today_action']) ?? null,
    date_changed: r.date_changed,
  }
}

function driftToFlip(r: DriftRow, dateChanged: string): StockFlip {
  return {
    instrument_id: r.instrument_id,
    ticker: r.ticker ?? r.instrument_id,
    yesterday_action: null,
    today_action: (r.today_action as StockFlip['today_action']) ?? null,
    date_changed: dateChanged,
  }
}

// ---------------------------------------------------------------------------
// Main export
// ---------------------------------------------------------------------------

/** Portfolio-level diff. Empty book → both arrays []. First snapshot → yesterday_action=null. */
export async function getBookDiff(): Promise<BookDiff> {
  const heldSet = await getHeldIidSet()

  if (heldSet.size === 0) {
    return { held_iids_flipped: [], held_drift_warns: [] }
  }

  const heldArray = Array.from(heldSet)

  const dateRows = await sql<DateRow[]>`
    SELECT
      MAX(snapshot_date)::text AS d,
      (
        SELECT MAX(snapshot_date)::text
        FROM atlas.atlas_conviction_daily
        WHERE snapshot_date < (SELECT MAX(snapshot_date) FROM atlas.atlas_conviction_daily)
      ) AS d_prev
    FROM atlas.atlas_conviction_daily
  `

  const todayDate: string | null = dateRows[0]?.d ?? null

  if (todayDate === null) {
    return { held_iids_flipped: [], held_drift_warns: [] }
  }

  const prevDate: string | null = dateRows[0]?.d_prev ?? null

  const [flipRows, driftRows] = await Promise.all([
    _queryFlipped(heldArray, todayDate, prevDate),
    _queryDriftWarns(heldArray, todayDate),
  ])

  return {
    held_iids_flipped: flipRows.map(toStockFlip),
    held_drift_warns: driftRows.map((r) => driftToFlip(r, todayDate)),
  }
}

// ---------------------------------------------------------------------------
// Sub-queries
// ---------------------------------------------------------------------------

async function _queryFlipped(
  heldIids: string[],
  todayDate: string,
  prevDate: string | null,
): Promise<FlipRow[]> {
  if (prevDate === null) {
    return sql<FlipRow[]>`
      SELECT
        cd.instrument_id::text,
        us.symbol              AS ticker,
        NULL::text             AS yesterday_action,
        cd.verdict::text       AS today_action,
        ${todayDate}           AS date_changed
      FROM atlas.atlas_conviction_daily cd
      LEFT JOIN atlas.atlas_universe_stocks us
        ON us.instrument_id = cd.instrument_id
      WHERE cd.snapshot_date = ${todayDate}::date
        AND cd.instrument_id = ANY(${heldIids}::uuid[])
      ORDER BY cd.instrument_id
    `
  }

  return sql<FlipRow[]>`
    WITH today AS (
      SELECT instrument_id, verdict AS today_action
      FROM atlas.atlas_conviction_daily
      WHERE snapshot_date = ${todayDate}::date
        AND instrument_id = ANY(${heldIids}::uuid[])
    ),
    yesterday AS (
      SELECT instrument_id, verdict AS yesterday_action
      FROM atlas.atlas_conviction_daily
      WHERE snapshot_date = ${prevDate}::date
        AND instrument_id = ANY(${heldIids}::uuid[])
    )
    SELECT
      t.instrument_id::text,
      us.symbol                AS ticker,
      y.yesterday_action::text,
      t.today_action::text,
      ${todayDate}             AS date_changed
    FROM today t
    LEFT JOIN yesterday y ON y.instrument_id = t.instrument_id
    LEFT JOIN atlas.atlas_universe_stocks us
      ON us.instrument_id = t.instrument_id
    WHERE t.today_action IS DISTINCT FROM y.yesterday_action
    ORDER BY t.instrument_id
  `
}

async function _queryDriftWarns(
  heldIids: string[],
  todayDate: string,
): Promise<DriftRow[]> {
  return sql<DriftRow[]>`
    SELECT DISTINCT
      sc.instrument_id::text,
      us.symbol              AS ticker,
      cd_snap.verdict::text  AS today_action,
      del.ts::date::text     AS date_changed
    FROM atlas.atlas_drift_event_log del
    JOIN atlas.atlas_signal_calls sc
      ON sc.cell_id = del.cell_id
      AND sc.exit_date IS NULL
      AND sc.instrument_id = ANY(${heldIids}::uuid[])
    LEFT JOIN atlas.atlas_conviction_daily cd_snap
      ON cd_snap.instrument_id = sc.instrument_id
      AND cd_snap.snapshot_date = ${todayDate}::date
    LEFT JOIN atlas.atlas_universe_stocks us
      ON us.instrument_id = sc.instrument_id
    WHERE del.ts >= NOW() - INTERVAL '24 hours'
      AND del.status_after = 'drift_warn'
    ORDER BY sc.instrument_id
  `
}
