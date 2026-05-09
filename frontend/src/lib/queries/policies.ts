// src/lib/queries/policies.ts
import 'server-only'
import sql from '@/lib/db'

export type DecisionPolicyRow = {
  policy_key: string
  policy_kind: 'gate_states' | 'multiplier_map'
  policy_value: string[] | Record<string, string>  // JSON-typed
  description: string
  methodology_section: string | null
  last_modified_by: string
  last_modified_at: Date
}

export type PolicyHistoryRow = {
  id: number
  policy_key: string
  old_value: string[] | Record<string, string> | null
  new_value: string[] | Record<string, string>
  changed_by: string
  changed_at: Date
  change_reason: string | null
}

export async function getAllDecisionPolicies(): Promise<DecisionPolicyRow[]> {
  return sql<DecisionPolicyRow[]>`
    SELECT
      policy_key,
      policy_kind,
      policy_value,
      description,
      methodology_section,
      last_modified_by,
      last_modified_at
    FROM atlas.atlas_decision_policy
    WHERE is_active = TRUE
    ORDER BY policy_kind, policy_key
  `
}

export async function getPolicyHistory(policyKey: string, limit: number = 20): Promise<PolicyHistoryRow[]> {
  return sql<PolicyHistoryRow[]>`
    SELECT
      id, policy_key, old_value, new_value, changed_by, changed_at, change_reason
    FROM atlas.atlas_decision_policy_history
    WHERE policy_key = ${policyKey}
    ORDER BY changed_at DESC
    LIMIT ${limit}
  `
}
