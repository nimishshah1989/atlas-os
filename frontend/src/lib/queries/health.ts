// src/lib/queries/health.ts — M12 backend health observability queries.
// Reads from atlas.atlas_pipeline_runs, atlas_validator_results, atlas_health_daily.

import 'server-only'
import sql from '@/lib/db'

// ---------------------------------------------------------------------------
// Pipeline runs (last N for the dashboard "recent runs" table)
// ---------------------------------------------------------------------------

export type PipelineRun = {
  run_id: string
  script_name: string
  milestone: string | null
  phase: string | null
  started_at: Date
  ended_at: Date | null
  status: 'running' | 'success' | 'failed'
  rows_written: number | null
  error_message: string | null
  host: string | null
  duration_seconds: number | null
}

export async function getRecentRuns(limit = 30): Promise<PipelineRun[]> {
  const rows = await sql<PipelineRun[]>`
    SELECT
      run_id::text       AS run_id,
      script_name,
      milestone,
      phase,
      started_at,
      ended_at,
      status,
      rows_written,
      error_message,
      host,
      EXTRACT(EPOCH FROM (ended_at - started_at))::int AS duration_seconds
    FROM atlas.atlas_pipeline_runs
    ORDER BY started_at DESC
    LIMIT ${limit}
  `
  return rows
}

// Latest run per distinct script — deduplicated summary view for the dashboard.
export async function getLatestRunPerScript(): Promise<PipelineRun[]> {
  const rows = await sql<PipelineRun[]>`
    SELECT DISTINCT ON (script_name)
      run_id::text       AS run_id,
      script_name,
      milestone,
      phase,
      started_at,
      ended_at,
      status,
      rows_written,
      error_message,
      host,
      EXTRACT(EPOCH FROM (ended_at - started_at))::int AS duration_seconds
    FROM atlas.atlas_pipeline_runs
    ORDER BY script_name, started_at DESC
  `
  return rows
}

// ---------------------------------------------------------------------------
// Freshness — current row counts + latest dates per table
// ---------------------------------------------------------------------------

export type TableFreshness = {
  table_name: string
  row_count: number
  latest_date: Date | null
  lag_days: number | null
}

const TRACKED_TABLES: { name: string; date_col: string | null }[] = [
  { name: 'atlas_index_metrics_daily',   date_col: 'date' },
  { name: 'atlas_sector_metrics_daily',  date_col: 'date' },
  { name: 'atlas_sector_states_daily',   date_col: 'date' },
  { name: 'atlas_market_regime_daily',   date_col: 'date' },
  { name: 'atlas_stock_metrics_daily',   date_col: 'date' },
  { name: 'atlas_stock_states_daily',    date_col: 'date' },
  { name: 'atlas_etf_metrics_daily',     date_col: 'date' },
  { name: 'atlas_etf_states_daily',      date_col: 'date' },
  { name: 'atlas_fund_metrics_daily',    date_col: 'nav_date' },
  { name: 'atlas_fund_lens_monthly',     date_col: 'as_of_date' },
  { name: 'atlas_fund_states_daily',     date_col: 'date' },
  { name: 'atlas_stock_decisions_daily', date_col: 'date' },
  { name: 'atlas_etf_decisions_daily',   date_col: 'date' },
  { name: 'atlas_fund_decisions_daily',  date_col: 'date' },
]

export async function getFreshness(): Promise<TableFreshness[]> {
  const today = new Date()
  today.setHours(0, 0, 0, 0)

  return Promise.all(
    TRACKED_TABLES.map(async ({ name, date_col }) => {
      if (date_col) {
        // Use pg_stat_user_tables for fast row-count estimate; MAX() is index-backed.
        const rows = await sql<{ row_count: string; latest_date: Date | null }[]>`
          SELECT
            (SELECT reltuples::bigint FROM pg_class
              JOIN pg_namespace ON pg_namespace.oid = pg_class.relnamespace
              WHERE nspname = 'atlas' AND relname = ${name})::text AS row_count,
            MAX(${sql(date_col)}) AS latest_date
          FROM atlas.${sql(name)}
        `
        const r = rows[0]
        const latest = r?.latest_date ? new Date(r.latest_date) : null
        const lag = latest
          ? Math.floor((today.getTime() - latest.getTime()) / (1000 * 60 * 60 * 24))
          : null
        return {
          table_name: name,
          row_count: Number(r?.row_count ?? 0),
          latest_date: latest,
          lag_days: lag,
        }
      } else {
        const rows = await sql<{ row_count: string }[]>`
          SELECT reltuples::bigint::text AS row_count
          FROM pg_class
          JOIN pg_namespace ON pg_namespace.oid = pg_class.relnamespace
          WHERE nspname = 'atlas' AND relname = ${name}
        `
        return {
          table_name: name,
          row_count: Number(rows[0]?.row_count ?? 0),
          latest_date: null,
          lag_days: null,
        }
      }
    }),
  )
}

export function lagThresholdDays(table: string): number {
  return table === 'atlas_fund_lens_monthly' ? 35 : 2
}

// ---------------------------------------------------------------------------
// JIP source sync freshness — public.de_* tables
// ---------------------------------------------------------------------------

const JIP_TABLES: { name: string; date_col: string }[] = [
  { name: 'de_source_files', date_col: 'created_at' },
  { name: 'de_equity_ohlcv', date_col: 'date' },
  { name: 'de_index_prices', date_col: 'date' },
  { name: 'de_mf_nav_daily', date_col: 'nav_date' },
  { name: 'de_etf_ohlcv',    date_col: 'date' },
  { name: 'de_cron_run',     date_col: 'started_at' },
]

export async function getJipFreshness(): Promise<TableFreshness[]> {
  const today = new Date()
  today.setHours(0, 0, 0, 0)

  return Promise.all(
    JIP_TABLES.map(async ({ name, date_col }) => {
      // Use pg_stat_user_tables estimate for row count; MAX() is index-backed.
      const rows = await sql<{ row_count: string; latest_date: Date | null }[]>`
        SELECT
          (SELECT reltuples::bigint FROM pg_class
            JOIN pg_namespace ON pg_namespace.oid = pg_class.relnamespace
            WHERE nspname = 'public' AND relname = ${name})::text AS row_count,
          MAX(${sql(date_col)}) AS latest_date
        FROM public.${sql(name)}
      `
      const r = rows[0]
      const latest = r?.latest_date ? new Date(r.latest_date) : null
      const lag = latest
        ? Math.floor((today.getTime() - latest.getTime()) / (1000 * 60 * 60 * 24))
        : null
      return {
        table_name: name,
        row_count: Number(r?.row_count ?? 0),
        latest_date: latest,
        lag_days: lag,
      }
    }),
  )
}

export function jipLagThresholdDays(_table: string): number {
  return 2
}

// ---------------------------------------------------------------------------
// Anomalies (today's flagged metrics)
// ---------------------------------------------------------------------------

export type AnomalyRow = {
  data_date: Date
  table_name: string
  metric_name: string
  value_today: number | null
  value_prior_day: number | null
  rolling_14d_avg: number | null
  rolling_14d_std: number | null
  pct_change_dod: number | null
  z_score: number | null
  is_anomaly: boolean
  severity: 'info' | 'warn' | 'critical' | null
  notes: string | null
}

export async function getLatestAnomalies(): Promise<AnomalyRow[]> {
  // Most-recent data_date that has any rows.
  const dateRows = await sql<{ d: Date | null }[]>`
    SELECT MAX(data_date) AS d FROM atlas.atlas_health_daily
  `
  const d = dateRows[0]?.d
  if (!d) return []

  const rows = await sql<AnomalyRow[]>`
    SELECT
      data_date,
      table_name,
      metric_name,
      value_today::float8       AS value_today,
      value_prior_day::float8   AS value_prior_day,
      rolling_14d_avg::float8   AS rolling_14d_avg,
      rolling_14d_std::float8   AS rolling_14d_std,
      pct_change_dod::float8    AS pct_change_dod,
      z_score::float8           AS z_score,
      is_anomaly,
      severity,
      notes
    FROM atlas.atlas_health_daily
    WHERE data_date = ${d}
      AND is_anomaly = TRUE
    ORDER BY
      CASE severity
        WHEN 'critical' THEN 0
        WHEN 'warn'     THEN 1
        WHEN 'info'     THEN 2
        ELSE 3
      END,
      table_name, metric_name
  `
  return rows
}

export async function getLatestHealthDate(): Promise<Date | null> {
  const r = await sql<{ d: Date | null }[]>`
    SELECT MAX(data_date) AS d FROM atlas.atlas_health_daily
  `
  return r[0]?.d ?? null
}

// ---------------------------------------------------------------------------
// Validator scorecard
// ---------------------------------------------------------------------------

export type ValidatorRun = {
  run_id: string
  validator: 'M3' | 'M4' | 'M5'
  ran_at: Date
  total_checks: number
  failures: number
  status: 'PASS' | 'FAIL'
}

export async function getValidatorHistory(days = 30): Promise<ValidatorRun[]> {
  const rows = await sql<ValidatorRun[]>`
    SELECT
      run_id::text AS run_id,
      validator,
      ran_at,
      total_checks,
      failures,
      status
    FROM atlas.atlas_validator_results
    WHERE ran_at >= NOW() - (${days}::int * INTERVAL '1 day')
    ORDER BY validator, ran_at DESC
  `
  return rows
}

// Latest result per validator — used for the summary scorecard cards.
export async function getValidatorLatest(): Promise<ValidatorRun[]> {
  const rows = await sql<ValidatorRun[]>`
    SELECT DISTINCT ON (validator)
      run_id::text AS run_id,
      validator,
      ran_at,
      total_checks,
      failures,
      status
    FROM atlas.atlas_validator_results
    ORDER BY validator, ran_at DESC
  `
  return rows
}

// ---------------------------------------------------------------------------
// Aggregated header status
// ---------------------------------------------------------------------------

export type HealthHeaderStatus = {
  level: 'green' | 'yellow' | 'red'
  message: string
  last_health_check: Date | null
}

export async function getHeaderStatus(): Promise<HealthHeaderStatus> {
  const [hcRows, anomRows, valRows] = await Promise.all([
    sql<{ ts: Date | null }[]>`
      SELECT MAX(computed_at) AS ts FROM atlas.atlas_health_daily
    `,
    sql<{ severity: string; n: string }[]>`
      SELECT severity, COUNT(*)::text AS n
      FROM atlas.atlas_health_daily
      WHERE data_date = (SELECT MAX(data_date) FROM atlas.atlas_health_daily)
        AND is_anomaly = TRUE
      GROUP BY severity
    `,
    // Latest result per validator — prevents old test runs from inflating FAIL count.
    sql<{ validator: string; status: string }[]>`
      SELECT DISTINCT ON (validator) validator, status
      FROM atlas.atlas_validator_results
      ORDER BY validator, ran_at DESC
    `,
  ])

  const last = hcRows[0]?.ts ?? null
  const sev: Record<string, number> = {}
  for (const r of anomRows) sev[r.severity] = Number(r.n)
  const validatorFailures = valRows.filter((r) => r.status === 'FAIL').length

  if ((sev.critical ?? 0) > 0 || validatorFailures > 0) {
    return {
      level: 'red',
      message: `${sev.critical ?? 0} critical anomalies · ${validatorFailures} validator FAILs`,
      last_health_check: last,
    }
  }
  if ((sev.warn ?? 0) > 0) {
    return {
      level: 'yellow',
      message: `${sev.warn} warnings`,
      last_health_check: last,
    }
  }
  return {
    level: 'green',
    message: 'System healthy',
    last_health_check: last,
  }
}
