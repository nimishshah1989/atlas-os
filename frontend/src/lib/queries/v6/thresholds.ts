// Thresholds control panel data — atlas_foundation.atlas_thresholds ONLY (no atlas.*).
// Every methodology knob the FM can retune (lens weights, conviction, RS, regime, gates…)
// already carries value + min/max + default + description, so the panel is a thin editor over
// this table. Edits persist here; the composite is re-blended from cached lens sub-scores by
// scripts/foundation/recompute_composite_fast.py (faithful to the canonical scorer). RULE #0:
// every value is a real stored threshold; writes are clamped to [min,max], never invented.
import 'server-only'
import sql from '@/lib/db'

export type ThresholdRow = {
  key: string
  value: number
  category: string
  description: string | null
  units: string | null
  min: number | null
  max: number | null
  default: number | null
  isWeight: boolean
  lastModifiedBy: string | null
  lastModifiedAt: string | null
}

const num = (v: string | null) => (v == null ? null : Number(v))

export async function getThresholds(): Promise<ThresholdRow[]> {
  const rows = await sql<Array<Record<string, string | null>>>`
    SELECT threshold_key, threshold_value, category, description, units,
           min_allowed, max_allowed, default_value, last_modified_by, last_modified_at
    FROM atlas_foundation.atlas_thresholds
    WHERE is_active
    ORDER BY category, threshold_key
  `
  return rows.map((r) => ({
    key: r.threshold_key as string,
    value: Number(r.threshold_value),
    category: (r.category as string) ?? 'other',
    description: r.description,
    units: r.units,
    min: num(r.min_allowed),
    max: num(r.max_allowed),
    default: num(r.default_value),
    isWeight: (r.category as string) === 'lens_weight',
    lastModifiedBy: r.last_modified_by,
    lastModifiedAt: r.last_modified_at,
  }))
}

export type ThresholdEdit = { key: string; value: number }

// Persist edits, each clamped/validated against its own min/max (server-side, authoritative).
// Returns the keys actually changed. Rejects unknown keys and out-of-range values rather than
// silently coercing — the FM should see exactly what stuck.
export async function updateThresholds(
  edits: ThresholdEdit[],
  modifiedBy = 'fm-panel',
): Promise<{ updated: string[]; rejected: { key: string; reason: string }[] }> {
  const current = await sql<Array<Record<string, string | null>>>`
    SELECT threshold_key, min_allowed, max_allowed
    FROM atlas_foundation.atlas_thresholds WHERE is_active
  `
  const bounds = new Map(current.map((r) => [r.threshold_key as string, { min: num(r.min_allowed), max: num(r.max_allowed) }]))
  const updated: string[] = []
  const rejected: { key: string; reason: string }[] = []

  for (const e of edits) {
    const b = bounds.get(e.key)
    if (!b) { rejected.push({ key: e.key, reason: 'unknown key' }); continue }
    if (!Number.isFinite(e.value)) { rejected.push({ key: e.key, reason: 'not a number' }); continue }
    if (b.min != null && e.value < b.min) { rejected.push({ key: e.key, reason: `below min ${b.min}` }); continue }
    if (b.max != null && e.value > b.max) { rejected.push({ key: e.key, reason: `above max ${b.max}` }); continue }
    await sql`
      UPDATE atlas_foundation.atlas_thresholds
      SET threshold_value = ${e.value}, last_modified_by = ${modifiedBy}, last_modified_at = now()
      WHERE threshold_key = ${e.key} AND is_active
    `
    updated.push(e.key)
  }
  return { updated, rejected }
}
