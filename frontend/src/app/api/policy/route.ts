// src/app/api/policy/route.ts
// POST /api/policy — validate and persist policy changes.
//
// Body: { portfolioId: string | null, changes: Partial<Record<fieldKey, value | null>> }
//   portfolioId null  → edit house-default row (is_house_default = TRUE)
//   portfolioId set   → edit per-portfolio override row
//   change value null → clear column (revert field to inherit from house default)
//
// Flow:
//   1. Load current effective policy (house + optional portfolio override)
//   2. Apply changes onto current policy → candidate
//   3. validatePolicy(candidate) — if violations → 400, write nothing
//   4. Persist: house → UPDATE; portfolio → UPSERT (INSERT or UPDATE)
//   5. Re-read effective policy → return {data}
//
// Conventions match /api/portfolio/propose/route.ts exactly:
//   force-dynamic, NextRequest/NextResponse, parameterized sql, Atlas error envelope.

import { NextRequest, NextResponse } from 'next/server'
import sql from '@/lib/db'
import { validatePolicy, POLICY_FIELDS } from '@/lib/policy-validate'
import type { FlatPolicy } from '@/lib/policy-validate'

export const dynamic = 'force-dynamic'

// ---------------------------------------------------------------------------
// Allowed field keys (whitelist — prevents arbitrary column injection)
// ---------------------------------------------------------------------------

const ALLOWED_FIELD_KEYS = new Set<string>(POLICY_FIELDS)

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type PolicyRow = FlatPolicy
type ChangeValue = string | string[] | boolean | null

// ---------------------------------------------------------------------------
// DB helpers — load house and portfolio override rows
// ---------------------------------------------------------------------------

async function loadHouseRow(): Promise<PolicyRow | null> {
  const rows = await sql<PolicyRow[]>`
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

async function loadOverrideRow(portfolioId: string): Promise<PolicyRow | null> {
  const rows = await sql<PolicyRow[]>`
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
// Merge — pure function: override row onto house row
// Mirrors atlas/intelligence/policy/policy.py _merge:
//   override non-null value → use override; null → use house default
// ---------------------------------------------------------------------------

function mergeRows(house: PolicyRow, override: PolicyRow | null): FlatPolicy {
  if (!override) return { ...house }
  const merged: FlatPolicy = {} as FlatPolicy
  for (const field of POLICY_FIELDS) {
    const ov = override[field]
    if (ov !== null && ov !== undefined) {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      ;(merged as any)[field] = ov
    } else {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      ;(merged as any)[field] = house[field]
    }
  }
  return merged
}

// ---------------------------------------------------------------------------
// Apply changes onto effective policy → candidate FlatPolicy
// null change means "revert to inherit" — use the current inherited value
// ---------------------------------------------------------------------------

function applyChanges(effective: FlatPolicy, changes: Record<string, ChangeValue>): FlatPolicy {
  const candidate: FlatPolicy = { ...effective }
  for (const [key, val] of Object.entries(changes)) {
    if (val !== null) {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      ;(candidate as any)[key] = val
    }
    // null: candidate already has the inherited house value — no update needed for validation
  }
  return candidate
}

// ---------------------------------------------------------------------------
// Persist house-default: single UPDATE with all changed columns
// Each changed key is pre-validated against ALLOWED_FIELD_KEYS.
// Single sql call per changed field — table has exactly 1 house row; fast.
// ---------------------------------------------------------------------------

async function persistHouseChanges(changes: Record<string, ChangeValue>): Promise<void> {
  const entries = Object.entries(changes)
  if (entries.length === 0) return

  // Build one parameterized UPDATE per changed field.
  // Field names come from the pre-validated ALLOWED_FIELD_KEYS whitelist —
  // never from user input — so embedding them as SQL literals is safe.
  // Values are passed as tagged-template parameters (no interpolation).
  for (const [field, val] of entries) {
    const scalarVal = Array.isArray(val) ? val : val === null ? null : String(val)
    await persistOneHouseField(field, scalarVal)
  }
}

// Each function is a separate tagged-template call so the field name is a
// compile-time literal in the SQL text, not a runtime interpolation.
// We use a dispatch approach via the parameterized value.
async function persistOneHouseField(
  field: string,
  val: string | string[] | boolean | null,
): Promise<void> {
  // The field name is embedded as a SQL literal (not a parameter) because
  // tagged-template drivers do not support column-name parameters.
  // Safety: field is validated against ALLOWED_FIELD_KEYS (17 fixed names) before reaching here.
  switch (field) {
    case 'cash_floor_pct':
      await sql`UPDATE atlas.atlas_portfolio_policy SET cash_floor_pct = ${val} WHERE is_house_default = TRUE`; break
    case 'respect_regime_cap':
      await sql`UPDATE atlas.atlas_portfolio_policy SET respect_regime_cap = ${val} WHERE is_house_default = TRUE`; break
    case 'max_per_stock_pct':
      await sql`UPDATE atlas.atlas_portfolio_policy SET max_per_stock_pct = ${val} WHERE is_house_default = TRUE`; break
    case 'max_per_sector_pct':
      await sql`UPDATE atlas.atlas_portfolio_policy SET max_per_sector_pct = ${val} WHERE is_house_default = TRUE`; break
    case 'max_small_cap_pct':
      await sql`UPDATE atlas.atlas_portfolio_policy SET max_small_cap_pct = ${val} WHERE is_house_default = TRUE`; break
    case 'min_holdings':
      await sql`UPDATE atlas.atlas_portfolio_policy SET min_holdings = ${val} WHERE is_house_default = TRUE`; break
    case 'max_positions':
      await sql`UPDATE atlas.atlas_portfolio_policy SET max_positions = ${val} WHERE is_house_default = TRUE`; break
    case 'buy_states':
      await sql`UPDATE atlas.atlas_portfolio_policy SET buy_states = ${val} WHERE is_house_default = TRUE`; break
    case 'min_within_state_rank':
      await sql`UPDATE atlas.atlas_portfolio_policy SET min_within_state_rank = ${val} WHERE is_house_default = TRUE`; break
    case 'min_rs_rank':
      await sql`UPDATE atlas.atlas_portfolio_policy SET min_rs_rank = ${val} WHERE is_house_default = TRUE`; break
    case 'hard_stop_pct':
      await sql`UPDATE atlas.atlas_portfolio_policy SET hard_stop_pct = ${val} WHERE is_house_default = TRUE`; break
    case 'state_exit_trim':
      await sql`UPDATE atlas.atlas_portfolio_policy SET state_exit_trim = ${val} WHERE is_house_default = TRUE`; break
    case 'state_exit_full':
      await sql`UPDATE atlas.atlas_portfolio_policy SET state_exit_full = ${val} WHERE is_house_default = TRUE`; break
    case 'trailing_stop_pct':
      await sql`UPDATE atlas.atlas_portfolio_policy SET trailing_stop_pct = ${val} WHERE is_house_default = TRUE`; break
    case 'instrument_universe':
      await sql`UPDATE atlas.atlas_portfolio_policy SET instrument_universe = ${val} WHERE is_house_default = TRUE`; break
    case 'benchmark':
      await sql`UPDATE atlas.atlas_portfolio_policy SET benchmark = ${val} WHERE is_house_default = TRUE`; break
    case 'rebalance_cadence':
      await sql`UPDATE atlas.atlas_portfolio_policy SET rebalance_cadence = ${val} WHERE is_house_default = TRUE`; break
    default:
      break
  }
}

// ---------------------------------------------------------------------------
// Persist portfolio override
// ---------------------------------------------------------------------------

async function upsertPortfolioOverride(
  portfolioId: string,
  changes: Record<string, ChangeValue>,
  existingRow: PolicyRow | null,
): Promise<void> {
  if (existingRow) {
    for (const [field, val] of Object.entries(changes)) {
      const scalarVal = Array.isArray(val) ? val : val === null ? null : String(val)
      await persistOnePortfolioField(portfolioId, field, scalarVal)
    }
  } else {
    // INSERT: only write non-null changed fields
    const nonNullChanges = Object.entries(changes).filter(([, v]) => v !== null)
    if (nonNullChanges.length === 0) return
    await insertPortfolioRow(portfolioId, Object.fromEntries(nonNullChanges))
  }
}

async function persistOnePortfolioField(
  portfolioId: string,
  field: string,
  val: string | string[] | boolean | null,
): Promise<void> {
  switch (field) {
    case 'cash_floor_pct':
      await sql`UPDATE atlas.atlas_portfolio_policy SET cash_floor_pct = ${val} WHERE portfolio_id = ${portfolioId}::uuid`; break
    case 'respect_regime_cap':
      await sql`UPDATE atlas.atlas_portfolio_policy SET respect_regime_cap = ${val} WHERE portfolio_id = ${portfolioId}::uuid`; break
    case 'max_per_stock_pct':
      await sql`UPDATE atlas.atlas_portfolio_policy SET max_per_stock_pct = ${val} WHERE portfolio_id = ${portfolioId}::uuid`; break
    case 'max_per_sector_pct':
      await sql`UPDATE atlas.atlas_portfolio_policy SET max_per_sector_pct = ${val} WHERE portfolio_id = ${portfolioId}::uuid`; break
    case 'max_small_cap_pct':
      await sql`UPDATE atlas.atlas_portfolio_policy SET max_small_cap_pct = ${val} WHERE portfolio_id = ${portfolioId}::uuid`; break
    case 'min_holdings':
      await sql`UPDATE atlas.atlas_portfolio_policy SET min_holdings = ${val} WHERE portfolio_id = ${portfolioId}::uuid`; break
    case 'max_positions':
      await sql`UPDATE atlas.atlas_portfolio_policy SET max_positions = ${val} WHERE portfolio_id = ${portfolioId}::uuid`; break
    case 'buy_states':
      await sql`UPDATE atlas.atlas_portfolio_policy SET buy_states = ${val} WHERE portfolio_id = ${portfolioId}::uuid`; break
    case 'min_within_state_rank':
      await sql`UPDATE atlas.atlas_portfolio_policy SET min_within_state_rank = ${val} WHERE portfolio_id = ${portfolioId}::uuid`; break
    case 'min_rs_rank':
      await sql`UPDATE atlas.atlas_portfolio_policy SET min_rs_rank = ${val} WHERE portfolio_id = ${portfolioId}::uuid`; break
    case 'hard_stop_pct':
      await sql`UPDATE atlas.atlas_portfolio_policy SET hard_stop_pct = ${val} WHERE portfolio_id = ${portfolioId}::uuid`; break
    case 'state_exit_trim':
      await sql`UPDATE atlas.atlas_portfolio_policy SET state_exit_trim = ${val} WHERE portfolio_id = ${portfolioId}::uuid`; break
    case 'state_exit_full':
      await sql`UPDATE atlas.atlas_portfolio_policy SET state_exit_full = ${val} WHERE portfolio_id = ${portfolioId}::uuid`; break
    case 'trailing_stop_pct':
      await sql`UPDATE atlas.atlas_portfolio_policy SET trailing_stop_pct = ${val} WHERE portfolio_id = ${portfolioId}::uuid`; break
    case 'instrument_universe':
      await sql`UPDATE atlas.atlas_portfolio_policy SET instrument_universe = ${val} WHERE portfolio_id = ${portfolioId}::uuid`; break
    case 'benchmark':
      await sql`UPDATE atlas.atlas_portfolio_policy SET benchmark = ${val} WHERE portfolio_id = ${portfolioId}::uuid`; break
    case 'rebalance_cadence':
      await sql`UPDATE atlas.atlas_portfolio_policy SET rebalance_cadence = ${val} WHERE portfolio_id = ${portfolioId}::uuid`; break
    default:
      break
  }
}

async function insertPortfolioRow(
  portfolioId: string,
  changes: Record<string, ChangeValue>,
): Promise<void> {
  // We INSERT only the fields that were explicitly changed.
  // Since field names are pre-validated, we dispatch via a switch on the known set.
  // For INSERT we need all columns in one call. Build a base row with NULLs then
  // set the changed fields. Use a single parameterized INSERT of all 17 cols.
  const base: Record<string, ChangeValue> = {
    cash_floor_pct: null, respect_regime_cap: null, max_per_stock_pct: null,
    max_per_sector_pct: null, max_small_cap_pct: null, min_holdings: null,
    max_positions: null, buy_states: null, min_within_state_rank: null,
    min_rs_rank: null, hard_stop_pct: null, state_exit_trim: null,
    state_exit_full: null, trailing_stop_pct: null, instrument_universe: null,
    benchmark: null, rebalance_cadence: null,
  }
  for (const [k, v] of Object.entries(changes)) {
    base[k] = v
  }

  await sql`
    INSERT INTO atlas.atlas_portfolio_policy (
      portfolio_id,
      cash_floor_pct, respect_regime_cap,
      max_per_stock_pct, max_per_sector_pct, max_small_cap_pct,
      min_holdings, max_positions,
      buy_states, min_within_state_rank, min_rs_rank,
      hard_stop_pct, state_exit_trim, state_exit_full, trailing_stop_pct,
      instrument_universe, benchmark, rebalance_cadence
    ) VALUES (
      ${portfolioId}::uuid,
      ${base.cash_floor_pct}, ${base.respect_regime_cap},
      ${base.max_per_stock_pct}, ${base.max_per_sector_pct}, ${base.max_small_cap_pct},
      ${base.min_holdings}, ${base.max_positions},
      ${base.buy_states}, ${base.min_within_state_rank}, ${base.min_rs_rank},
      ${base.hard_stop_pct}, ${base.state_exit_trim}, ${base.state_exit_full}, ${base.trailing_stop_pct},
      ${base.instrument_universe}, ${base.benchmark}, ${base.rebalance_cadence}
    )
  `
}

// ---------------------------------------------------------------------------
// Build EffectivePolicy response from two DB rows
// ---------------------------------------------------------------------------

type FieldEntry = {
  value: string | string[] | boolean | null
  source: 'inherited' | 'overridden'
}

type EffectivePolicyResponse = Record<string, FieldEntry>

function buildEffectiveResponse(
  house: PolicyRow,
  override: PolicyRow | null,
): EffectivePolicyResponse {
  const result: EffectivePolicyResponse = {}
  for (const field of POLICY_FIELDS) {
    const ov = override?.[field] ?? null
    if (ov !== null && ov !== undefined) {
      result[field] = { value: ov as string | string[] | boolean | null, source: 'overridden' }
    } else {
      result[field] = {
        value: house[field] as string | string[] | boolean | null,
        source: 'inherited',
      }
    }
  }
  return result
}

// ---------------------------------------------------------------------------
// POST /api/policy
// ---------------------------------------------------------------------------

export async function POST(req: NextRequest): Promise<NextResponse> {
  // --- Parse body ---
  let body: Record<string, unknown>
  try {
    body = await req.json()
  } catch {
    return NextResponse.json(
      { error_code: 'bad_request', message: 'Request body must be valid JSON' },
      { status: 400 },
    )
  }

  // --- Validate portfolioId ---
  const { portfolioId, changes } = body
  if (portfolioId !== null && typeof portfolioId !== 'string') {
    return NextResponse.json(
      {
        error_code: 'validation_error',
        message: 'portfolioId must be a string UUID or null (for house default)',
      },
      { status: 400 },
    )
  }

  // --- Validate changes ---
  if (changes === undefined || changes === null || typeof changes !== 'object' || Array.isArray(changes)) {
    return NextResponse.json(
      { error_code: 'validation_error', message: 'changes must be an object' },
      { status: 400 },
    )
  }

  const changesObj = changes as Record<string, unknown>
  // Whitelist all change keys
  for (const key of Object.keys(changesObj)) {
    if (!ALLOWED_FIELD_KEYS.has(key)) {
      return NextResponse.json(
        {
          error_code: 'validation_error',
          message: `Unknown policy field: '${key}'. Allowed: ${[...ALLOWED_FIELD_KEYS].sort().join(', ')}`,
        },
        { status: 400 },
      )
    }
  }

  const validatedChanges = changesObj as Record<string, ChangeValue>

  try {
    // --- Load current effective policy ---
    const houseRow = await loadHouseRow()
    if (!houseRow) {
      return NextResponse.json(
        {
          error_code: 'db_error',
          message:
            'No house-default row found in atlas_portfolio_policy. Run scripts/seed_house_policy.py.',
        },
        { status: 500 },
      )
    }

    let overrideRow: PolicyRow | null = null
    if (typeof portfolioId === 'string') {
      overrideRow = await loadOverrideRow(portfolioId)
    }

    const effectivePolicy = mergeRows(houseRow, overrideRow)

    // --- Short-circuit when nothing changed ---
    if (Object.keys(validatedChanges).length === 0) {
      const responseData = buildEffectiveResponse(houseRow, overrideRow)
      return NextResponse.json({ data: responseData }, { status: 200 })
    }

    // --- Apply changes to candidate for validation ---
    const candidate = applyChanges(effectivePolicy, validatedChanges)

    // --- Validate candidate ---
    const violations = validatePolicy(candidate)
    if (violations.length > 0) {
      return NextResponse.json(
        {
          error_code: 'policy_violation',
          message: violations.join('; '),
        },
        { status: 400 },
      )
    }

    // --- Persist ---
    if (portfolioId === null) {
      await persistHouseChanges(validatedChanges)
    } else {
      await upsertPortfolioOverride(portfolioId, validatedChanges, overrideRow)
    }

    // --- Re-read and return new effective policy ---
    const newHouseRow = await loadHouseRow()
    let newOverrideRow: PolicyRow | null = null
    if (typeof portfolioId === 'string') {
      newOverrideRow = await loadOverrideRow(portfolioId)
    }

    const responseData = buildEffectiveResponse(newHouseRow ?? houseRow, newOverrideRow)
    return NextResponse.json({ data: responseData }, { status: 200 })
  } catch (err) {
    const message = err instanceof Error ? err.message : 'Database error'
    return NextResponse.json({ error_code: 'db_error', message }, { status: 500 })
  }
}
