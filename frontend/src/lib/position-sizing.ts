// Position-sizing helper — TS port of atlas/intelligence/policy/sizing.py.
// All percent values are whole-number strings or numbers (e.g. "5" = 5%).

export type SizingResult = {
  suggestedPct: string
  bindingConstraint: string
  /** True only when a real sector-gap value was passed in (not a default). */
  sectorGapApplied: boolean
}

/**
 * Compute the suggested position size given policy + regime inputs.
 *
 * @param maxPerStockPct   Policy max-per-stock cap, as a percent string (e.g. "5").
 * @param deploymentMultiplier  Regime multiplier 0.0–1.0 (fraction of full deployment).
 * @param currentInvestedPct   Sum of existing holding weight_pct values in the portfolio.
 *
 * target_gap is not yet wired — Task 2.6 feeds deriveSectorTargets empty current weights.
 * It defaults to maxPerStockPct so it does not bind tighter than the stock cap.
 * sectorGapApplied is always false until that work lands.
 */
export function computeSizing(
  maxPerStockPct: string,
  deploymentMultiplier: string,
  currentInvestedPct: number,
): SizingResult {
  const maxPs = parseFloat(maxPerStockPct)
  // deployment_multiplier is a fraction 0.0–1.0 → convert to whole-number percent
  const regimeCap = parseFloat(deploymentMultiplier) * 100
  const regimeRoom = regimeCap - currentInvestedPct
  const targetGap = maxPs // sector-gap not yet wired

  const raw = Math.min(targetGap, maxPs, regimeRoom)
  const suggested = Math.max(raw, 0)

  let binding: string
  if (suggested <= 0) {
    if (targetGap <= 0) binding = 'target_gap'
    else binding = 'regime_cap'
  } else if (raw === targetGap && raw === maxPs) {
    binding = 'max_per_stock' // tie: max_per_stock wins (targetGap == maxPs by design)
  } else if (raw === maxPs) {
    binding = 'max_per_stock'
  } else {
    binding = 'regime_cap'
  }

  // sector-gap term is defaulted (not derived from real sector weights)
  return {
    suggestedPct: suggested.toFixed(1),
    bindingConstraint: binding,
    sectorGapApplied: false,
  }
}
