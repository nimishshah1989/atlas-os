// frontend/src/lib/queries/component_validation.ts
// Reads atlas_component_validation — per-tier IC status.
// Memory-cached at module level because validator runs at most weekly.
// mean_ic, ic_ir, q5_q1_spread are ratio/IR values (not price/AUM):
// cast to float8 at SELECT boundary is correct per financial-domain rules.
import 'server-only'
import sql from '@/lib/db'

export type ComponentStatus = 'validated' | 'validated_inverse' | 'weak' | 'decorative'

export interface ComponentValidation {
  component_name: string
  badge: string
  threshold_range: string
  implied_action: string
  horizon_days: number
  mean_ic: number | null
  ic_ir: number | null
  q5_q1_spread: number | null
  status: ComponentStatus
}

let _cache: ComponentValidation[] | null = null
let _cacheAt: number = 0
const CACHE_TTL_MS = 5 * 60 * 1000  // 5 minutes

/**
 * All active component validations. Memory-cached (5-min TTL) because the
 * validator runs at most weekly. Server-only.
 */
export async function getComponentValidations(): Promise<ComponentValidation[]> {
  if (_cache !== null && Date.now() - _cacheAt < CACHE_TTL_MS) return _cache

  const rows = await sql<ComponentValidation[]>`
    SELECT
      component_name,
      badge,
      threshold_range,
      implied_action,
      horizon_days,
      mean_ic::float8     AS mean_ic,
      ic_ir::float8       AS ic_ir,
      q5_q1_spread::float8 AS q5_q1_spread,
      status
    FROM atlas.atlas_component_validation
    WHERE as_of_date = (
      SELECT MAX(as_of_date) FROM atlas.atlas_component_validation
    )
  `
  _cache = rows
  _cacheAt = Date.now()
  return rows
}

/**
 * Lookup a specific (component_name, badge) validation. Returns undefined if not catalogued.
 */
export async function getValidation(
  componentName: string,
  badge: string,
): Promise<ComponentValidation | undefined> {
  const all = await getComponentValidations()
  return all.find(v => v.component_name === componentName && v.badge === badge)
}
