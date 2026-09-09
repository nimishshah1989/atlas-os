// src/lib/queries/health.ts — the operator surface. Reads ONLY atlas_global (rule #1; the schema
// gate scans this directory): atlas_pipeline_runs, atlas_validator_results, atlas_health_daily.
// Shapes follow India's frontend/src/lib/queries/health.ts so the panels port 1:1.
import 'server-only'
import type { TransactionSql } from 'postgres'
import { db, dbAvailable } from '@/lib/db'

// EVERY READ ON THIS PAGE HAS A SERVER-SIDE BUDGET. On 2026-09-08 two of these — the two that
// touch atlas_health_daily — stopped returning, on a six-row table, while count(*) on the same
// table answered in 0.0s. The page's client-side budget (src/lib/result.ts) makes that a named
// error instead of a hang, but it cancels nothing: the statement keeps running in Postgres and
// holds its pooler connection until it returns — which, if it is waiting on a lock, is never.
// With max 5 connections per process, a handful of stalled /health renders would exhaust the
// pool and every page that queries would hang — the pages readers actually use. So the budget
// is applied where the cancel is real: `SET LOCAL statement_timeout` inside one transaction.
// Postgres cancels the statement at the limit, the error names itself ("canceling statement
// due to statement timeout"), and the connection is released.
//
// This is the transaction-mode pooler's ONE supported use of SET LOCAL — scoped to a single
// sql.begin(), which pins a connection for exactly that transaction. It is the same pattern
// scripts/foundation/_db.py::_apply_timeout uses ("pooler-proof"). db.ts's rule that nothing
// may rely on SET LOCAL is about session state across statements; this is not that.
//
// 5s, not 10s: statement_timeout is PER STATEMENT, and getLatestAnomalies runs two in one
// transaction, so a transaction can hold its pooler connection for up to twice the budget.
// The page gives up at 12s (health/page.tsx QUERY_BUDGET_MS); the connection must be released
// before that, not after, or a stalled render leaves a connection pinned past the page that
// asked for it. Every read here is on a table of hundreds of rows and answers in well under
// a second when the database is healthy — 5s is headroom, not a ceiling anyone should meet.
const STATEMENT_BUDGET = '5s'

/** Run `fn` in one transaction whose statements are cancelled server-side after the budget. */
async function bounded<T>(fn: (tx: TransactionSql) => Promise<T>): Promise<T> {
  const result = await db().begin(async (tx) => {
    await tx.unsafe(`SET LOCAL statement_timeout = '${STATEMENT_BUDGET}'`)
    return fn(tx)
  })
  return result as T
}

// ── pipeline runs ───────────────────────────────────────────────────────────

export type PipelineRun = {
  run_id: string
  script_name: string
  milestone: string | null
  started_at: Date
  ended_at: Date | null
  status: 'queued' | 'running' | 'success' | 'failed'
  rows_written: number | null
  error_message: string | null
  host: string | null
  git_sha: string | null
  duration_seconds: number | null
}

const RUN_COLUMNS = `
  run_id::text                                        AS run_id,
  script_name, milestone, started_at, ended_at, status,
  rows_written::float8                                AS rows_written,
  error_message, host, git_sha,
  EXTRACT(EPOCH FROM (ended_at - started_at))::int    AS duration_seconds`

/** The last N runs, newest first. */
export async function getPipelineRuns(limit = 30): Promise<PipelineRun[]> {
  if (!dbAvailable) return []
  return bounded((tx) => tx<PipelineRun[]>`
    SELECT ${tx.unsafe(RUN_COLUMNS)}
    FROM atlas_global.atlas_pipeline_runs
    ORDER BY started_at DESC
    LIMIT ${limit}
  `)
}

/** One row per script — its most recent run. */
export async function getLatestRunPerScript(): Promise<PipelineRun[]> {
  if (!dbAvailable) return []
  return bounded((tx) => tx<PipelineRun[]>`
    SELECT DISTINCT ON (script_name) ${tx.unsafe(RUN_COLUMNS)}
    FROM atlas_global.atlas_pipeline_runs
    ORDER BY script_name, started_at DESC
  `)
}

// ── freshness: the "as of" stamp on every surface ──────────────────────────

// A run that finished within one US session plus the overnight window is current; anything
// older is shown amber and said to be stale in words. An ops display threshold, not methodology.
export const FRESH_WITHIN_HOURS = 30

export type Freshness =
  | { state: 'no-db' }
  | { state: 'none' }
  | { state: 'error'; error: string }
  | { state: 'fresh' | 'stale'; ended_at: Date; script_name: string; age_hours: number }

/** The latest successful pipeline step, and whether it is recent enough to trust. */
export async function getFreshness(): Promise<Freshness> {
  if (!dbAvailable) return { state: 'no-db' }
  const rows = await bounded((tx) => tx<{ script_name: string; ended_at: Date }[]>`
    SELECT script_name, ended_at
    FROM atlas_global.atlas_pipeline_runs
    WHERE status = 'success' AND ended_at IS NOT NULL
    ORDER BY ended_at DESC
    LIMIT 1
  `)
  const r = rows[0]
  if (!r) return { state: 'none' }
  const ended_at = new Date(r.ended_at)
  const age_hours = (Date.now() - ended_at.getTime()) / 3_600_000
  return {
    state: age_hours <= FRESH_WITHIN_HOURS ? 'fresh' : 'stale',
    ended_at,
    script_name: r.script_name,
    age_hours,
  }
}

// ── validators ─────────────────────────────────────────────────────────────

export type ValidatorRun = {
  run_id: string
  validator: string
  ran_at: Date
  total_checks: number
  failures: number
  status: 'PASS' | 'FAIL'
}

/** The latest result per validator. */
export async function getValidatorLatest(): Promise<ValidatorRun[]> {
  if (!dbAvailable) return []
  return bounded((tx) => tx<ValidatorRun[]>`
    SELECT DISTINCT ON (validator)
      run_id::text AS run_id, validator, ran_at, total_checks, failures, status
    FROM atlas_global.atlas_validator_results
    ORDER BY validator, ran_at DESC
  `)
}

/** Every result inside the window, for pass rates. */
export async function getValidatorHistory(days = 30): Promise<ValidatorRun[]> {
  if (!dbAvailable) return []
  return bounded((tx) => tx<ValidatorRun[]>`
    SELECT run_id::text AS run_id, validator, ran_at, total_checks, failures, status
    FROM atlas_global.atlas_validator_results
    WHERE ran_at >= NOW() - (${days}::int * INTERVAL '1 day')
    ORDER BY validator, ran_at DESC
  `)
}

// ── anomalies (the health snapshot's flagged metrics) ──────────────────────

export type AnomalyRow = {
  data_date: string
  table_name: string
  metric_name: string
  value_today: number | null
  value_prior_day: number | null
  pct_change_dod: number | null
  z_score: number | null
  severity: 'info' | 'warn' | 'critical' | null
  notes: string | null
}

export type AnomalySnapshot = { data_date: string | null; rows: AnomalyRow[] }

/** Flagged metrics on the most recent snapshot date (data_date selected as text: no zone shift). */
export async function getLatestAnomalies(): Promise<AnomalySnapshot> {
  if (!dbAvailable) return { data_date: null, rows: [] }
  return bounded(async (tx) => {
    const latest = await tx<{ d: string | null }[]>`
      SELECT MAX(data_date)::text AS d FROM atlas_global.atlas_health_daily
    `
    const d = latest[0]?.d ?? null
    if (!d) return { data_date: null, rows: [] }
    const rows = await tx<AnomalyRow[]>`
      SELECT
        data_date::text          AS data_date,
        table_name, metric_name,
        value_today::float8      AS value_today,
        value_prior_day::float8  AS value_prior_day,
        pct_change_dod::float8   AS pct_change_dod,
        z_score::float8          AS z_score,
        severity, notes
      FROM atlas_global.atlas_health_daily
      WHERE data_date = ${d}::date AND is_anomaly = TRUE
      ORDER BY
        CASE severity WHEN 'critical' THEN 0 WHEN 'warn' THEN 1 WHEN 'info' THEN 2 ELSE 3 END,
        table_name, metric_name
    `
    return { data_date: d, rows }
  })
}

// ── freshness rows (the snapshot's lag per tracked table, in SPY sessions) ─

// The metric write_health_snapshot writes once per tracked table: lag in SPY sessions (null with a
// "no SPY bar" note while ohlcv_daily has no anchor bar, or "EMPTY") and the guard's tolerance.
export const FRESHNESS_METRIC = 'freshness_lag_sessions'

export type FreshnessRow = {
  data_date: string
  table_name: string
  value_today: number | null
  is_anomaly: boolean
  severity: 'info' | 'warn' | 'critical' | null
  notes: string | null
  computed_at: Date
}

export type FreshnessSnapshot = { data_date: string | null; rows: FreshnessRow[] }

/** Every tracked table's lag on the most recent snapshot date that carries the metric. */
export async function getFreshnessRows(): Promise<FreshnessSnapshot> {
  if (!dbAvailable) return { data_date: null, rows: [] }
  const rows = await bounded((tx) => tx<FreshnessRow[]>`
    SELECT
      data_date::text      AS data_date,
      table_name,
      value_today::float8  AS value_today,
      is_anomaly, severity, notes, computed_at
    FROM atlas_global.atlas_health_daily
    WHERE metric_name = ${FRESHNESS_METRIC}
      AND data_date = (
        SELECT MAX(data_date) FROM atlas_global.atlas_health_daily WHERE metric_name = ${FRESHNESS_METRIC}
      )
    ORDER BY table_name
  `)
  return { data_date: rows[0]?.data_date ?? null, rows }
}

// ── provider calls (the budget the run date spent) ─────────────────────────

export type ProviderCallRow = {
  run_date: string
  provider: string
  endpoint: string
  calls: number
  updated_at: Date
}

export type ProviderCallsSnapshot = { run_date: string | null; rows: ProviderCallRow[] }

/** Calls per (provider, endpoint) on the most recent run date, as the scripts recorded them. */
export async function getProviderCalls(): Promise<ProviderCallsSnapshot> {
  if (!dbAvailable) return { run_date: null, rows: [] }
  const rows = await bounded((tx) => tx<ProviderCallRow[]>`
    SELECT run_date::text AS run_date, provider, endpoint, calls, updated_at
    FROM atlas_global.provider_calls
    WHERE run_date = (SELECT MAX(run_date) FROM atlas_global.provider_calls)
    ORDER BY provider, endpoint
  `)
  return { run_date: rows[0]?.run_date ?? null, rows }
}
