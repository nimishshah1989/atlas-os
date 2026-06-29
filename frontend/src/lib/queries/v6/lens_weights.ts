// Single source of truth for the lens composite weights: foundation_staging.atlas_thresholds.
// The FM edits these in the /thresholds panel; both the backend stock composite and every frontend
// roll-up (sector / fund / ETF) read the SAME values, so a weight change in one place moves
// everything. Server-only — pages fetch once and thread the weights into the pure score helpers.
import 'server-only'
import sql from '@/lib/db'
import type { LensWeightMap } from '@/lib/v6/sectorScore'
import { DEFAULT_WEIGHTS } from '@/lib/v6/sectorScore'

export async function getLensWeights(): Promise<LensWeightMap> {
  const rows = (await sql`
    SELECT threshold_key, threshold_value
    FROM foundation_staging.atlas_thresholds
    WHERE threshold_key IN ('lens_weight_technical','lens_weight_fundamental','lens_weight_flow','lens_weight_catalyst')
  `) as unknown as { threshold_key: string; threshold_value: string }[]
  const m = new Map(rows.map((r) => [r.threshold_key, Number(r.threshold_value)]))
  return {
    technical: m.get('lens_weight_technical') ?? DEFAULT_WEIGHTS.technical,
    fundamental: m.get('lens_weight_fundamental') ?? DEFAULT_WEIGHTS.fundamental,
    flow: m.get('lens_weight_flow') ?? DEFAULT_WEIGHTS.flow,
    catalyst: m.get('lens_weight_catalyst') ?? DEFAULT_WEIGHTS.catalyst,
  }
}
