// src/lib/queries/policy.ts
// Reads the effective portfolio policy for a given portfolio id.
// Merge semantics mirror atlas/intelligence/policy/policy.py:
//   - load house-default row (is_house_default = TRUE)
//   - load per-portfolio override row (portfolio_id = $id) if any
//   - per field: if override row exists and field is non-null → source='overridden'
//   - otherwise → source='inherited' with house-default value
//
// pct columns store whole-number percent (5 = 5%, 8 = 8%).
// rank columns store fractions in [0,1] (0.60 = 60th percentile).
// All numeric values returned as strings (postgres driver convention).
import 'server-only'
import sql from '@/lib/db'
import type { EffectivePolicy, PolicyFieldValue } from '@/components/portfolio/PolicyPanel'

// ---------------------------------------------------------------------------
// DB row types — raw Postgres output
// ---------------------------------------------------------------------------

type PolicyDbRow = {
  cash_floor_pct: string | null
  respect_regime_cap: boolean | null
  max_per_stock_pct: string | null
  max_per_sector_pct: string | null
  max_small_cap_pct: string | null
  min_holdings: string | null
  max_positions: string | null
  buy_states: string[] | null
  min_within_state_rank: string | null
  min_rs_rank: string | null
  hard_stop_pct: string | null
  state_exit_trim: string | null
  state_exit_full: string | null
  trailing_stop_pct: string | null
  instrument_universe: string | null
  benchmark: string | null
  rebalance_cadence: string | null
}

// ---------------------------------------------------------------------------
// SQL queries
// ---------------------------------------------------------------------------

async function loadHouseDefault(): Promise<PolicyDbRow | null> {
  const rows = await sql<PolicyDbRow[]>`
    SELECT
      cash_floor_pct::text,
      respect_regime_cap,
      max_per_stock_pct::text,
      max_per_sector_pct::text,
      max_small_cap_pct::text,
      min_holdings::text,
      max_positions::text,
      buy_states,
      min_within_state_rank::text,
      min_rs_rank::text,
      hard_stop_pct::text,
      state_exit_trim,
      state_exit_full,
      trailing_stop_pct::text,
      instrument_universe,
      benchmark,
      rebalance_cadence
    FROM atlas.atlas_portfolio_policy
    WHERE is_house_default = TRUE
    LIMIT 1
  `
  return rows[0] ?? null
}

async function loadPortfolioOverride(portfolioId: string): Promise<PolicyDbRow | null> {
  const rows = await sql<PolicyDbRow[]>`
    SELECT
      cash_floor_pct::text,
      respect_regime_cap,
      max_per_stock_pct::text,
      max_per_sector_pct::text,
      max_small_cap_pct::text,
      min_holdings::text,
      max_positions::text,
      buy_states,
      min_within_state_rank::text,
      min_rs_rank::text,
      hard_stop_pct::text,
      state_exit_trim,
      state_exit_full,
      trailing_stop_pct::text,
      instrument_universe,
      benchmark,
      rebalance_cadence
    FROM atlas.atlas_portfolio_policy
    WHERE portfolio_id = ${portfolioId}
    LIMIT 1
  `
  return rows[0] ?? null
}

// ---------------------------------------------------------------------------
// Merge logic — pure function, separately testable
// ---------------------------------------------------------------------------

type ScalarFieldValue = string | string[] | boolean | null

// resolveField mirrors the backend atlas/intelligence/policy/policy.py _merge rule:
//   - SQL NULL (JS null/undefined) → inherited from house default
//   - ANY non-null value, including an empty array [], → overridden
//
// The sql driver returns SQL NULL as JS null and an empty Postgres array as
// a JS empty array []. We must NOT treat [] as inherited — an empty buy_states
// is a valid explicit override meaning "buy nothing".
export function resolveField(
  houseVal: ScalarFieldValue,
  overrideVal: ScalarFieldValue,
): PolicyFieldValue {
  if (overrideVal !== null && overrideVal !== undefined) {
    return { value: overrideVal, source: 'overridden' }
  }
  return { value: houseVal, source: 'inherited' }
}

function mergeRows(house: PolicyDbRow, override: PolicyDbRow | null): EffectivePolicy {
  const o = override ?? {}
  return {
    cash_floor_pct:       resolveField(house.cash_floor_pct, (o as PolicyDbRow).cash_floor_pct ?? null),
    respect_regime_cap:   resolveField(house.respect_regime_cap, (o as PolicyDbRow).respect_regime_cap ?? null),
    max_per_stock_pct:    resolveField(house.max_per_stock_pct, (o as PolicyDbRow).max_per_stock_pct ?? null),
    max_per_sector_pct:   resolveField(house.max_per_sector_pct, (o as PolicyDbRow).max_per_sector_pct ?? null),
    max_small_cap_pct:    resolveField(house.max_small_cap_pct, (o as PolicyDbRow).max_small_cap_pct ?? null),
    min_holdings:         resolveField(house.min_holdings, (o as PolicyDbRow).min_holdings ?? null),
    max_positions:        resolveField(house.max_positions, (o as PolicyDbRow).max_positions ?? null),
    buy_states:           resolveField(house.buy_states, (o as PolicyDbRow).buy_states ?? null),
    min_within_state_rank: resolveField(house.min_within_state_rank, (o as PolicyDbRow).min_within_state_rank ?? null),
    min_rs_rank:          resolveField(house.min_rs_rank, (o as PolicyDbRow).min_rs_rank ?? null),
    hard_stop_pct:        resolveField(house.hard_stop_pct, (o as PolicyDbRow).hard_stop_pct ?? null),
    state_exit_trim:      resolveField(house.state_exit_trim, (o as PolicyDbRow).state_exit_trim ?? null),
    state_exit_full:      resolveField(house.state_exit_full, (o as PolicyDbRow).state_exit_full ?? null),
    trailing_stop_pct:    resolveField(house.trailing_stop_pct, (o as PolicyDbRow).trailing_stop_pct ?? null),
    instrument_universe:  resolveField(house.instrument_universe, (o as PolicyDbRow).instrument_universe ?? null),
    benchmark:            resolveField(house.benchmark, (o as PolicyDbRow).benchmark ?? null),
    rebalance_cadence:    resolveField(house.rebalance_cadence, (o as PolicyDbRow).rebalance_cadence ?? null),
  }
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

/**
 * Returns the effective policy for a portfolio, or null if no house-default
 * row has been seeded yet.
 *
 * Each field carries both the resolved value and whether it is 'inherited'
 * from the house default or 'overridden' by the portfolio's own row.
 */
export async function getEffectivePolicy(portfolioId: string): Promise<EffectivePolicy | null> {
  const [house, override] = await Promise.all([
    loadHouseDefault(),
    loadPortfolioOverride(portfolioId),
  ])
  if (house === null) return null
  return mergeRows(house, override)
}

/**
 * Returns the house-default policy with all fields marked as 'inherited'.
 * Used for the /setup/policy page when no portfolio is selected.
 * Returns null if no house-default row has been seeded yet.
 */
export async function getHouseDefaultPolicy(): Promise<EffectivePolicy | null> {
  const house = await loadHouseDefault()
  if (house === null) return null
  return mergeRows(house, null)
}
