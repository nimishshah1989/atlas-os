'use server'

import { revalidatePath } from 'next/cache'
import { callInternalApi } from '@/lib/internal-api'
import sql from '@/lib/db'

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i

export type RerunResult =
  | { ok: true; compute_run_id: string }
  | { ok: false; error: string; error_code?: string; existing_run_id?: string }

export type RunStatusResult = {
  status: string
  finished_at: string | null
} | null

export async function rerunBacktest(
  strategyId: string,
  startDate: string,  // YYYY-MM-DD
  endDate: string,    // YYYY-MM-DD
  initialCapital: number,
): Promise<RerunResult> {
  // Server-side validation — client already validated but we validate again.
  if (!UUID_RE.test(strategyId)) {
    return { ok: false, error: 'Invalid strategy ID' }
  }
  if (!startDate || !endDate) {
    return { ok: false, error: 'Start date and end date are required' }
  }
  if (startDate >= endDate) {
    return { ok: false, error: 'End date must be after start date' }
  }
  if (!Number.isFinite(initialCapital) || initialCapital < 100_000) {
    return { ok: false, error: 'Initial capital must be at least ₹1,00,000' }
  }

  type BacktestData = { compute_run_id: string; strategy_id: string; status: string }

  const result = await callInternalApi<BacktestData>(
    `/api/strategies/${strategyId}/backtest`,
    {
      method: 'POST',
      body: {
        start_date: startDate,
        end_date: endDate,
        initial_capital: initialCapital,
      },
    },
  )

  if (result.ok) {
    revalidatePath(`/strategies/${strategyId}`)
    return { ok: true, compute_run_id: result.data.compute_run_id }
  }

  if (result.status === 409) {
    return {
      ok: false,
      error: result.message,
      error_code: 'already_running',
      existing_run_id: (result as { existing_run_id?: string }).existing_run_id,
    }
  }

  return { ok: false, error: result.message, error_code: result.error_code }
}

export async function getBacktestRunStatus(runId: string): Promise<RunStatusResult> {
  if (!UUID_RE.test(runId)) return null

  const rows = await sql<{ status: string; finished_at: Date | null }[]>`
    SELECT status, ended_at AS finished_at
    FROM atlas.atlas_pipeline_runs
    WHERE run_id = ${runId}
    LIMIT 1
  `
  if (!rows[0]) return null
  return {
    status: rows[0].status,
    finished_at: rows[0].finished_at ? rows[0].finished_at.toISOString() : null,
  }
}
