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

export type StackLink = { label: string; up: boolean }
export type EmaStack = {
  links: StackLink[]
  /** aligned-up = price > 21 > 50 > 200, the FM's buy alignment; null when data is short. */
  verdict: 'aligned-up' | 'aligned-down' | 'mixed' | null
}

/**
 * The price-to-moving-average stack, as a chain of inequalities.
 *
 * The FM's rule (2026-07-30): price > EMA21 > EMA50 > EMA200 reads long, the exact
 * reverse reads short, anything else is mixed. This is his stated methodology, not a
 * threshold invented here — and each link is reported separately so a broken chain shows
 * WHERE it broke rather than collapsing to one verdict.
 */
export function emaStack(
  close: number | null | undefined,
  ema21: number | null | undefined,
  ema50: number | null | undefined,
  ema200: number | null | undefined,
): EmaStack {
  if (close == null || ema21 == null || ema50 == null || ema200 == null) {
    return { links: [], verdict: null }
  }
  const links: StackLink[] = [
    { label: 'Price/21', up: close > ema21 },
    { label: '21/50', up: ema21 > ema50 },
    { label: '50/200', up: ema50 > ema200 },
  ]
  const ups = links.filter((l) => l.up).length
  return {
    links,
    verdict: ups === links.length ? 'aligned-up' : ups === 0 ? 'aligned-down' : 'mixed',
  }
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
