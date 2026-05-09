// src/lib/queries/thresholds.ts
import 'server-only'
import sql from '@/lib/db'

// postgres returns NUMERIC as string — keep as string, parse at display time

export type ThresholdRow = {
  threshold_key: string
  threshold_value: string // NUMERIC -> text
  category: string
  description: string
  methodology_section: string | null
  units: string | null
  min_allowed: string
  max_allowed: string
  default_value: string
  last_modified_by: string
  last_modified_at: Date
}

export type ThresholdHistoryRow = {
  id: number
  threshold_key: string
  old_value: string | null
  new_value: string
  changed_by: string
  changed_at: Date
  change_reason: string | null
  triggered_reclassify: boolean
  reclassify_run_id: string | null
}

export type RecentRunRow = {
  run_id: string
  script_name: string
  milestone: string | null
  status: string // 'running' | 'success' | 'failed'
  started_at: Date
  ended_at: Date | null
  rows_written: number | null
  error_message: string | null
}

export async function getAllThresholds(): Promise<ThresholdRow[]> {
  return sql<ThresholdRow[]>`
    SELECT
      threshold_key,
      threshold_value::text   AS threshold_value,
      category,
      description,
      methodology_section,
      units,
      min_allowed::text       AS min_allowed,
      max_allowed::text       AS max_allowed,
      default_value::text     AS default_value,
      last_modified_by,
      last_modified_at
    FROM atlas.atlas_thresholds
    WHERE is_active = TRUE
    ORDER BY category, threshold_key
  `
}

export async function getThresholdHistory(
  thresholdKey: string,
  limit: number = 20,
): Promise<ThresholdHistoryRow[]> {
  return sql<ThresholdHistoryRow[]>`
    SELECT
      id,
      threshold_key,
      old_value::text         AS old_value,
      new_value::text         AS new_value,
      changed_by,
      changed_at,
      change_reason,
      triggered_reclassify,
      reclassify_run_id
    FROM atlas.atlas_threshold_history
    WHERE threshold_key = ${thresholdKey}
    ORDER BY changed_at DESC
    LIMIT ${limit}
  `
}

export async function getRunStatus(runId: string): Promise<RecentRunRow | null> {
  const rows = await sql<RecentRunRow[]>`
    SELECT
      run_id,
      script_name,
      milestone,
      status,
      started_at,
      ended_at,
      rows_written,
      error_message
    FROM atlas.atlas_pipeline_runs
    WHERE run_id = ${runId}
    LIMIT 1
  `
  return rows[0] ?? null
}

export async function getRecentRuns(limit: number = 5): Promise<RecentRunRow[]> {
  return sql<RecentRunRow[]>`
    SELECT
      run_id,
      script_name,
      milestone,
      status,
      started_at,
      ended_at,
      rows_written,
      error_message
    FROM atlas.atlas_pipeline_runs
    ORDER BY started_at DESC
    LIMIT ${limit}
  `
}
