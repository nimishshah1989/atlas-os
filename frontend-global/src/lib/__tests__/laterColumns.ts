// Not a test file (vitest collects `src/**/*.test.{ts,tsx}` only) — the one place recording which
// InstrumentDbRow columns were added AFTER the fixtures in this directory were captured.
//
// WHY THIS EXISTS. Every fixture here is a REAL row read out of a real database on a stated date
// (rule #0). When a column is added to the query, those captures cannot grow a real value for it:
// nobody re-ran that database. So the honest entry is null WITH A REASON, and the reason belongs
// in one file rather than pasted into five where it will drift.
//
// NULL HERE MEANS "NOT CAPTURED". It does not mean zero, it does not mean false, and it does not
// mean the producer found nothing — several of these columns certainly DO carry values in the
// databases these rows came from. A test that needs a real value for one of them must capture it,
// not spread this in; a test that spreads this in must not assert on these columns.
export const NOT_CAPTURED = {
  /** The theme's taxonomy id. This one is genuinely null wherever `theme` is: every fixture fund
   *  in this directory is a broad-market, factor, dividend or bond fund whose name states no
   *  theme, verified by running classify_theme over each name. */
  theme_id: null,
  // The rest of the blend, beyond `technical`.
  risk: null,
  cost_liquidity: null,
  flow: null,
  quality: null,
  fundamental: null,
  valuation: null,
  catalyst: null,
  // technical_daily's three trend flags and etf_meta's two cost facts.
  above_ema_21: null,
  above_ema_50: null,
  above_ema_200: null,
  emas_stacked: null,
  expense_ratio: null,
  aum_usd: null,
} as const
