// Phase C validator queries — run history + findings.
import 'server-only'
import sql from '@/lib/db'

export type ValidatorRun = {
  id: string
  started_at: Date
  completed_at: Date | null
  status: string
  scope: string
  n_findings: number | null
}

export type ValidatorFinding = {
  id: string
  run_id: string
  finding_class: string
  severity: string
  route: string | null
  surface: string
  identifier: string
  expected_value: string
  actual_value: string
  delta_pct: string | null
  first_seen: Date
  last_seen: Date
}

// One row per (route, surface, severity) — aggregated count + representative sample.
export type FindingGroup = {
  route: string | null
  surface: string
  severity: string
  count: number
  sample_identifier: string | null
  sample_expected: string | null
  sample_actual: string | null
  last_seen: Date
}

export type RouteSummary = {
  route: string
  p0: number
  p1: number
  p2: number
  total: number
}

export type DayTrend = {
  run_date: string
  p0: number
  p1: number
  p2: number
  total: number
}

export async function getRecentValidatorRuns(limit = 20): Promise<ValidatorRun[]> {
  return sql<ValidatorRun[]>`
    SELECT
      id::text            AS id,
      started_at,
      completed_at,
      status,
      scope,
      n_findings
    FROM atlas.atlas_validator_runs
    ORDER BY started_at DESC
    LIMIT ${limit}
  `
}

// All findings from the single most-recent successful frontend_diff run, grouped by (route, surface, severity).
export async function getLatestFrontendFindingGroups(): Promise<FindingGroup[]> {
  return sql<FindingGroup[]>`
    WITH latest_run AS (
      SELECT id FROM atlas.atlas_validator_runs
      WHERE scope = 'frontend_diff' AND status = 'success'
      ORDER BY started_at DESC
      LIMIT 1
    )
    SELECT
      f.route,
      f.surface,
      f.severity,
      COUNT(*)                                      AS count,
      MIN(f.identifier)                             AS sample_identifier,
      MIN(f.expected_value)                         AS sample_expected,
      MIN(f.actual_value)                           AS sample_actual,
      MAX(f.last_seen)                              AS last_seen
    FROM atlas.atlas_validator_findings f
    JOIN latest_run lr ON lr.id = f.run_id
    WHERE f.finding_class IN ('frontend_diff', 'frontend_extract_error')
    GROUP BY f.route, f.surface, f.severity
    ORDER BY
      CASE f.severity WHEN 'P0' THEN 0 WHEN 'P1' THEN 1 WHEN 'P2' THEN 2 ELSE 3 END,
      f.route
  `
}

// Per-route P0/P1/P2 breakdown for the latest successful run.
export async function getLatestRouteSummary(): Promise<RouteSummary[]> {
  return sql<RouteSummary[]>`
    WITH latest_run AS (
      SELECT id FROM atlas.atlas_validator_runs
      WHERE scope = 'frontend_diff' AND status = 'success'
      ORDER BY started_at DESC
      LIMIT 1
    )
    SELECT
      COALESCE(f.route, '(unknown)')                AS route,
      COUNT(*) FILTER (WHERE f.severity = 'P0')     AS p0,
      COUNT(*) FILTER (WHERE f.severity = 'P1')     AS p1,
      COUNT(*) FILTER (WHERE f.severity = 'P2')     AS p2,
      COUNT(*)                                      AS total
    FROM atlas.atlas_validator_findings f
    JOIN latest_run lr ON lr.id = f.run_id
    WHERE f.finding_class IN ('frontend_diff', 'frontend_extract_error')
    GROUP BY f.route
    ORDER BY p0 DESC, p1 DESC, f.route
  `
}

// 7-day trend: P0/P1/P2 counts per day for frontend_diff runs.
export async function getValidatorTrend(days = 7): Promise<DayTrend[]> {
  return sql<DayTrend[]>`
    SELECT
      started_at::date::text                            AS run_date,
      COALESCE(SUM(p0_count), 0)                        AS p0,
      COALESCE(SUM(p1_count), 0)                        AS p1,
      COALESCE(SUM(p2_count), 0)                        AS p2,
      COALESCE(SUM(p0_count + p1_count + p2_count), 0)  AS total
    FROM (
      SELECT
        r.started_at,
        COUNT(*) FILTER (WHERE f.severity = 'P0') AS p0_count,
        COUNT(*) FILTER (WHERE f.severity = 'P1') AS p1_count,
        COUNT(*) FILTER (WHERE f.severity = 'P2') AS p2_count
      FROM atlas.atlas_validator_runs r
      LEFT JOIN atlas.atlas_validator_findings f
        ON f.run_id = r.id
        AND f.finding_class IN ('frontend_diff', 'frontend_extract_error')
      WHERE r.scope = 'frontend_diff'
        AND r.started_at >= NOW() - INTERVAL '1 day' * ${days}
      GROUP BY r.id, r.started_at
    ) sub
    GROUP BY started_at::date
    ORDER BY run_date DESC
  `
}
