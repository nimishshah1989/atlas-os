// frontend/src/lib/queries/v6/cells.ts
//
// Server-only query module for atlas_cell_definitions.
//
// Sources:
//   atlas_cell_definitions (migration 080) — cap_tier / tenure / action /
//     confidence_unconditional / friction_adjusted_excess / drift_status /
//     methodology_lock_ref / rule_dsl
//   atlas_signal_calls (migration 080) — predicted_excess (latest ACTIVE per cell)
//
// Notes:
//   - bh_fdr_q does NOT exist on atlas_cell_definitions (migration 080 scan);
//     the column is returned as NULL via a SQL literal.
//   - predicted_excess is NOT on atlas_cell_definitions; sourced from latest
//     open (exit_date IS NULL) atlas_signal_calls row per cell_id.
//   - getAllCells and getMatrixCells are memoized per server request via
//     React.cache(). getCellById is a bare async function (different input
//     per call — use getAllCells + find when you need multiple lookups).

import 'server-only'
import { cache } from 'react'
import sql from '@/lib/db'

// ---------------------------------------------------------------------------
// Public types
// ---------------------------------------------------------------------------

export type CellState = 'POSITIVE' | 'NEUTRAL' | 'NEGATIVE'
export type DriftStatus = 'healthy' | 'drift_warn' | 'deprecated'
export type Tenure = '1m' | '3m' | '6m' | '12m'
export type CapTier = 'Small' | 'Mid' | 'Large'

export type Cell = {
  cell_id: string
  cap_tier: CapTier
  tenure: Tenure
  action: CellState
  confidence_unconditional: string        // stringified Decimal
  friction_adjusted_excess: string        // stringified Decimal
  predicted_excess: string | null         // from atlas_signal_calls latest ACTIVE
  drift_status: DriftStatus
  bh_fdr_q: string | null                 // column not yet in schema → always null
  methodology_lock_ref: string | null
  rule_dsl: Record<string, unknown>       // JSONB rule_dsl
}

export type MatrixCell = Cell & {
  n_firing_today: number
}

// ---------------------------------------------------------------------------
// Internal row types (postgres-js returns plain objects)
// ---------------------------------------------------------------------------

type CellRow = {
  cell_id: string
  cap_tier: string
  tenure: string
  action: string
  confidence_unconditional: string | null
  friction_adjusted_excess: string | null
  predicted_excess: string | null
  drift_status: string
  bh_fdr_q: string | null
  methodology_lock_ref: string | null
  rule_dsl: Record<string, unknown>
}

type MatrixCellRow = CellRow & {
  n_firing_today: string  // COUNT() comes back as string from postgres-js
}

// ---------------------------------------------------------------------------
// Row → Cell mapper
// ---------------------------------------------------------------------------

function mapCell(r: CellRow): Cell {
  return {
    cell_id: r.cell_id,
    cap_tier: r.cap_tier as CapTier,
    tenure: r.tenure as Tenure,
    action: r.action as CellState,
    confidence_unconditional: r.confidence_unconditional ?? '0',
    friction_adjusted_excess: r.friction_adjusted_excess ?? '0',
    predicted_excess: r.predicted_excess ?? null,
    drift_status: r.drift_status as DriftStatus,
    bh_fdr_q: r.bh_fdr_q ?? null,
    methodology_lock_ref: r.methodology_lock_ref ?? null,
    rule_dsl: r.rule_dsl ?? {},
  }
}

// ---------------------------------------------------------------------------
// Get all cells (memoized per server request)
// ---------------------------------------------------------------------------

export const getAllCells: () => Promise<Cell[]> = cache(async () => {
  const rows = await sql<CellRow[]>`
    SELECT
      cd.cell_id::text,
      cd.cap_tier::text,
      cd.tenure::text,
      cd.action::text,
      cd.confidence_unconditional::text,
      cd.friction_adjusted_excess::text,
      (SELECT sc.predicted_excess::text
       FROM atlas.atlas_signal_calls sc
       WHERE sc.cell_id = cd.cell_id
         AND sc.exit_date IS NULL
       ORDER BY sc.entry_date DESC
       LIMIT 1) AS predicted_excess,
      cd.drift_status::text,
      NULL::text AS bh_fdr_q,
      cd.methodology_lock_ref,
      cd.rule_dsl
    FROM atlas.atlas_cell_definitions cd
    ORDER BY cd.cap_tier, cd.tenure, cd.action
  `
  return rows.map(mapCell)
})

// ---------------------------------------------------------------------------
// Get one cell by id (NOT memoized — per-call different input)
// ---------------------------------------------------------------------------

export async function getCellById(cell_id: string): Promise<Cell | null> {
  const rows = await sql<CellRow[]>`
    SELECT
      cd.cell_id::text,
      cd.cap_tier::text,
      cd.tenure::text,
      cd.action::text,
      cd.confidence_unconditional::text,
      cd.friction_adjusted_excess::text,
      (SELECT sc.predicted_excess::text
       FROM atlas.atlas_signal_calls sc
       WHERE sc.cell_id = cd.cell_id
         AND sc.exit_date IS NULL
       ORDER BY sc.entry_date DESC
       LIMIT 1) AS predicted_excess,
      cd.drift_status::text,
      NULL::text AS bh_fdr_q,
      cd.methodology_lock_ref,
      cd.rule_dsl
    FROM atlas.atlas_cell_definitions cd
    WHERE cd.cell_id = ${cell_id}::uuid
  `
  return rows.length > 0 ? mapCell(rows[0]) : null
}

// ---------------------------------------------------------------------------
// Matrix view with firing-today count (memoized per server request)
// ---------------------------------------------------------------------------

export const getMatrixCells: () => Promise<MatrixCell[]> = cache(async () => {
  const rows = await sql<MatrixCellRow[]>`
    SELECT
      cd.cell_id::text,
      cd.cap_tier::text,
      cd.tenure::text,
      cd.action::text,
      cd.confidence_unconditional::text,
      cd.friction_adjusted_excess::text,
      (SELECT sc.predicted_excess::text
       FROM atlas.atlas_signal_calls sc
       WHERE sc.cell_id = cd.cell_id
         AND sc.exit_date IS NULL
       ORDER BY sc.entry_date DESC
       LIMIT 1) AS predicted_excess,
      cd.drift_status::text,
      NULL::text AS bh_fdr_q,
      cd.methodology_lock_ref,
      cd.rule_dsl,
      COALESCE(firing.n, 0)::text AS n_firing_today
    FROM atlas.atlas_cell_definitions cd
    LEFT JOIN LATERAL (
      SELECT COUNT(*)::int AS n
      FROM atlas.atlas_signal_calls sc
      WHERE sc.cell_id = cd.cell_id
        AND sc.exit_date IS NULL
        AND sc.date = (
          SELECT MAX(date)
          FROM atlas.atlas_signal_calls
        )
    ) firing ON true
    ORDER BY cd.cap_tier, cd.tenure, cd.action
  `

  return rows.map((r): MatrixCell => ({
    ...mapCell(r),
    n_firing_today: Number(r.n_firing_today),
  }))
})
