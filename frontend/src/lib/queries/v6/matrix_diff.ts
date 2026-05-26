// frontend/src/lib/queries/v6/matrix_diff.ts
//
// Universe-level diff: which cells started firing, went dormant, or gained
// drift_warn overnight. Compares atlas_signal_calls at D vs D-1 where D and
// D-1 are resolved from the actual populated dates in the table (handles
// weekends, holidays, and gaps automatically).
//
// atlas_drift_event_log is EMPTY at v6.0 launch (no drift-detector cron yet).
// All three query paths handle an empty table → empty array; no placeholders.

import 'server-only'
import sql from '@/lib/db'

// ---------------------------------------------------------------------------
// Public types
// ---------------------------------------------------------------------------
export type CellSummary = {
  cell_id: string
  cap_tier: 'Small' | 'Mid' | 'Large'
  tenure: '1m' | '3m' | '6m' | '12m'
  action: 'POSITIVE' | 'NEUTRAL' | 'NEGATIVE'
  /** Derived from confidence_unconditional (0..1): AAA / AA / A / BBB / BB / B */
  grade: string
  /** Stringified Decimal — confidence_unconditional from atlas_signal_calls */
  confidence_unconditional: string
  /** ISO date (YYYY-MM-DD): date the signal call was created (new_firing) or
   *  the last active date (cells_dormant). */
  date_changed: string
}

export type MatrixDiff = {
  /** Cells active today (open signal_call), not active yesterday. */
  new_cells_firing: CellSummary[]
  /** Cells that had an open signal_call yesterday but not today. */
  cells_dormant: CellSummary[]
  /** Cells whose drift_status flipped to 'drift_warn' in the last 24 hours.
   *  Empty at v6.0 launch — no drift detector cron deployed yet. */
  new_drift_warns: CellSummary[]
}

// ---------------------------------------------------------------------------
// Internal types (raw DB rows — grade computed in TypeScript from confidence)
// ---------------------------------------------------------------------------
type DateRow = { d: string | null; d_prev: string | null }

type RawCellRow = {
  cell_id: string
  cap_tier: string
  tenure: string
  action: string
  confidence_unconditional: string | null
  date_changed: string
}

// ---------------------------------------------------------------------------
// Grade derivation — mirrors funds_holding_stock.ts convention, scaled 0..1
// NULL confidence defaults to 0 → 'B'.
// ---------------------------------------------------------------------------
export function deriveGrade(conf: string | null): string {
  const v = conf !== null ? parseFloat(conf) : 0
  if (v >= 0.90) return 'AAA'
  if (v >= 0.80) return 'AA'
  if (v >= 0.70) return 'A'
  if (v >= 0.60) return 'BBB'
  if (v >= 0.50) return 'BB'
  return 'B'
}

// ---------------------------------------------------------------------------
// Mapper
// ---------------------------------------------------------------------------

function toSummary(r: RawCellRow): CellSummary {
  return {
    cell_id: r.cell_id,
    cap_tier: r.cap_tier as CellSummary['cap_tier'],
    tenure: r.tenure as CellSummary['tenure'],
    action: r.action as CellSummary['action'],
    grade: deriveGrade(r.confidence_unconditional),
    confidence_unconditional: r.confidence_unconditional ?? '0',
    date_changed: r.date_changed,
  }
}

// ---------------------------------------------------------------------------
// Main export
// ---------------------------------------------------------------------------

/**
 * Returns matrix diff: which cells started firing overnight, which went
 * dormant, and which gained a drift_warn in the last 24 hours.
 *
 * D and D-1 are resolved from the actual populated dates in atlas_signal_calls
 * so the function is correct across weekends, holidays, and any gap.
 *
 * Edge cases:
 *  - First-ever snapshot (no D-1): new_cells_firing filled, cells_dormant [].
 *  - No signal_calls at all: all three arrays empty.
 *  - atlas_drift_event_log empty (v6.0 launch state): new_drift_warns [].
 */
export async function getMatrixDiff(): Promise<MatrixDiff> {
  // Resolve D and D-1 directly from atlas_signal_calls (self-consistent for
  // weekends, holidays, any calendar gap).
  const dateRows = await sql<DateRow[]>`
    SELECT
      MAX(date)::text AS d,
      (SELECT MAX(date)::text FROM atlas.atlas_signal_calls
       WHERE date < (SELECT MAX(date) FROM atlas.atlas_signal_calls)) AS d_prev
    FROM atlas.atlas_signal_calls
  `

  const todayDate: string | null = dateRows[0]?.d ?? null
  const prevDate: string | null = dateRows[0]?.d_prev ?? null

  // No signal_calls at all → empty diff, no further queries.
  if (todayDate === null) {
    return { new_cells_firing: [], cells_dormant: [], new_drift_warns: [] }
  }

  // Run content queries in parallel. _queryDormant skipped when prevDate is
  // null (first-ever snapshot → no dormant cells possible).
  const [firingRows, dormantRows, driftRows] = await Promise.all([
    _queryNewFiring(todayDate, prevDate),
    prevDate !== null ? _queryDormant(todayDate, prevDate) : Promise.resolve<RawCellRow[]>([]),
    _queryDriftWarns(),
  ])

  return {
    new_cells_firing: firingRows.map(toSummary),
    cells_dormant: dormantRows.map(toSummary),
    new_drift_warns: driftRows.map(toSummary),
  }
}

// ---------------------------------------------------------------------------
// Sub-queries
// ---------------------------------------------------------------------------

async function _queryNewFiring(
  todayDate: string,
  prevDate: string | null,
): Promise<RawCellRow[]> {
  if (prevDate === null) {
    // First snapshot — all of today's cells are "new". DISTINCT ON (cell_id)
    // so we get ONE row per distinct cell, not one per signal_call (which
    // would give 363 dupes when there are only 18 distinct cells firing).
    return sql<RawCellRow[]>`
      SELECT DISTINCT ON (sc.cell_id)
             sc.cell_id::text, cd.cap_tier::text, sc.tenure::text, sc.action::text,
             sc.confidence_unconditional::text, sc.date::text AS date_changed
      FROM atlas.atlas_signal_calls sc
      JOIN atlas.atlas_cell_definitions cd ON cd.cell_id = sc.cell_id
      WHERE sc.date = ${todayDate}::date AND sc.exit_date IS NULL
      ORDER BY sc.cell_id, cd.cap_tier, sc.tenure, sc.action
    `
  }

  return sql<RawCellRow[]>`
    SELECT DISTINCT ON (sc.cell_id)
           sc.cell_id::text, cd.cap_tier::text, sc.tenure::text, sc.action::text,
           sc.confidence_unconditional::text, sc.date::text AS date_changed
    FROM atlas.atlas_signal_calls sc
    JOIN atlas.atlas_cell_definitions cd ON cd.cell_id = sc.cell_id
    WHERE sc.date = ${todayDate}::date
      AND sc.exit_date IS NULL
      AND sc.cell_id NOT IN (
        SELECT DISTINCT cell_id FROM atlas.atlas_signal_calls
        WHERE date = ${prevDate}::date AND exit_date IS NULL
      )
    ORDER BY sc.cell_id, cd.cap_tier, sc.tenure, sc.action
  `
}

async function _queryDormant(
  todayDate: string,
  prevDate: string,
): Promise<RawCellRow[]> {
  return sql<RawCellRow[]>`
    SELECT sc.cell_id::text, cd.cap_tier::text, sc.tenure::text, sc.action::text,
           sc.confidence_unconditional::text, ${prevDate} AS date_changed
    FROM atlas.atlas_signal_calls sc
    JOIN atlas.atlas_cell_definitions cd ON cd.cell_id = sc.cell_id
    WHERE sc.date = ${prevDate}::date
      AND sc.exit_date IS NULL
      AND sc.cell_id NOT IN (
        SELECT DISTINCT cell_id FROM atlas.atlas_signal_calls
        WHERE date = ${todayDate}::date AND exit_date IS NULL
      )
    ORDER BY cd.cap_tier, sc.tenure, sc.action
  `
}

async function _queryDriftWarns(): Promise<RawCellRow[]> {
  // Empty at v6.0 launch. Returns zero rows from an empty table — no guard needed.
  return sql<RawCellRow[]>`
    SELECT del.cell_id::text, cd.cap_tier::text, cd.tenure::text, cd.action::text,
           cd.confidence_unconditional::text, del.ts::date::text AS date_changed
    FROM atlas.atlas_drift_event_log del
    JOIN atlas.atlas_cell_definitions cd ON cd.cell_id = del.cell_id
    WHERE del.ts >= NOW() - INTERVAL '24 hours'
      AND del.status_after = 'drift_warn'
    ORDER BY del.ts DESC
  `
}
