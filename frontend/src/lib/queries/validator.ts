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

export async function getRecentValidatorRuns(limit = 30): Promise<ValidatorRun[]> {
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

export async function getLatestFrontendFindings(limit = 100): Promise<ValidatorFinding[]> {
  return sql<ValidatorFinding[]>`
    SELECT
      f.id::text           AS id,
      f.run_id::text       AS run_id,
      f.finding_class,
      f.severity,
      f.route,
      f.surface,
      f.identifier,
      f.expected_value,
      f.actual_value,
      f.delta_pct::text    AS delta_pct,
      f.first_seen,
      f.last_seen
    FROM atlas.atlas_validator_findings f
    JOIN atlas.atlas_validator_runs r ON r.id = f.run_id
    WHERE f.finding_class IN ('frontend_diff', 'frontend_extract_error')
      AND r.scope = 'frontend_diff'
      AND r.status = 'success'
    ORDER BY f.severity ASC, f.last_seen DESC
    LIMIT ${limit}
  `
}
