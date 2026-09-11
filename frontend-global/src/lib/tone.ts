// src/lib/tone.ts — ONE conditional-format ramp, for every surface that tints a cell.
//
// WHY THIS FILE EXISTS. Four surfaces were each mixing their own green: `rsTint` in scores.ts,
// `shade` in RankStrip, `fraction` in PulseView, and the bar in BreadthBar. Three of them
// saturated at 100% of `--color-pos`, which puts near-black ink (#131922) on solid #2d8561 — a
// contrast ratio of about 3.9:1, under the 4.5:1 floor for body text, and the "darker than
// required" the FM saw. The DecileChip, written later and checked across its whole ramp, had
// already settled on 30%. So the ceiling was not a matter of taste; three call sites were simply
// wrong and one was right.
//
// TWO RULES.
//
// 1. A TINT NEVER EXCEEDS `CEILING`. The tint is a background for text that is always printed,
//    so it has to stay a background. At 26% over the panel every step of the ramp clears 10:1
//    against `--color-ink`, which is the same discipline the decile chip is held to.
// 2. THE RAMP IS SQUARE-ROOT, NOT LINEAR. Linear spends its whole range on the extremes: a fund
//    beating the index by 2 points got a 10%-of-26% wash nobody can see, while everything past
//    the saturation point looked identical. `sqrt` lifts the small readings into view and
//    compresses the top, where the reader has already got the message.
//
// Colour remains the SECOND channel everywhere (scores.ts rule 3): every tinted cell prints its
// own value, so the board reads in greyscale and in a pasted screenshot.

/** The strongest a text-cell tint may ever be, as a percentage mixed into the surface. */
export const CEILING = 26

/** `color-mix` over a theme token, so a tint follows the palette instead of baking in a colour.
 *  `share` is 0–1 of the way to the ceiling; anything outside is clamped rather than trusted. */
export function tint(token: string, share: number): string {
  const clamped = Number.isFinite(share) ? Math.min(Math.max(share, 0), 1) : 0
  return `color-mix(in srgb, ${token} ${(Math.sqrt(clamped) * CEILING).toFixed(1)}%, transparent)`
}

/** A SIGNED reading against a zero baseline — relative strength, an excess return, a spread.
 *  `full` is the magnitude at which the tint saturates: past it, more is not louder. */
export function signedTint(value: string | number | null | undefined, full: number): string | undefined {
  if (value == null || value === '') return undefined
  const n = Number(value)
  if (!Number.isFinite(n) || !(full > 0)) return undefined
  return tint(n >= 0 ? 'var(--color-pos)' : 'var(--color-neg)', Math.abs(n) / full)
}

/** A SHARE of a population against a baseline — "how many of them are above their 200-day".
 *  Half is bare in both directions; 0 and 1 are the two saturated ends. */
export function shareTint(share: number, baseline = 0.5): string | undefined {
  if (!Number.isFinite(share)) return undefined
  const width = share >= baseline ? 1 - baseline : baseline
  if (!(width > 0)) return undefined
  return tint(share >= baseline ? 'var(--color-pos)' : 'var(--color-neg)', Math.abs(share - baseline) / width)
}

/** A POSITIONAL shade within the population on screen — best to worst of what is drawn, floored
 *  so the weakest row is still a row and not a blank. No absolute band is invented: every
 *  methodology cut lives in atlas_thresholds (rule #1). */
export function rangeTint(
  value: string | number | null | undefined,
  worst: number,
  best: number,
  token = 'var(--color-pos)',
): string | undefined {
  if (value == null || value === '') return undefined
  const n = Number(value)
  if (!Number.isFinite(n)) return undefined
  const width = best - worst
  // A single-valued population has no range to place anything in; everything sits mid-ramp.
  const share = width > 0 ? (n - worst) / width : 0.5
  return tint(token, 0.15 + Math.min(Math.max(share, 0), 1) * 0.85)
}
