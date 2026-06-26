// frontend/src/lib/queries/v6/recent_signal_calls.ts
//
// Query: individual signal_call events from foundation_staging.atlas_signal_calls.
// Three public functions:
//   getRecentSignalCalls  → today-page "recent activity" feed
//   getSignalCallsByIid   → stock-detail audit trail
//   getSignalCallsByCell  → cell-detail history
//
// Schema: migrations/versions/080_v6_scorecard_signals_cells_regime.py
// NOTE: atlas_signal_calls.date = trigger date (aliased to entry_date).
//       entry_price does NOT exist in schema 080 → returns NULL.
//       ticker from LEFT JOIN atlas_universe_stocks; fallback = instrument_id::text.

import 'server-only'
import sql from '@/lib/db'

// ---------------------------------------------------------------------------
// Public types
// ---------------------------------------------------------------------------

export type SignalCallEvent = {
  signal_call_id: string
  cell_id: string
  /** "<cap_tier> <tenure> <action>" e.g. "Mid 12m POSITIVE" */
  cell_name: string
  instrument_id: string
  /** NSE/BSE symbol; falls back to instrument_id::text when not in universe */
  ticker: string
  action: 'POSITIVE' | 'NEUTRAL' | 'NEGATIVE'
  cap_tier: 'Small' | 'Mid' | 'Large'
  tenure: '1m' | '3m' | '6m' | '12m'
  /** ISO date YYYY-MM-DD: sc.date (trigger date) */
  entry_date: string
  /** NULL — entry_price column does not exist in schema 080 */
  entry_price: string | null
  /** Stringified Decimal (0..1) */
  confidence_unconditional: string
  /** Stringified Decimal — null when not computed */
  predicted_excess: string | null
  /** ISO date YYYY-MM-DD or null when position still open */
  exit_date: string | null
  /** true when exit_date IS NULL */
  is_active: boolean
}

// Internal raw DB row
type RawRow = {
  signal_call_id: string
  cell_id: string
  cell_name: string
  instrument_id: string
  ticker: string | null
  action: string
  cap_tier: string
  tenure: string
  entry_date: string
  entry_price: string | null
  confidence_unconditional: string
  predicted_excess: string | null
  exit_date: string | null
  is_active: boolean
}

function toEvent(r: RawRow): SignalCallEvent {
  return {
    signal_call_id: r.signal_call_id,
    cell_id: r.cell_id,
    cell_name: r.cell_name,
    instrument_id: r.instrument_id,
    ticker: r.ticker ?? r.instrument_id, // fallback when not in universe
    action: r.action as SignalCallEvent['action'],
    cap_tier: r.cap_tier as SignalCallEvent['cap_tier'],
    tenure: r.tenure as SignalCallEvent['tenure'],
    entry_date: r.entry_date,
    entry_price: r.entry_price,
    confidence_unconditional: r.confidence_unconditional,
    predicted_excess: r.predicted_excess,
    exit_date: r.exit_date,
    is_active: r.is_active,
  }
}

// Shared SELECT columns (documented once; used in all three query functions)
// sc.date aliased to entry_date; NULL::text for entry_price (not in schema).

/**
 * Returns the most recent N signal calls fired in the last N calendar days.
 * Used by the Today page "Recent Activity" panel.
 * Empty table → returns []. days=0 → []. limit=0 → [].
 */
export async function getRecentSignalCalls(
  limit: number = 50,
  days: number = 7,
): Promise<SignalCallEvent[]> {
  const rows = await sql<RawRow[]>`
    SELECT sc.signal_call_id::text, sc.cell_id::text,
      CONCAT(sc.cap_tier_at_trigger::text, ' ', sc.tenure::text, ' ', sc.action::text) AS cell_name,
      sc.instrument_id::text, us.symbol AS ticker,
      sc.action::text AS action, sc.cap_tier_at_trigger::text AS cap_tier, sc.tenure::text AS tenure,
      sc.date::text AS entry_date, NULL::text AS entry_price,
      sc.confidence_unconditional::text, sc.predicted_excess::text,
      sc.exit_date::text, (sc.exit_date IS NULL) AS is_active
    FROM foundation_staging.atlas_signal_calls sc
    LEFT JOIN foundation_staging.instrument_master us ON us.instrument_id = sc.instrument_id
    WHERE sc.date >= CURRENT_DATE - (${days} || ' days')::interval
    ORDER BY sc.date DESC, sc.computed_at DESC
    LIMIT ${limit}
  `
  return rows.map(toEvent)
}

/**
 * Returns all historic signal calls for a specific instrument_id.
 * Used by the stock detail page audit trail (chronological history).
 * Empty result when iid has no calls. NULL ticker falls back to iid string.
 */
export async function getSignalCallsByIid(
  iid: string,
  limit: number = 20,
): Promise<SignalCallEvent[]> {
  const rows = await sql<RawRow[]>`
    SELECT sc.signal_call_id::text, sc.cell_id::text,
      CONCAT(sc.cap_tier_at_trigger::text, ' ', sc.tenure::text, ' ', sc.action::text) AS cell_name,
      sc.instrument_id::text, us.symbol AS ticker,
      sc.action::text AS action, sc.cap_tier_at_trigger::text AS cap_tier, sc.tenure::text AS tenure,
      sc.date::text AS entry_date, NULL::text AS entry_price,
      sc.confidence_unconditional::text, sc.predicted_excess::text,
      sc.exit_date::text, (sc.exit_date IS NULL) AS is_active
    FROM foundation_staging.atlas_signal_calls sc
    LEFT JOIN foundation_staging.instrument_master us ON us.instrument_id = sc.instrument_id
    WHERE sc.instrument_id = ${iid}::uuid
    ORDER BY sc.date DESC, sc.computed_at DESC
    LIMIT ${limit}
  `
  return rows.map(toEvent)
}

/**
 * Returns all historic signal calls fired by a specific cell.
 * Used by the cell detail page to show its firing history.
 * Empty result when cell_id has no calls.
 */
export async function getSignalCallsByCell(
  cell_id: string,
  limit: number = 20,
): Promise<SignalCallEvent[]> {
  const rows = await sql<RawRow[]>`
    SELECT sc.signal_call_id::text, sc.cell_id::text,
      CONCAT(sc.cap_tier_at_trigger::text, ' ', sc.tenure::text, ' ', sc.action::text) AS cell_name,
      sc.instrument_id::text, us.symbol AS ticker,
      sc.action::text AS action, sc.cap_tier_at_trigger::text AS cap_tier, sc.tenure::text AS tenure,
      sc.date::text AS entry_date, NULL::text AS entry_price,
      sc.confidence_unconditional::text, sc.predicted_excess::text,
      sc.exit_date::text, (sc.exit_date IS NULL) AS is_active
    FROM foundation_staging.atlas_signal_calls sc
    LEFT JOIN foundation_staging.instrument_master us ON us.instrument_id = sc.instrument_id
    WHERE sc.cell_id = ${cell_id}::uuid
    ORDER BY sc.date DESC, sc.computed_at DESC
    LIMIT ${limit}
  `
  return rows.map(toEvent)
}
