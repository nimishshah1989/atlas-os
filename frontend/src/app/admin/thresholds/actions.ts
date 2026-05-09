'use server'

import { revalidatePath } from 'next/cache'
import sql from '@/lib/db'
import { triggerRecompute as callInternal } from '@/lib/internal-api'
import { getThresholdHistory, getRunStatus } from '@/lib/queries/thresholds'

// Hardcoded identity for v0 — see PRD §Architecture #2.
// Full RBAC is deferred until auth layer is extended beyond the single-password gate.
const FUND_MANAGER = 'fund-manager'

export type UpdateThresholdResult = { ok: true } | { ok: false; error: string }

export async function updateThreshold(
  thresholdKey: string,
  newValue: string, // numeric string from form input
  reason: string,
): Promise<UpdateThresholdResult> {
  if (!reason.trim()) {
    return { ok: false, error: 'Change reason is required' }
  }

  const parsedValue = Number(newValue)
  if (!Number.isFinite(parsedValue)) {
    return { ok: false, error: 'Value must be a number' }
  }

  try {
    // CRITICAL: SET LOCAL is a no-op outside a transaction. Using sql.begin
    // ensures the GUC is set inside the same tx as the UPDATE so the
    // audit trigger can read it via current_setting().
    await sql.begin(async (tx) => {
      await tx`SET LOCAL atlas.change_reason = ${reason}`
      await tx`
        UPDATE atlas.atlas_thresholds
        SET threshold_value   = ${parsedValue},
            last_modified_by  = ${FUND_MANAGER},
            last_modified_at  = NOW()
        WHERE threshold_key = ${thresholdKey}
          AND is_active = TRUE
      `
    })
  } catch (err) {
    // CHECK constraint (chk_threshold_in_range) violation arrives here.
    // postgres.js exposes constraint_name as a typed field on PostgresError —
    // use that instead of fragile string-match on err.message.
    const isPostgresError = (e: unknown): e is { constraint_name?: string; message: string } =>
      e instanceof Error && 'constraint_name' in e

    if (isPostgresError(err) && err.constraint_name === 'chk_threshold_in_range') {
      return { ok: false, error: 'Value is outside the allowed [min, max] range' }
    }
    const msg = err instanceof Error ? err.message : String(err)
    return { ok: false, error: msg }
  }

  revalidatePath('/admin/thresholds')
  return { ok: true }
}

export type TriggerRecomputeResult =
  | { ok: true; compute_run_id: string; milestone: string }
  | { ok: false; error: string; existing_run_id?: string }

export async function triggerRecompute(
  milestone: 'm3' | 'm4' | 'm5' | 'all',
): Promise<TriggerRecomputeResult> {
  const result = await callInternal(milestone)

  if (result.ok) {
    revalidatePath('/admin/thresholds')
    return { ok: true, compute_run_id: result.compute_run_id, milestone: result.milestone }
  }

  return {
    ok: false,
    error: result.message,
    existing_run_id: 'existing_run_id' in result ? result.existing_run_id : undefined,
  }
}

export async function getThresholdHistoryAction(thresholdKey: string) {
  return getThresholdHistory(thresholdKey, 20)
}

export async function getRunStatusAction(runId: string) {
  return getRunStatus(runId)
}
