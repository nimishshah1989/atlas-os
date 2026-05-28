// frontend/src/lib/queries/v6/calls.ts
//
// Data layer for /calls (Page 08 — Calls Performance).
// Primary source: atlas.mv_calls_performance (587 rows, real win-rate data).
//
// MV columns: signal_call_id, instrument_id, symbol, company_name, cell_name,
//   cap_tier, tenure, action, entry_date, confidence_unconditional,
//   predicted_excess, stock_ret_pct, bench_ret_pct, realized_excess_pct,
//   days_in_position, is_hit, status, refreshed_at
//
// Data reality as of 2026-05-27:
//   - 576/587 rows have non-null realized_excess_pct
//   - 587/587 rows have is_hit
//   - Hit rates per cell range 25%–92%
//   - status = 'in_flight' | 'closed'
//
// Exports:
//   getCallsHero()              — aggregate hero stats from MV
//   getCallsLedger(limit)       — full rows from mv_calls_performance
//   getMatrix24Cells()          — GROUP BY cap_tier × tenure × action (win-rate)
//   getTopSixCells()            — {best: [3], worst: [3]} by avg realized_excess_pct
//   getCallsSummaryByCell()     — per-cell summary for trajectories section
//   getCumulativeExcessSeries() — daily series for line chart

import 'server-only'
import sql from '@/lib/db'

// Re-export fmtSignedPct from the shared utility for convenience.
// Components should import from '@/lib/format-number' directly to avoid
// importing server-only code into client components.
export { fmtSignedPct } from '@/lib/format-number'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type CallsHero = {
  total_calls: number
  open_calls: number
  closed_calls: number
  buy_calls: number
  avoid_calls: number
  /** Decimal fraction avg realized excess across all calls with data */
  avg_realized_excess: number | null
  /** Overall hit rate (win rate) as decimal fraction */
  overall_hit_rate: number | null
  data_as_of: string
}

export type CallRow = {
  signal_call_id: string
  symbol: string
  company_name: string | null
  cap_tier: string
  tenure: string
  action: string
  /** BUY or AVOID — display vocab per CONTEXT.md */
  action_display: string
  cell_name: string
  cell_label: string
  entry_date: string
  days_in_position: number
  /** Decimal fraction from MV.predicted_excess */
  predicted_excess: number | null
  /** Decimal fraction from MV.realized_excess_pct (non-null for 576/587) */
  realized_excess_pct: number | null
  /** Whether this call was a hit (beat benchmark) */
  is_hit: boolean | null
  /** 'in_flight' | 'closed' — from MV, not synthesized */
  status: string
}

export type WinRateCell = {
  cap_tier: string
  tenure: string
  action: string
  call_count: number
  /** Realized win rate as decimal fraction (e.g. 0.72 = 72%) */
  hit_rate: number | null
  /** Average realized excess, decimal fraction */
  avg_realized_excess: number | null
}

export type TopCell = {
  cell_name: string
  cell_label: string
  cap_tier: string
  tenure: string
  action: string
  action_display: string
  call_count: number
  hit_rate: number | null
  avg_realized_excess: number | null
  avg_predicted_excess: number | null
  in_flight_count: number
}

export type TopSixResult = {
  best: TopCell[]
  worst: TopCell[]
}

export type CumulativeExcessPoint = {
  entry_date: string
  avg_realized_excess: number | null
}

// ---------------------------------------------------------------------------
// Raw DB row shapes
// ---------------------------------------------------------------------------

type HeroRaw = {
  total_calls: string
  open_calls: string
  closed_calls: string
  buy_calls: string
  avoid_calls: string
  avg_realized_excess: string | null
  overall_hit_rate: string | null
  data_as_of: string | null
}

type CallRowRaw = {
  signal_call_id: string
  symbol: string | null
  company_name: string | null
  cap_tier: string
  tenure: string
  action: string
  cell_name: string | null
  entry_date: string
  days_in_position: string | null
  predicted_excess: string | null
  realized_excess_pct: string | null
  is_hit: boolean | null
  status: string
}

type WinRateCellRaw = {
  cap_tier: string
  tenure: string
  action: string
  call_count: string
  hit_rate: string | null
  avg_realized_excess: string | null
}

type TopCellRaw = {
  cap_tier: string
  tenure: string
  action: string
  cell_name: string | null
  call_count: string
  hit_rate: string | null
  avg_realized_excess: string | null
  avg_predicted_excess: string | null
  in_flight_count: string
}

type CumulativeExcessRaw = {
  entry_date: string
  avg_realized_excess: string | null
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function actionDisplay(action: string): string {
  if (action === 'POSITIVE') return 'BUY'
  if (action === 'NEGATIVE') return 'AVOID'
  return action
}

function cellLabel(cap_tier: string, tenure: string, action: string): string {
  const tier = cap_tier === 'Large' ? 'L' : cap_tier === 'Mid' ? 'M' : 'S'
  const dir = action === 'POSITIVE' ? 'POS' : action === 'NEGATIVE' ? 'NEG' : action
  return `${tier} ${tenure} ${dir}`
}

// ---------------------------------------------------------------------------
// getCallsHero
// ---------------------------------------------------------------------------

/**
 * Aggregate hero stats for the Calls Performance page header.
 * Reads from atlas.mv_calls_performance — real win-rate and realized excess data.
 * status='in_flight' = open, status='closed' = closed.
 */
export async function getCallsHero(): Promise<CallsHero> {
  const rows = await sql<HeroRaw[]>`
    SELECT
      COUNT(*)::text                                                        AS total_calls,
      COUNT(*) FILTER (WHERE status = 'in_flight')::text                   AS open_calls,
      COUNT(*) FILTER (WHERE status = 'closed')::text                      AS closed_calls,
      COUNT(*) FILTER (WHERE action = 'POSITIVE')::text                    AS buy_calls,
      COUNT(*) FILTER (WHERE action = 'NEGATIVE')::text                    AS avoid_calls,
      AVG(realized_excess_pct)::text                                        AS avg_realized_excess,
      AVG(is_hit::int)::text                                                AS overall_hit_rate,
      MAX(refreshed_at)::date::text                                         AS data_as_of
    FROM atlas.mv_calls_performance
    WHERE action IN ('POSITIVE', 'NEGATIVE')
  `

  if (rows.length === 0 || rows[0].total_calls === '0') {
    return {
      total_calls: 0,
      open_calls: 0,
      closed_calls: 0,
      buy_calls: 0,
      avoid_calls: 0,
      avg_realized_excess: null,
      overall_hit_rate: null,
      data_as_of: new Date().toISOString().slice(0, 10),
    }
  }

  const r = rows[0]
  return {
    total_calls: parseInt(r.total_calls, 10),
    open_calls: parseInt(r.open_calls, 10),
    closed_calls: parseInt(r.closed_calls, 10),
    buy_calls: parseInt(r.buy_calls, 10),
    avoid_calls: parseInt(r.avoid_calls, 10),
    avg_realized_excess: r.avg_realized_excess != null ? parseFloat(r.avg_realized_excess) : null,
    overall_hit_rate: r.overall_hit_rate != null ? parseFloat(r.overall_hit_rate) : null,
    data_as_of: r.data_as_of ?? new Date().toISOString().slice(0, 10),
  }
}

// ---------------------------------------------------------------------------
// getCallsLedger
// ---------------------------------------------------------------------------

/**
 * Full call ledger from mv_calls_performance.
 * MV already has symbol + company_name — no JOIN needed.
 * status column is used directly (not synthesized from exit_date).
 */
export async function getCallsLedger(
  limit: number = 587,
): Promise<CallRow[]> {
  const rows = await sql<CallRowRaw[]>`
    SELECT
      signal_call_id::text,
      symbol,
      company_name,
      cap_tier::text,
      tenure::text,
      action::text,
      cell_name,
      entry_date::text,
      days_in_position::text,
      predicted_excess::text,
      realized_excess_pct::text,
      is_hit,
      status::text
    FROM atlas.mv_calls_performance
    WHERE action IN ('POSITIVE', 'NEGATIVE')
    ORDER BY entry_date DESC, signal_call_id
    LIMIT ${limit}
  `

  return rows.map((r) => ({
    signal_call_id: r.signal_call_id,
    symbol: r.symbol ?? r.signal_call_id.slice(0, 8),
    company_name: r.company_name ?? null,
    cap_tier: r.cap_tier,
    tenure: r.tenure,
    action: r.action,
    action_display: actionDisplay(r.action),
    cell_name: r.cell_name ?? cellLabel(r.cap_tier, r.tenure, r.action),
    cell_label: cellLabel(r.cap_tier, r.tenure, r.action),
    entry_date: r.entry_date,
    days_in_position: r.days_in_position != null ? parseInt(r.days_in_position, 10) : 0,
    predicted_excess: r.predicted_excess != null ? parseFloat(r.predicted_excess) : null,
    realized_excess_pct: r.realized_excess_pct != null ? parseFloat(r.realized_excess_pct) : null,
    is_hit: r.is_hit ?? null,
    status: r.status,
  }))
}

// ---------------------------------------------------------------------------
// getMatrix24Cells
// ---------------------------------------------------------------------------

/**
 * Groups calls by (cap_tier × tenure × action) for the 24-cell win-rate matrix.
 * Shows realized hit_rate (win rate) and avg realized_excess_pct per cell.
 */
export async function getMatrix24Cells(): Promise<WinRateCell[]> {
  const rows = await sql<WinRateCellRaw[]>`
    SELECT
      cap_tier::text,
      tenure::text,
      action::text,
      COUNT(*)::text                   AS call_count,
      AVG(is_hit::int)::text           AS hit_rate,
      AVG(realized_excess_pct)::text   AS avg_realized_excess
    FROM atlas.mv_calls_performance
    WHERE action IN ('POSITIVE', 'NEGATIVE')
    GROUP BY cap_tier, tenure, action
    ORDER BY cap_tier, tenure, action
  `

  return rows.map((r) => ({
    cap_tier: r.cap_tier,
    tenure: r.tenure,
    action: r.action,
    call_count: parseInt(r.call_count, 10),
    hit_rate: r.hit_rate != null ? parseFloat(r.hit_rate) : null,
    avg_realized_excess: r.avg_realized_excess != null ? parseFloat(r.avg_realized_excess) : null,
  }))
}

// ---------------------------------------------------------------------------
// getTopSixCells
// ---------------------------------------------------------------------------

/**
 * Returns {best: top 3, worst: bottom 3} by avg realized_excess_pct.
 * Explicitly structured so SixCellCards can render badges correctly.
 */
export async function getTopSixCells(): Promise<TopSixResult> {
  const rows = await sql<TopCellRaw[]>`
    SELECT
      cap_tier::text,
      tenure::text,
      action::text,
      cell_name,
      COUNT(*)::text                                         AS call_count,
      AVG(is_hit::int)::text                                 AS hit_rate,
      AVG(realized_excess_pct)::text                         AS avg_realized_excess,
      AVG(predicted_excess)::text                            AS avg_predicted_excess,
      COUNT(*) FILTER (WHERE status = 'in_flight')::text     AS in_flight_count
    FROM atlas.mv_calls_performance
    WHERE action IN ('POSITIVE', 'NEGATIVE')
    GROUP BY cap_tier, tenure, action, cell_name
    HAVING COUNT(*) >= 1
    ORDER BY AVG(COALESCE(realized_excess_pct, 0)) DESC
  `

  const mapped: TopCell[] = rows.map((r) => ({
    cell_name: r.cell_name ?? cellLabel(r.cap_tier, r.tenure, r.action),
    cell_label: cellLabel(r.cap_tier, r.tenure, r.action),
    cap_tier: r.cap_tier,
    tenure: r.tenure,
    action: r.action,
    action_display: actionDisplay(r.action),
    call_count: parseInt(r.call_count, 10),
    hit_rate: r.hit_rate != null ? parseFloat(r.hit_rate) : null,
    avg_realized_excess: r.avg_realized_excess != null ? parseFloat(r.avg_realized_excess) : null,
    avg_predicted_excess: r.avg_predicted_excess != null ? parseFloat(r.avg_predicted_excess) : null,
    in_flight_count: parseInt(r.in_flight_count, 10),
  }))

  const best = mapped.slice(0, 3)
  const worst = mapped.length >= 3 ? mapped.slice(mapped.length - 3) : mapped.slice(0)

  return { best, worst }
}

// ---------------------------------------------------------------------------
// getCallsSummaryByCell
// ---------------------------------------------------------------------------

/**
 * Per-cell summary ordered by avg realized_excess_pct DESC.
 * Used for the trajectories section (all cells with >= 3 calls).
 */
export async function getCallsSummaryByCell(): Promise<TopCell[]> {
  const rows = await sql<TopCellRaw[]>`
    SELECT
      cap_tier::text,
      tenure::text,
      action::text,
      cell_name,
      COUNT(*)::text                                         AS call_count,
      AVG(is_hit::int)::text                                 AS hit_rate,
      AVG(realized_excess_pct)::text                         AS avg_realized_excess,
      AVG(predicted_excess)::text                            AS avg_predicted_excess,
      COUNT(*) FILTER (WHERE status = 'in_flight')::text     AS in_flight_count
    FROM atlas.mv_calls_performance
    WHERE action IN ('POSITIVE', 'NEGATIVE')
    GROUP BY cap_tier, tenure, action, cell_name
    HAVING COUNT(*) >= 3
    ORDER BY AVG(COALESCE(realized_excess_pct, 0)) DESC
  `

  return rows.map((r) => ({
    cell_name: r.cell_name ?? cellLabel(r.cap_tier, r.tenure, r.action),
    cell_label: cellLabel(r.cap_tier, r.tenure, r.action),
    cap_tier: r.cap_tier,
    tenure: r.tenure,
    action: r.action,
    action_display: actionDisplay(r.action),
    call_count: parseInt(r.call_count, 10),
    hit_rate: r.hit_rate != null ? parseFloat(r.hit_rate) : null,
    avg_realized_excess: r.avg_realized_excess != null ? parseFloat(r.avg_realized_excess) : null,
    avg_predicted_excess: r.avg_predicted_excess != null ? parseFloat(r.avg_predicted_excess) : null,
    in_flight_count: parseInt(r.in_flight_count, 10),
  }))
}

// ---------------------------------------------------------------------------
// getCumulativeExcessSeries
// ---------------------------------------------------------------------------

/**
 * Daily series of avg realized_excess_pct grouped by entry_date.
 * Feeds the cumulative excess line chart (Recharts LineChart).
 */
export async function getCumulativeExcessSeries(): Promise<CumulativeExcessPoint[]> {
  const rows = await sql<CumulativeExcessRaw[]>`
    SELECT
      entry_date::text,
      AVG(realized_excess_pct)::text AS avg_realized_excess
    FROM atlas.mv_calls_performance
    WHERE action IN ('POSITIVE', 'NEGATIVE')
    GROUP BY entry_date
    ORDER BY entry_date
  `

  return rows.map((r) => ({
    entry_date: r.entry_date,
    avg_realized_excess: r.avg_realized_excess != null ? parseFloat(r.avg_realized_excess) : null,
  }))
}
