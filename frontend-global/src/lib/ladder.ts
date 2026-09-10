// src/lib/ladder.ts — the adapter, in the shape of India's frontend/src/components/adapters/:
// a ScoreDetail row → the DecileLadder's model, and nothing else. Pure — no React, no database.
//
// RULE #0. Nothing is computed here that the scorer did not already write. Every value traces to
// a column of `lens_scores_daily` / `etf_scores_daily` or to that row's own evidence JSONB; an
// absent column comes out as null and is rendered as words, never as a zero.
//
// THE PER-LENS DECILE IS CUT ON READ, not stored — `<lens>_decile` on the score row, an ntile(10)
// inside the same cohort the composite's decile is cut in (src/lib/queries/scores.ts), which is
// exactly how India's `getStockDecile` produces the deciles its own ladder shows. So the number is
// as real as the composite's: a statement about a population on one date, computed from the
// journal, never materialised. A lens the scorer could not compute has no decile at all — an empty
// track and the words, never a low one (rule #0).
import type { LadderLens, LadderNumber } from '@/components/ui/DecileLadder'
import type { AssetClass } from '@/lib/facts'
import { formatNum } from '@/lib/format'
import type { ScoreDetail } from '@/lib/queries/scores'
import { lensLabel, lensSubs, subLabel, type LensWeight } from '@/lib/scores'

/** A lens is out of 100; a sub-score is out of 25, because a lens is the mean of its PRESENT subs
 *  × 4 (atlas/global_market/scoring/etf_lenses._lens, stock_lenses likewise, and the "subs (0–25)"
 *  comments in ddl/05_scores.sql). Printing the denominator is what stops one being read as the
 *  other — the units the ladder's "actual numbers" carry. */
export const SUB_MAX = 25

/** NUMERIC arrives as text; an empty string is postgres's null through the same door. */
const score = (v: string | null | undefined): number | null =>
  v == null || v === '' ? null : Number(v)

/** A decile is an integer 1-10 or nothing. Anything else — a 0 from a bad cut, a value off the
 *  scale — is refused rather than clamped, because a clamped decile is a claim nobody computed. */
function decileOf(n: number | null | undefined): number | null {
  if (n == null || !Number.isInteger(n) || n < 1 || n > 10) return null
  return n
}

/** Widest weight first, the query's own `ORDER BY threshold_value DESC, threshold_key`, repeated
 *  here so the ladder reads "this is what the score is mostly made of" whoever hands it the list. */
const byWeight = (a: LensWeight, b: LensWeight) => b.weight - a.weight || a.key.localeCompare(b.key)

/** The sub-scores of one lens, as the actual numbers WITH THEIR UNIT. A sub the scorer could not
 *  compute is null here and the ladder says so in words. */
function numbersFor(
  assetClass: AssetClass,
  lens: string,
  values: Record<string, string | null>,
): LadderNumber[] {
  return lensSubs(assetClass, lens).map((sub) => {
    const n = score(values[sub])
    return { label: subLabel(sub), value: n == null ? null : `${formatNum(n, 1)} / ${SUB_MAX}` }
  })
}

/** The trail the scorer wrote for one lens. Both writers key it by lens name at the top level of
 *  the evidence JSONB (scripts/global_market/score_etfs.py, score_stocks.py) and each lens's own
 *  entry is a flat map of what an input said — `rs_3m: "strong"`, `reason: "no sub-score had
 *  inputs"`. Only the STRING entries are the scorer's words; counts belong to the numbers above.
 *  Nothing is rephrased and nothing is added. */
function evidenceFor(evidence: unknown, lens: string): string[] {
  if (!evidence || typeof evidence !== 'object') return []
  const entry = (evidence as Record<string, unknown>)[lens]
  if (!entry || typeof entry !== 'object' || Array.isArray(entry)) return []
  return Object.entries(entry as Record<string, unknown>)
    .filter(([, v]) => typeof v === 'string' && v.trim() !== '')
    .slice(0, 4)
    .map(([k, v]) => `${k.replace(/_/g, ' ')}: ${(v as string).trim()}`)
}

/** One row per lens the weight table carries, widest weight first: the lens score the scorer
 *  wrote, its sub-scores as the actual numbers, the weight in force, and the evidence trail. A
 *  lens with no producer keeps its row — an empty track and the words, so a reader sees WHICH
 *  lenses have not been measured rather than a score that quietly omits them. */
export function scoreToLadder(assetClass: AssetClass, s: ScoreDetail): LadderLens[] {
  return [...s.lenses].sort(byWeight).map((l) => ({
    key: l.key,
    label: lensLabel(l.key),
    score: score(s.values[l.key]),
    // `<lens>_decile` arrives beside the lens itself. Null where that lens has no score, and null
    // for every lens on a fund whose asset class is too small to rank at all.
    decile: decileOf(s.deciles[l.key]),
    weight: l.weight,
    numbers: numbersFor(assetClass, l.key, s.values),
    evidence: evidenceFor(s.evidence, l.key),
  }))
}

/** The row to open on arrival: the strongest scored lens, so the actual numbers are on the screen
 *  before anyone clicks. Ties go to the heavier weight, which is the order above. Null when no
 *  lens is scored — nothing is opened rather than opening an empty one. */
export function topLens(lenses: LadderLens[]): string | undefined {
  let best: LadderLens | undefined
  for (const l of lenses) if (l.score != null && (best == null || l.score > best.score!)) best = l
  return best?.key
}
