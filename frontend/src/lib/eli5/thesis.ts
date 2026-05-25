// frontend/src/lib/eli5/thesis.ts
//
// Pure-function thesis registry — maps (archetype, cap_tier, tenure, direction,
// is_held, features) → ThesisBullets. Zero React imports. Zero async.
//
// Display-label derivation (CONTEXT.md authoritative):
//   POSITIVE + not held → BUY  |  POSITIVE + held → ACCUMULATE
//   NEUTRAL  + not held → WATCH | NEUTRAL  + held → HOLD
//   NEGATIVE + not held → AVOID | NEGATIVE + held → SELL
//
// NOTE: TRIM is NOT used — CONTEXT.md replaced TRIM with SELL.
// Source of truth: docs/v6/design-application.md §4, CONTEXT.md cell-state vocab.

import { ARCHETYPE_TEMPLATES } from './thesis-data'

// ─── Exported types ──────────────────────────────────────────────────────────

export type CellState = 'POSITIVE' | 'NEUTRAL' | 'NEGATIVE'

export type ActionVerb =
  | 'BUY'
  | 'ACCUMULATE'
  | 'HOLD'
  | 'WATCH'
  | 'AVOID'
  | 'SELL'

export type ThesisBullets = {
  action: ActionVerb
  bullets: string[]
}

export type ThesisInput = {
  /** One of the 19 archetype slugs defined in thesis-data.ts */
  archetype: string
  cap_tier: 'Large' | 'Mid' | 'Small'
  tenure: '1m' | '3m' | '6m' | '12m'
  /** POSITIVE or NEGATIVE; NEUTRAL falls back to WATCH/HOLD */
  direction: CellState
  is_held: boolean
  /**
   * Key-value map of feature values for filling in {{placeholders}}.
   * Missing keys render the placeholder as the key name in plain text.
   */
  features: Record<string, string | number | null>
}

// ─── Action-verb derivation ───────────────────────────────────────────────────

/**
 * Derives the display-label action verb from cell state + ownership.
 * CONTEXT.md ownership-aware rendering table:
 *   POSITIVE + not held → BUY  |  POSITIVE + held → ACCUMULATE
 *   NEUTRAL  + not held → WATCH | NEUTRAL  + held → HOLD
 *   NEGATIVE + not held → AVOID | NEGATIVE + held → SELL
 */
export function deriveActionVerb(direction: CellState, is_held: boolean): ActionVerb {
  if (direction === 'POSITIVE') return is_held ? 'ACCUMULATE' : 'BUY'
  if (direction === 'NEUTRAL') return is_held ? 'HOLD' : 'WATCH'
  // NEGATIVE
  return is_held ? 'SELL' : 'AVOID'
}

// ─── Placeholder resolver ─────────────────────────────────────────────────────

/**
 * Resolves {{placeholder}} tokens in a template string.
 * Built-in keys: archetype, cap_tier, tenure.
 * Additional values come from input.features.
 * Missing keys are left as their key name (no crash).
 */
function resolvePlaceholders(
  template: string,
  input: ThesisInput,
): string {
  const builtins: Record<string, string | number | null> = {
    cap_tier: input.cap_tier,
    tenure: input.tenure,
    archetype: input.archetype,
    // Common feature defaults
    sector_name: 'this sector',
    sector_rank: '—',
    sector_breadth_pos: '—',
    vs_cohort_pp: '—',
    vs_nifty500_pp: '—',
    vs_nifty50_pp: '—',
    vs_gold_pp: '—',
    vol_60d_vs_avg: '1.0',
    vol_z: '—',
    ic: '—',
    fric_adj_excess: '—',
    hit_rate_pct: '—',
    dd_pct: '—',
    rsi: '—',
    dist_sma200_pct: '—',
    n_day: '52',
  }

  const merged: Record<string, string | number | null> = { ...builtins, ...input.features }

  return template.replace(/\{\{(\w+)\}\}/g, (_match, key: string) => {
    const val = merged[key]
    if (val === null || val === undefined) return key
    return String(val)
  })
}

// ─── Main export ─────────────────────────────────────────────────────────────

/**
 * Generates thesis bullets for the given archetype + context.
 *
 * @throws {Error} if the archetype slug is not recognised.
 */
export function generateThesis(input: ThesisInput): ThesisBullets {
  const template = ARCHETYPE_TEMPLATES[input.archetype]
  if (!template) {
    throw new Error(
      `[thesis] Unknown archetype: "${input.archetype}". ` +
      `Valid archetypes: ${Object.keys(ARCHETYPE_TEMPLATES).join(', ')}`,
    )
  }

  const action = deriveActionVerb(input.direction, input.is_held)

  // For NEUTRAL direction we fallback to positive bullets when available,
  // otherwise negative. NEUTRAL is the residual state (no dedicated template).
  let rawBullets: string[]
  if (input.direction === 'POSITIVE') {
    rawBullets = template.positive ?? template.negative ?? []
  } else if (input.direction === 'NEGATIVE') {
    rawBullets = template.negative ?? template.positive ?? []
  } else {
    // NEUTRAL — watch/hold: prefer positive (no strong signal either way)
    rawBullets = template.positive ?? template.negative ?? []
  }

  if (rawBullets.length === 0) {
    throw new Error(
      `[thesis] Archetype "${input.archetype}" has no bullet templates for direction "${input.direction}".`,
    )
  }

  const bullets = rawBullets.map((t) => resolvePlaceholders(t, input))

  return { action, bullets }
}

// ─── List helpers ─────────────────────────────────────────────────────────────

/** Returns all 19 registered archetype slugs. */
export function listArchetypeSlugs(): string[] {
  return Object.keys(ARCHETYPE_TEMPLATES)
}

/** Returns true if the archetype slug is registered. */
export function isKnownArchetype(slug: string): boolean {
  return slug in ARCHETYPE_TEMPLATES
}
