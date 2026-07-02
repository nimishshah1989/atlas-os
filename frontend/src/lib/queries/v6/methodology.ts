// Live methodology thresholds — the single source of truth (atlas_foundation.atlas_thresholds,
// the same table the /thresholds panel edits and the scoring engine reads). The public methodology
// page renders these so its weights, convergence boosts and conviction tiers always match the live
// engine — no hard-coded numbers that can drift from the model.
import 'server-only'
import sql from '@/lib/db'
import type { LensWeightMap } from '@/lib/v6/sectorScore'

export type MethodologyThresholds = {
  // lens weights as fractions (0–1); valuation/policy are context (typically 0).
  weights: LensWeightMap & { valuation: number; policy: number }
  convergence: { agreeMin: number; boost2: number; boost3: number; boost4plus: number }
  conviction: {
    highestScore: number; highestLayers: number
    highScore: number; highLayers: number
    mediumScore: number; watchScore: number
  }
}

export async function getMethodologyThresholds(): Promise<MethodologyThresholds> {
  const rows = (await sql`
    SELECT threshold_key, threshold_value
    FROM atlas_foundation.atlas_thresholds
    WHERE is_active AND (threshold_key LIKE 'lens_weight_%'
       OR threshold_key LIKE 'lens_convergence_%'
       OR threshold_key LIKE 'lens_conviction_%')
  `) as unknown as { threshold_key: string; threshold_value: string }[]
  const m = new Map(rows.map((r) => [r.threshold_key, Number(r.threshold_value)]))
  const g = (k: string, d = 0) => m.get(k) ?? d
  return {
    weights: {
      technical: g('lens_weight_technical'),
      fundamental: g('lens_weight_fundamental'),
      flow: g('lens_weight_flow'),
      catalyst: g('lens_weight_catalyst'),
      valuation: g('lens_weight_valuation'),
      policy: g('lens_weight_policy'),
    },
    convergence: {
      agreeMin: g('lens_convergence_threshold', 40),
      boost2: g('lens_convergence_2', 1.06),
      boost3: g('lens_convergence_3', 1.1),
      boost4plus: g('lens_convergence_4plus', 1.15),
    },
    conviction: {
      highestScore: g('lens_conviction_highest_score', 70),
      highestLayers: g('lens_conviction_highest_min_layers', 3),
      highScore: g('lens_conviction_high_score', 58),
      highLayers: g('lens_conviction_high_min_layers', 2),
      mediumScore: g('lens_conviction_medium_score', 45),
      watchScore: g('lens_conviction_watch_score', 30),
    },
  }
}
