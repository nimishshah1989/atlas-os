// src/lib/policy-compliance.ts
// Pure TypeScript twin of atlas/intelligence/policy/compliance.py.
// Six rules, strict comparisons (>/<). At-limit = not a breach.
// No DB access, no I/O — pure function.
//
// Rules:
//   max_per_stock  — any holding.weight_pct > policy.max_per_stock_pct
//   max_per_sector — sector sum(weight_pct) > policy.max_per_sector_pct
//   max_small_cap  — sum(is_small_cap weights) > policy.max_small_cap_pct
//   min_holdings   — len(holdings) < policy.min_holdings
//   max_positions  — len(holdings) > policy.max_positions
//   cash_floor     — (100 − sum weights) < policy.cash_floor_pct
//
// A null policy field means that rule is unchecked (skip).

export type ComplianceHolding = {
  instrument_id: string
  weight_pct: number     // whole-number percent (e.g. 5.0 = 5%)
  sector: string
  is_small_cap: boolean
}

export type CompliancePolicy = {
  max_per_stock_pct: number | null
  max_per_sector_pct: number | null
  max_small_cap_pct: number | null
  min_holdings: number | null
  max_positions: number | null
  cash_floor_pct: number | null
}

export type ComplianceBreach = {
  rule:
    | 'max_per_stock'
    | 'max_per_sector'
    | 'max_small_cap'
    | 'min_holdings'
    | 'max_positions'
    | 'cash_floor'
  message: string
  actual: number
  limit: number
  // Present for max_per_stock breach — the offending holding
  instrument_id?: string
  // Present for max_per_sector breach — the offending sector
  sector?: string
}

// ---------------------------------------------------------------------------
// Rule 1: max_per_stock
// ---------------------------------------------------------------------------

function checkMaxPerStock(
  holdings: ComplianceHolding[],
  policy: CompliancePolicy,
): ComplianceBreach[] {
  if (policy.max_per_stock_pct === null) return []
  const limit = policy.max_per_stock_pct
  const breaches: ComplianceBreach[] = []
  for (const h of holdings) {
    if (h.weight_pct > limit) {
      breaches.push({
        rule: 'max_per_stock',
        message: `${h.instrument_id} weight ${h.weight_pct}% exceeds per-stock cap ${limit}%`,
        actual: h.weight_pct,
        limit,
        instrument_id: h.instrument_id,
      })
    }
  }
  return breaches
}

// ---------------------------------------------------------------------------
// Rule 2: max_per_sector
// ---------------------------------------------------------------------------

function checkMaxPerSector(
  holdings: ComplianceHolding[],
  policy: CompliancePolicy,
): ComplianceBreach[] {
  if (policy.max_per_sector_pct === null) return []
  const limit = policy.max_per_sector_pct

  // Aggregate sector totals in input order (stable iteration)
  const sectorTotals = new Map<string, number>()
  for (const h of holdings) {
    sectorTotals.set(h.sector, (sectorTotals.get(h.sector) ?? 0) + h.weight_pct)
  }

  const breaches: ComplianceBreach[] = []
  for (const [sector, total] of sectorTotals) {
    if (total > limit) {
      breaches.push({
        rule: 'max_per_sector',
        message: `Sector '${sector}' total ${total}% exceeds per-sector cap ${limit}%`,
        actual: total,
        limit,
        sector,
      })
    }
  }
  return breaches
}

// ---------------------------------------------------------------------------
// Rule 3: max_small_cap
// ---------------------------------------------------------------------------

function checkMaxSmallCap(
  holdings: ComplianceHolding[],
  policy: CompliancePolicy,
): ComplianceBreach | null {
  if (policy.max_small_cap_pct === null) return null
  const limit = policy.max_small_cap_pct
  const smallCapTotal = holdings
    .filter((h) => h.is_small_cap)
    .reduce((sum, h) => sum + h.weight_pct, 0)
  if (smallCapTotal > limit) {
    return {
      rule: 'max_small_cap',
      message: `Small-cap total ${smallCapTotal}% exceeds small-cap cap ${limit}%`,
      actual: smallCapTotal,
      limit,
    }
  }
  return null
}

// ---------------------------------------------------------------------------
// Rule 4: min_holdings
// ---------------------------------------------------------------------------

function checkMinHoldings(
  holdings: ComplianceHolding[],
  policy: CompliancePolicy,
): ComplianceBreach | null {
  if (policy.min_holdings === null) return null
  const limit = policy.min_holdings
  const count = holdings.length
  if (count < limit) {
    return {
      rule: 'min_holdings',
      message: `Portfolio has ${count} holdings, below minimum ${limit}`,
      actual: count,
      limit,
    }
  }
  return null
}

// ---------------------------------------------------------------------------
// Rule 5: max_positions
// ---------------------------------------------------------------------------

function checkMaxPositions(
  holdings: ComplianceHolding[],
  policy: CompliancePolicy,
): ComplianceBreach | null {
  if (policy.max_positions === null) return null
  const limit = policy.max_positions
  const count = holdings.length
  if (count > limit) {
    return {
      rule: 'max_positions',
      message: `Portfolio has ${count} positions, above maximum ${limit}`,
      actual: count,
      limit,
    }
  }
  return null
}

// ---------------------------------------------------------------------------
// Rule 6: cash_floor
// ---------------------------------------------------------------------------

function checkCashFloor(
  holdings: ComplianceHolding[],
  policy: CompliancePolicy,
): ComplianceBreach | null {
  if (policy.cash_floor_pct === null) return null
  const limit = policy.cash_floor_pct
  const invested = holdings.reduce((sum, h) => sum + h.weight_pct, 0)
  const cash = 100 - invested
  if (cash < limit) {
    return {
      rule: 'cash_floor',
      message: `Residual cash ${cash.toFixed(4)}% is below cash floor ${limit}% (invested ${invested.toFixed(4)}% of 100%)`,
      actual: cash,
      limit,
    }
  }
  return null
}

// ---------------------------------------------------------------------------
// Public function
// ---------------------------------------------------------------------------

/**
 * Check a portfolio's holdings against every Policy constraint.
 *
 * Evaluates all six rules in order: max_per_stock, max_per_sector,
 * max_small_cap, min_holdings, max_positions, cash_floor.
 *
 * Returns empty list if and only if fully compliant.
 * A null policy field means that rule is skipped (unchecked).
 */
export function checkCompliance(
  holdings: ComplianceHolding[],
  policy: CompliancePolicy,
): ComplianceBreach[] {
  const breaches: ComplianceBreach[] = []

  // Rule 1
  breaches.push(...checkMaxPerStock(holdings, policy))
  // Rule 2
  breaches.push(...checkMaxPerSector(holdings, policy))
  // Rule 3
  const scBreach = checkMaxSmallCap(holdings, policy)
  if (scBreach !== null) breaches.push(scBreach)
  // Rule 4
  const mhBreach = checkMinHoldings(holdings, policy)
  if (mhBreach !== null) breaches.push(mhBreach)
  // Rule 5
  const mpBreach = checkMaxPositions(holdings, policy)
  if (mpBreach !== null) breaches.push(mpBreach)
  // Rule 6
  const cfBreach = checkCashFloor(holdings, policy)
  if (cfBreach !== null) breaches.push(cfBreach)

  return breaches
}
