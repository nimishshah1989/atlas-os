// Formatting + flagging for the instrument insight panel.
//
// Deliberately introduces NO numeric threshold. "Is this a concern?" is answered only
// from values the engine already produced — the sign of a return, a stored boolean like
// above_ema_200, the engine's own conviction tier, its valuation zone, its risk_flags.
// Inventing a cut-off here (RSI > 70, composite < 40) would put methodology in code,
// which belongs in atlas_thresholds (rule #4), and would present a guess as a signal.

/** Returns and RS are stored as fractions (0.0414 = +4.14pp). Null stays null. */
export function toPp(fraction: number | null | undefined): number | null {
  return fraction == null ? null : fraction * 100
}

/** A 0-100 lens score as a 1-10 decile for the board's DecileMeter glyph. */
export function decileOf(score: number | null | undefined): number | null {
  if (score == null) return null
  return Math.min(10, Math.max(1, Math.floor(score / 10) + 1))
}

/** Tiers the engine itself names as not-yet-convincing. */
const WEAK_TIERS = new Set(['BELOW_THRESHOLD', 'WATCH'])

export function weakTier(tier: string | null | undefined): boolean {
  return tier != null && WEAK_TIERS.has(tier)
}

/** Valuation zones the engine flags as stretched. */
const STRETCHED_ZONES = new Set(['OVERVALUED', 'EXPENSIVE'])

export type Checkable =
  | { kind: 'signed'; value: number | null | undefined }
  | { kind: 'bool'; value: boolean | null | undefined }
  | { kind: 'zone'; value: string | null | undefined }

/**
 * Whether a metric is worth the FM cross-checking before he commits. A missing value
 * is never a concern — it is unknown, and saying otherwise would invent a signal.
 */
export function isConcern(m: Checkable): boolean {
  if (m.value == null) return false
  if (m.kind === 'signed') return m.value < 0
  if (m.kind === 'bool') return m.value === false
  return STRETCHED_ZONES.has(m.value)
}
