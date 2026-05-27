// Position-sizing recommendation function — v6.
// Port of v2 `computeSizing` from `lib/position-sizing.ts` with v6 extensions:
//   - per-stock current_weight_pct (v2 used portfolio-total currentInvestedPct)
//   - deployment_multiplier as a per-stock scalar (0.5x / 1.0x / 1.5x)
//   - sector_gap_pp wired (v2 stubbed as 0)
//   - cell_conviction_depth gate (new in v6)
//
// PURE FUNCTION — no DB calls, no async, no React.

/** Which policy or regime limit is the tightest constraint on the suggested add. */
export type BindingConstraint =
  | 'max_per_stock'
  | 'deployment_cap'
  | 'sector_cap'
  | 'conviction_floor'

export type SizingInput = {
  /** Current % weight this stock holds in the portfolio (whole-number, e.g. 3.5 = 3.5%). */
  current_weight_pct: number
  /** Policy cap per stock (e.g. 5 = 5%). */
  max_per_stock_pct: number
  /**
   * Regime-derived sizing scalar (0.5 = bear / 1.0 = neutral / 1.5 = bull).
   * Multiplied against max_per_stock_pct to get the regime-adjusted effective cap.
   * DB stores values such as 0.0, 0.4, 0.7, 1.0 (regime.py) — those pass through unchanged.
   */
  deployment_multiplier: number
  /**
   * Book weight minus Nifty 500 benchmark weight for this stock's sector (pp).
   * Positive = overweight. Sourced from B.2 getSectorBookExposure().
   */
  sector_gap_pp: number
  /**
   * Number of Atlas cell rules that fire in support of this stock's active signal (0..5).
   * Zero means no cell conviction — position sizing is blocked.
   */
  cell_conviction_depth: number
}

export type SizingRec = {
  suggested_add_pct: number
  binding_constraint: BindingConstraint
  rationale: string
}

/** Overweight sector threshold (pp) above which sector_cap binds. */
const SECTOR_OVERWEIGHT_THRESHOLD_PP = 5

/** Underweight sector adjustment boost (fraction). 0.2 = +20% to suggested add. */
const SECTOR_UNDERWEIGHT_BOOST = 0.2

/** Underweight sector threshold (pp) below which the boost applies. */
const SECTOR_UNDERWEIGHT_THRESHOLD_PP = -5

/**
 * Compute the recommended position-size addition given policy + regime + sector inputs.
 *
 * Binding constraint priority (highest to lowest):
 *   1. conviction_floor — zero rules support: do not add
 *   2. max_per_stock    — already at or above the per-stock cap
 *   3. deployment_cap   — regime multiplier reduces effective cap below the stock cap
 *   4. sector_cap       — sector is overweight vs benchmark by > SECTOR_OVERWEIGHT_THRESHOLD_PP
 */
export function computeSizing(input: SizingInput): SizingRec {
  const {
    current_weight_pct,
    max_per_stock_pct,
    deployment_multiplier,
    sector_gap_pp,
    cell_conviction_depth,
  } = input

  // Guard: conviction_floor — no cell rules support this position.
  if (cell_conviction_depth <= 0) {
    return {
      suggested_add_pct: 0,
      binding_constraint: 'conviction_floor',
      rationale: '+0% — no cell conviction (depth=0); position entry not supported',
    }
  }

  // Guard: already at or above per-stock cap.
  const roomToMax = max_per_stock_pct - current_weight_pct
  if (roomToMax <= 0) {
    return {
      suggested_add_pct: 0,
      binding_constraint: 'max_per_stock',
      rationale: `+0% — already at ${max_per_stock_pct}% per-stock cap`,
    }
  }

  // Effective cap = max_per_stock_pct scaled by regime multiplier.
  // When multiplier = 1.0: full cap. When 0.5: halved. When 1.5: boosted.
  // (V2 equivalent: regimeCap = deploymentMultiplier * 100; here per-stock.)
  const effectiveCap = max_per_stock_pct * deployment_multiplier
  const regimeRoom = effectiveCap - current_weight_pct

  // Guard: sector overweight — sector_cap binds.
  if (sector_gap_pp > SECTOR_OVERWEIGHT_THRESHOLD_PP) {
    return {
      suggested_add_pct: 0,
      binding_constraint: 'sector_cap',
      rationale: `+0% — sector overweight by ${sector_gap_pp.toFixed(1)}pp vs benchmark (cap: ${SECTOR_OVERWEIGHT_THRESHOLD_PP}pp threshold)`,
    }
  }

  // Base suggested = min of room to policy cap and regime-adjusted room.
  const baseRaw = Math.min(roomToMax, regimeRoom)
  let suggested = Math.max(baseRaw, 0)

  // Apply sector underweight boost (up to +SECTOR_UNDERWEIGHT_BOOST fraction).
  if (sector_gap_pp < SECTOR_UNDERWEIGHT_THRESHOLD_PP) {
    const boosted = suggested * (1 + SECTOR_UNDERWEIGHT_BOOST)
    suggested = Math.min(boosted, roomToMax) // never exceed per-stock cap
  }

  // Round to 1 decimal place.
  suggested = Math.round(suggested * 10) / 10

  // Determine binding constraint for the non-zero case.
  let binding: BindingConstraint
  let bindingDesc: string

  if (suggested <= 0) {
    // regimeRoom was ≤ 0 but sector_cap didn't fire — deployment_cap binds.
    binding = 'deployment_cap'
    bindingDesc = `+0% — deployment cap at ${deployment_multiplier}x leaves no room (effective cap ${effectiveCap.toFixed(1)}%)`
    return { suggested_add_pct: 0, binding_constraint: binding, rationale: bindingDesc }
  }

  // Determine which constraint was tighter: max_per_stock or deployment_cap.
  if (regimeRoom >= roomToMax) {
    // Per-stock cap is the tighter constraint (regime has more room).
    binding = 'max_per_stock'
    bindingDesc = `+${suggested.toFixed(1)}% suggested — within ${max_per_stock_pct}% max per stock, regime ${deployment_multiplier}x active`
  } else {
    // Regime-adjusted effective cap is tighter.
    binding = 'deployment_cap'
    bindingDesc = `+${suggested.toFixed(1)}% suggested — deployment cap ${deployment_multiplier}x limits effective cap to ${effectiveCap.toFixed(1)}%`
  }

  // Add sector context to rationale if sector adjustment was applied.
  let rationale = bindingDesc
  if (sector_gap_pp < SECTOR_UNDERWEIGHT_THRESHOLD_PP) {
    rationale += `; sector underweight ${Math.abs(sector_gap_pp).toFixed(1)}pp → boosted`
  }

  return {
    suggested_add_pct: suggested,
    binding_constraint: binding,
    rationale,
  }
}
