'use server'

import { revalidatePath } from 'next/cache'
import sql from '@/lib/db'
import { triggerRecompute as callInternal } from '@/lib/internal-api'
import { getPolicyHistory } from '@/lib/queries/policies'
import { GATE_CONFIG, MULTIPLIER_CONFIG } from '@/lib/policy-catalogs'

const FUND_MANAGER = 'fund-manager'

export type UpdatePolicyResult = { ok: true } | { ok: false; error: string }

export async function updateGatePolicy(
  policyKey: string,
  allowedStates: string[],
  reason: string,
): Promise<UpdatePolicyResult> {
  if (!reason.trim()) return { ok: false, error: 'Change reason is required' }
  const config = GATE_CONFIG[policyKey]
  if (!config) return { ok: false, error: 'Unknown policy key' }
  // Validate state names
  for (const s of allowedStates) {
    if (!config.catalog.includes(s)) {
      return { ok: false, error: `Unknown state '${s}' for ${policyKey}` }
    }
  }
  try {
    await sql.begin(async (tx) => {
      await tx`SET LOCAL atlas.change_reason = ${reason}`
      await tx`
        UPDATE atlas.atlas_decision_policy
        SET policy_value = ${JSON.stringify(allowedStates)}::jsonb,
            last_modified_by = ${FUND_MANAGER},
            last_modified_at = NOW()
        WHERE policy_key = ${policyKey}
          AND is_active = TRUE
      `
    })
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err)
    return { ok: false, error: msg }
  }
  revalidatePath('/admin/policies')
  return { ok: true }
}

export async function updateMultiplier(
  policyKey: string,
  values: Record<string, number>,
  reason: string,
): Promise<UpdatePolicyResult> {
  if (!reason.trim()) return { ok: false, error: 'Change reason is required' }
  const config = MULTIPLIER_CONFIG[policyKey]
  if (!config) return { ok: false, error: 'Unknown multiplier key' }
  // Validate keys + ranges
  for (const [k, v] of Object.entries(values)) {
    if (!config.catalog.includes(k)) {
      return { ok: false, error: `Unknown state '${k}' for ${policyKey}` }
    }
    if (typeof v !== 'number' || !Number.isFinite(v)) {
      return { ok: false, error: `Invalid value for '${k}'` }
    }
    if (v < config.min || v > config.max) {
      return { ok: false, error: `Value for '${k}' out of range [${config.min}, ${config.max}]` }
    }
  }
  try {
    await sql.begin(async (tx) => {
      await tx`SET LOCAL atlas.change_reason = ${reason}`
      await tx`
        UPDATE atlas.atlas_decision_policy
        SET policy_value = ${JSON.stringify(values)}::jsonb,
            last_modified_by = ${FUND_MANAGER},
            last_modified_at = NOW()
        WHERE policy_key = ${policyKey}
          AND is_active = TRUE
      `
    })
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err)
    return { ok: false, error: msg }
  }
  revalidatePath('/admin/policies')
  return { ok: true }
}

export async function getPolicyHistoryAction(policyKey: string) {
  return getPolicyHistory(policyKey, 20)
}

// Re-export M13's recompute trigger so RecomputePanel works on the policies page
export { triggerRecompute, getRunStatusAction } from '../thresholds/actions'
