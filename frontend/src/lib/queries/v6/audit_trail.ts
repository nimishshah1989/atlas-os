// allow-large: heavy audit query — 6-section provenance chain, 5 parallel queries
//
// frontend/src/lib/queries/v6/audit_trail.ts
//
// Provenance chain for AuditTrailTab (design-application.md §7.1).
// Sections 1, 2, 3, 4, 5, 7 in v6.0; Section 6 deferred to v6.1.
//
// Sources:
//   Section 1 (universe): atlas_universe_stocks — membership + tier + sector
//   Section 2 (cell_matches): atlas_conviction_daily — per-(iid × tenure) verdict
//   Section 3 (signal_call): atlas_signal_calls — latest ACTIVE call for iid
//   Section 4 (predicates_met): atlas_conviction_daily.fired_predicates JSONB
//                               + atlas_cell_definitions.rule_dsl for translation
//   Section 5 (regime): atlas_regime_daily — state + deployment + days_in_regime
//   Section 7 (provenance): atlas_provenance_log — run_id + source + computed_at
//
// Performance notes (EXPLAIN ANALYZE targets):
//   - Section 1: ix on atlas_universe_stocks.instrument_id → Index Scan
//   - Section 2: idx_conviction_daily_iid_date composite → Index Scan
//   - Section 3: ix_atlas_signal_calls_iid_date + open partial index → Index Scan
//   - Section 5: ix_atlas_regime_daily_date → single row fetch
//   - Section 7: ix_atlas_provenance_log_output_table_ts_desc → Index Scan + LIMIT
//   All five run in parallel via Promise.all — target <250ms p95 on production.

import 'server-only'
import { cache } from 'react'
import sql from '@/lib/db'

// ---------------------------------------------------------------------------
// Public types (contract)
// ---------------------------------------------------------------------------

export type AuditTrail = {
  // Section 1: Universe membership
  universe: {
    iid: string
    in_universe: boolean
    universe_total: number
    cap_tier: 'Small' | 'Mid' | 'Large'
    sector: string
    as_of_date: string
  }
  // Section 2: Cell matches — which cells this iid triggered today
  cell_matches: Array<{
    cell_id: string
    cell_name: string
    action: 'POSITIVE' | 'NEUTRAL' | 'NEGATIVE'
    confidence_unconditional: string
    triggered_at: string
  }>
  // Section 3: Signal call provenance (latest open call)
  signal_call: {
    signal_call_id: string
    cell_id: string
    entry_date: string
    entry_price: string | null
    predicted_excess: string | null
    rule_dsl: Record<string, unknown>
  } | null
  // Section 4: Predicates met (feature values vs rule thresholds)
  predicates_met: Array<{
    predicate_text: string
    actual_value: string
    satisfied: boolean
    translation: string
  }>
  // Section 5: Regime context
  regime: {
    state: string
    deployment_multiplier: string
    cell_active_in_regime: boolean
    days_in_regime: number
  } | null
  // Section 6: Deferred to v6.1 (ensemble cross-rule check)
  cross_rule_check: null
  // Section 7: Provenance log
  provenance: Array<{
    table_name: string
    run_id: string
    computed_at: string
    source: string
  }>
}

// ---------------------------------------------------------------------------
// Internal row types
// ---------------------------------------------------------------------------

type UniverseRow = {
  instrument_id: string
  symbol: string
  sector: string
  tier: string
  in_universe: boolean
  universe_total: string
}

type ConvictionRow = {
  cell_id: string | null
  cell_name: string
  verdict: string
  confidence_unconditional: string | null
  snapshot_date: string
}

type SignalCallRow = {
  signal_call_id: string
  cell_id: string
  entry_date: string
  entry_price: string | null
  predicted_excess: string | null
  rule_dsl: Record<string, unknown>
}

type RegimeRow = {
  state: string
  deployment_multiplier: string | null
  cell_active_in_regime: boolean | null
  days_in_regime: string
}

type ProvenanceRow = {
  run_id: string
  output_table: string
  actor: string
  ts: string
}

// ---------------------------------------------------------------------------
// Feature-name translation lookup (deterministic, no runtime I/O)
// Covers the 12-feature methodology vocabulary from CONTEXT.md + common extras.
// ---------------------------------------------------------------------------

const FEATURE_TRANSLATIONS: Record<string, string> = {
  log_med_tv_60d:       'Daily turnover is well above the mega-liquid floor.',
  rs_residual_6m:       'Relative strength residual over 6 months is positive — stock beats cohort trend.',
  rs_residual_12m:      'Stock is in the top tier of 12-month relative strength vs Nifty 500.',
  volume_zscore_252d:   'Recent volume is above its 12-month average — institutional accumulation signal.',
  realized_vol_60d:     '60-day realized volatility is within the acceptable range for this tier.',
  formation_max_dd:     'Maximum drawdown during the formation window is within threshold.',
  log_price:            'Log price satisfies the minimum price floor for this universe tier.',
  listing_age_days:     'Instrument has sufficient listing history for the rule to be reliable.',
  dist_sma200:          'Price is positioned above the 200-day moving average — trend intact.',
  dist_sma50:           'Price is positioned above the 50-day moving average — intermediate trend intact.',
  ema_ratio_20_50:      '20-day EMA is above the 50-day EMA — short-term momentum is positive.',
  ema_distance_200:     'Distance from 200-day EMA is within the expansion zone.',
  rsi_14:               'RSI-14 is in the acceptable range — not overbought or oversold.',
  beta_60d:             'Beta to Nifty 500 over 60 days is within the cell threshold.',
  atr_pct_20d:          'Average True Range (20d) is within the volatility budget for this rule.',
  breadth_pct_above_200: 'Sector breadth above 200-day SMA supports the signal direction.',
}

function translateFeatureName(feature: string): string {
  return FEATURE_TRANSLATIONS[feature] ?? `Feature "${feature}" meets the rule threshold.`
}

// ---------------------------------------------------------------------------
// Predicate parser — reads fired_predicates JSONB entries
// Shape: [{feature, op, threshold, value, satisfied}] (conviction_tape writer)
// Falls back gracefully when shape varies.
// ---------------------------------------------------------------------------

type FiredPredicate = {
  feature?: string
  op?: string
  threshold?: number | string | null
  value?: number | string | null
  satisfied?: boolean
}

function parseFiredPredicates(raw: unknown): AuditTrail['predicates_met'] {
  if (!Array.isArray(raw)) return []

  return raw.map((p: FiredPredicate) => {
    const feature = p.feature ?? 'unknown'
    const op = p.op ?? '>='
    const threshold = p.threshold != null ? String(p.threshold) : '—'
    const value = p.value != null ? String(p.value) : '—'
    const satisfied = p.satisfied ?? false

    const predicate_text = `${feature} ${op} ${threshold}`
    const actual_value = value
    const translation = translateFeatureName(feature)

    return { predicate_text, actual_value, satisfied, translation }
  })
}

// ---------------------------------------------------------------------------
// Resolve as_of date: use provided date or fall back to latest snapshot date
// ---------------------------------------------------------------------------

async function resolveAsOf(as_of?: string): Promise<string> {
  if (as_of) return as_of

  const rows = await sql<Array<{ as_of: string }>>`
    SELECT MAX(snapshot_date)::text AS as_of
    FROM atlas.atlas_conviction_daily
  `
  return rows[0]?.as_of ?? new Date().toISOString().slice(0, 10)
}

// ---------------------------------------------------------------------------
// Section 1 — Universe membership
// Uses: atlas_universe_stocks (indexed on instrument_id, effective_to)
// ---------------------------------------------------------------------------

async function fetchUniverse(
  iid: string,
  asOf: string,
): Promise<AuditTrail['universe']> {
  // Single query: LEFT JOIN universe table so we always get the universe total
  // even when the iid is absent.
  // EXPLAIN ANALYZE: Index Scan on atlas_universe_stocks.instrument_id (ix_universe_stocks_active)
  // universe_total uses a scalar sub-select (no Seq Scan — small table, cached).
  const rows = await sql<UniverseRow[]>`
    SELECT
      COALESCE(us.instrument_id::text, ${iid}) AS instrument_id,
      COALESCE(us.sector, 'Unknown')           AS sector,
      COALESCE(us.tier, 'Large')               AS tier,
      (us.instrument_id IS NOT NULL)           AS in_universe,
      (SELECT COUNT(*)::text
         FROM atlas.atlas_universe_stocks
        WHERE effective_to IS NULL)            AS universe_total
    FROM (SELECT 1) dummy
    LEFT JOIN atlas.atlas_universe_stocks us
      ON us.instrument_id = ${iid}::uuid
        AND us.effective_to IS NULL
    LIMIT 1
  `

  const r = rows[0]
  const inUniverse = r?.in_universe ?? false
  const tier = r?.tier === 'Small' || r?.tier === 'Mid' || r?.tier === 'Large' ? r.tier : 'Large'

  return {
    iid,
    in_universe: inUniverse,
    universe_total: Number(r?.universe_total ?? 0),
    cap_tier: tier as 'Small' | 'Mid' | 'Large',
    sector: r?.sector ?? 'Unknown',
    as_of_date: asOf,
  }
}

// ---------------------------------------------------------------------------
// Section 2 — Cell matches (conviction_daily for this iid + date)
// Uses: idx_conviction_daily_iid_date composite index
// ---------------------------------------------------------------------------

async function fetchCellMatches(
  iid: string,
  asOf: string,
): Promise<AuditTrail['cell_matches']> {
  // EXPLAIN ANALYZE: Bitmap Index Scan on idx_conviction_daily_iid_date
  const rows = await sql<ConvictionRow[]>`
    SELECT
      conv.cell_definition_id::text            AS cell_id,
      CONCAT(
        COALESCE(cd.cap_tier::text, '?'), ' ',
        COALESCE(cd.tenure::text, '?'), ' ',
        conv.verdict
      )                                        AS cell_name,
      conv.verdict                             AS verdict,
      COALESCE(cd.confidence_unconditional::text, '0')
                                               AS confidence_unconditional,
      conv.snapshot_date::text                 AS snapshot_date
    FROM atlas.atlas_conviction_daily conv
    LEFT JOIN atlas.atlas_cell_definitions cd
      ON cd.cell_id = conv.cell_definition_id
    WHERE conv.instrument_id = ${iid}::uuid
      AND conv.snapshot_date = ${asOf}::date
      AND conv.verdict IN ('POSITIVE', 'NEGATIVE')
    ORDER BY conv.tenure, conv.verdict
  `

  return rows.map((r) => ({
    cell_id: r.cell_id ?? '',
    cell_name: r.cell_name,
    action: r.verdict as 'POSITIVE' | 'NEUTRAL' | 'NEGATIVE',
    confidence_unconditional: r.confidence_unconditional ?? '0',
    triggered_at: r.snapshot_date,
  }))
}

// ---------------------------------------------------------------------------
// Section 3 — Signal call provenance (latest open call for this iid)
// Uses: ix_atlas_signal_calls_iid_date + ix_atlas_signal_calls_open
// ---------------------------------------------------------------------------

async function fetchSignalCall(
  iid: string,
  asOf: string,
): Promise<AuditTrail['signal_call']> {
  // EXPLAIN ANALYZE: Index Scan on ix_atlas_signal_calls_open (partial WHERE exit_date IS NULL)
  const rows = await sql<SignalCallRow[]>`
    SELECT
      sc.signal_call_id::text,
      sc.cell_id::text,
      sc.date::text            AS entry_date,
      NULL::text               AS entry_price,
      sc.predicted_excess::text,
      cd.rule_dsl
    FROM atlas.atlas_signal_calls sc
    LEFT JOIN atlas.atlas_cell_definitions cd
      ON cd.cell_id = sc.cell_id
    WHERE sc.instrument_id = ${iid}::uuid
      AND sc.exit_date IS NULL
      AND sc.date <= ${asOf}::date
    ORDER BY sc.date DESC, sc.computed_at DESC
    LIMIT 1
  `

  if (rows.length === 0) return null

  const r = rows[0]
  return {
    signal_call_id: r.signal_call_id,
    cell_id: r.cell_id,
    entry_date: r.entry_date,
    entry_price: r.entry_price,
    predicted_excess: r.predicted_excess,
    rule_dsl: r.rule_dsl ?? {},
  }
}

// ---------------------------------------------------------------------------
// Section 4 — Predicates met
// Derived from atlas_conviction_daily.fired_predicates JSONB (latest row)
// Uses: idx_conviction_daily_iid_date
// ---------------------------------------------------------------------------

async function fetchPredicatesMet(
  iid: string,
  asOf: string,
): Promise<AuditTrail['predicates_met']> {
  const rows = await sql<Array<{ fired_predicates: unknown }>>`
    SELECT conv.fired_predicates
    FROM atlas.atlas_conviction_daily conv
    WHERE conv.instrument_id = ${iid}::uuid
      AND conv.snapshot_date = ${asOf}::date
      AND conv.fired_predicates IS NOT NULL
    ORDER BY conv.tenure
    LIMIT 1
  `

  if (rows.length === 0) return []
  return parseFiredPredicates(rows[0].fired_predicates)
}

// ---------------------------------------------------------------------------
// Section 5 — Regime context
// Uses: ix_atlas_regime_daily_date (single row fetch + window for days_in_regime)
// cell_active_in_regime from atlas_signal_calls (latest open call)
// ---------------------------------------------------------------------------

async function fetchRegime(
  iid: string,
  asOf: string,
): Promise<AuditTrail['regime']> {
  // EXPLAIN ANALYZE: Index Scan on ix_atlas_regime_daily_date (ORDER BY date DESC LIMIT 1)
  // Days-in-regime: count consecutive trailing rows with the same state.
  // Simple approach: fetch last 365 rows and count from the end — avoids
  // correlated sub-selects that could force a Seq Scan on small tables.
  const [regimeRows, signalRows] = await Promise.all([
    sql<Array<{ state: string; date: string }>>`
      SELECT state::text, date::text
      FROM atlas.atlas_regime_daily
      WHERE date <= ${asOf}::date
      ORDER BY date DESC
      LIMIT 365
    `,
    sql<Array<{ cell_active_in_regime: boolean }>>`
      SELECT cell_active_in_regime
      FROM atlas.atlas_signal_calls
      WHERE instrument_id = ${iid}::uuid
        AND exit_date IS NULL
        AND date <= ${asOf}::date
      ORDER BY date DESC, computed_at DESC
      LIMIT 1
    `,
  ])

  if (regimeRows.length === 0) return null

  const currentState = regimeRows[0].state
  let daysInRegime = 0
  for (const row of regimeRows) {
    if (row.state !== currentState) break
    daysInRegime++
  }

  const cellActiveInRegime = signalRows[0]?.cell_active_in_regime ?? true

  return {
    state: currentState,
    // deployment_multiplier lives on atlas_market_regime_daily (not atlas_regime_daily)
    // Return '1.0' as default; full multiplier available via getCurrentRegime().
    deployment_multiplier: '1.0',
    cell_active_in_regime: cellActiveInRegime,
    days_in_regime: daysInRegime,
  }
}

// ---------------------------------------------------------------------------
// Section 7 — Provenance log
// atlas_provenance_log is empty at v6.0 launch; query MUST return [] cleanly.
// Uses: ix_atlas_provenance_log_output_table_ts_desc (no Seq Scan per perf gate)
// ---------------------------------------------------------------------------

async function fetchProvenance(asOf: string): Promise<AuditTrail['provenance']> {
  // EXPLAIN ANALYZE: Index Scan on ix_atlas_provenance_log_output_table_ts_desc
  // Empty table → 0 rows, no Seq Scan (index still used per planner)
  const rows = await sql<ProvenanceRow[]>`
    SELECT
      run_id::text,
      output_table            AS output_table,
      actor                   AS actor,
      ts::text                AS ts
    FROM atlas.atlas_provenance_log
    WHERE ts::date >= (${asOf}::date - INTERVAL '1 day')
      AND ts::date <= (${asOf}::date + INTERVAL '1 day')
    ORDER BY ts DESC
    LIMIT 20
  `

  return rows.map((r) => ({
    table_name: r.output_table,
    run_id: r.run_id,
    computed_at: r.ts,
    source: r.actor,
  }))
}

// ---------------------------------------------------------------------------
// Main export — memoized per server request per (iid, as_of)
// ---------------------------------------------------------------------------

export const getAuditTrail: (
  iid: string,
  as_of?: string,
) => Promise<AuditTrail | null> = cache(async (
  iid: string,
  as_of?: string,
): Promise<AuditTrail | null> => {
  if (!iid) return null

  const asOf = await resolveAsOf(as_of)

  // 5 parallel queries — each hits its own index
  const [universe, cell_matches, signal_call, predicates_met, regime, provenance] =
    await Promise.all([
      fetchUniverse(iid, asOf),
      fetchCellMatches(iid, asOf),
      fetchSignalCall(iid, asOf),
      fetchPredicatesMet(iid, asOf),
      fetchRegime(iid, asOf),
      fetchProvenance(asOf),
    ])

  return {
    universe,
    cell_matches,
    signal_call,
    predicates_met,
    regime,
    cross_rule_check: null,
    provenance,
  }
})
