/**
 * Sector target derivation — pure TypeScript mirror of
 * atlas/intelligence/policy/targets.py:derive_sector_targets.
 *
 * Formula (C6):
 *   raw[i]        = pct_stage_2[i] * mean_within_state_rank[i]
 *   total_raw     = sum(raw)
 *   normalized[i] = raw[i] / total_raw
 *   pre_cap[i]    = normalized[i] * regime_cap
 *   target[i]     = min(pre_cap[i], max_per_sector_pct), rounded to 2 dp
 *   gap[i]        = target[i] - current[i]
 *
 * Degenerate: if total_raw = 0, all targets = 0.
 * Null inputs: pct_stage_2=null and mean_within_state_rank=null are treated as 0.
 *
 * These are display-only percentage weights; regular number arithmetic is
 * acceptable (not stored financial values requiring Decimal).
 */

export interface SectorSignalInput {
  sector: string
  /** Fraction [0,1] of sector stocks in Stage 2. null → 0. */
  pct_stage_2: number | null
  /** Mean within-state rank for the sector [0,1]. null → 0. */
  mean_within_state_rank: number | null
}

export interface SectorTargetOutput {
  sector: string
  /** Current portfolio weight (whole-number %) */
  current: number
  /** Derived target weight (whole-number %, 2 dp) */
  target: number
  /** gap = target - current; negative = trim signal */
  gap: number
}

/**
 * Derive per-sector target weights given sector signals, regime cap,
 * and max-per-sector policy constraint.
 *
 * @param sectorSignals      One entry per sector with pct_stage_2 + mean_within_state_rank.
 * @param currentWeights     Map of sector → current portfolio weight (whole-number %).
 *                           Missing sectors default to 0.
 * @param regimeCap          Max total book deployment (whole-number %, e.g. 80 = 80%).
 * @param maxPerSectorPct    Policy per-sector cap (whole-number %, e.g. 15 = 15%).
 * @returns Array of SectorTargetOutput, same order as sectorSignals.
 */
export function deriveSectorTargets(
  sectorSignals: SectorSignalInput[],
  currentWeights: Record<string, number>,
  regimeCap: number,
  maxPerSectorPct: number,
): SectorTargetOutput[] {
  if (sectorSignals.length === 0) return []

  // Step 1: raw scores (null → 0)
  const raws = sectorSignals.map(s =>
    (s.pct_stage_2 ?? 0) * (s.mean_within_state_rank ?? 0)
  )

  const totalRaw = raws.reduce((a, b) => a + b, 0)

  // Degenerate: all zeros
  if (totalRaw === 0) {
    return sectorSignals.map(s => {
      const current = currentWeights[s.sector] ?? 0
      return { sector: s.sector, current, target: 0, gap: -current }
    })
  }

  // Steps 3–5: normalize → scale → cap → round
  return sectorSignals.map((s, i) => {
    const normalized = raws[i] / totalRaw
    const preCap = normalized * regimeCap
    const capped = Math.min(preCap, maxPerSectorPct)
    const target = round2dp(capped)
    const current = currentWeights[s.sector] ?? 0
    const gap = round2dp(target - current)
    return { sector: s.sector, current, target, gap }
  })
}

/** Round to 2 decimal places (ROUND_HALF_UP). */
function round2dp(v: number): number {
  return Math.round(v * 100) / 100
}
