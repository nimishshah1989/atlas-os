// src/lib/universe.ts — why a fund the board measured is not one the board offers.
//
// MEASURED IS NOT OFFERED. score_etfs.py grades nearly every classified fund, on the FM's own
// instruction ("we should score all the funds… coverage close to 100%"), so a composite means
// only that we looked. `universe_snapshot.in_universe` is the separate question — may this fund
// be ranked, put at the top of a theme, or seeded into a basket — and `exclusion_reason` is the
// single rule that answered no.
//
// The strings are the producer's, written by scripts/global_market/build_universe_snapshot.py.
// An unknown one renders verbatim rather than as "other": a reason the board cannot name is a
// reason the reader should still see, and it is how a new rule announces itself.

const REASONS: Record<string, string> = {
  below_floor: 'below the liquidity floor',
  leveraged: 'geared',
  inverse: 'inverse',
  too_few_observations: 'too little history',
  no_bars: 'no price history',
  stale: 'prices stale',
}

/** The exclusion in the reader's words, or null when the fund is offered. */
export function whyNotOffered(reason: string | null | undefined): string | null {
  if (!reason) return null
  return REASONS[reason] ?? reason.replace(/_/g, ' ')
}
