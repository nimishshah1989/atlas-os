// src/lib/countries.ts — the country view's SHARED SHAPE: the windows the grid shows and the
// row types, with no I/O and no `server-only`.
//
// It exists because CountryGrid and CountryFundTable are client components (a row has to be
// clickable and a column sortable) and `src/lib/queries/countries.ts` is `server-only` — importing
// a runtime value from it into a client bundle fails the build outright, which is exactly what it
// is there to do. Types alone would erase, but `RS_WINDOWS` is a real array the header maps over.
// So the contract lives here and both sides import it.

/** The relative-strength windows the grid shows, shortest first. */
export const RS_WINDOWS = ['1w', '1m', '3m', '6m', '12m', '24m'] as const
export type RsWindow = (typeof RS_WINDOWS)[number]

export type CountryRow = {
  iso2: string
  name: string
  region: string | null
  /** null when every fund covering this market is geared, inverse or currency-hedged. */
  symbol: string | null
  fund_name: string | null
  adv_usd_60d_median: string | null
  n_etfs: number
  /** The representative fund's composite (0-100), or null where nothing is scored yet. */
  composite: string | null
  /** Percent of this market's SCORED funds at or above the seeded breadth cut. */
  breadth_pct: string | null
  /** 1 (weakest) to 10 (strongest) across every scored market on this date; null when unscored. */
  decile: number | null
  /** 1 = the strongest scored market on this date. Ties share a rank. */
  rank: number | null
  /** How many markets carry a composite at all — the denominator behind `rank`. */
  n_ranked: number
  /** Why the FM's universe rules do not offer the REPRESENTATIVE fund; null when they do. A
   *  market whose only funds sit under his floor still gets a row and a score — the market is
   *  covered — but the grid has to say that the fund standing for it is not one he can buy. */
  exclusion_reason: string | null
  /** Relative strength vs SPY in the ADR-0002 relative form, as a fraction. */
  rs: Record<RsWindow, string | null>
}

export type CountryList = {
  /** The session every row is anchored on, or null when the table is empty. */
  date: string | null
  rows: CountryRow[]
}

/** One fund covering a market, as the detail page ranks it. */
export type CountryFund = {
  instrument_id: string
  symbol: string
  name: string
  /** 1 = the strongest SCORED fund covering this market. Null when the fund carries no score. */
  rank: number | null
  composite: string | null
  /** Cut across this market's scored funds — a fund's standing among its alternatives, which is
   *  a different question from its decile in its global peer group. */
  decile: number | null
  adv_usd_60d_median: string | null
  expense_ratio: string | null
  aum_usd: string | null
  leveraged: boolean | null
  inverse: boolean | null
  hedged: boolean | null
  /** Whether the FM's universe rules OFFER this fund: not geared, not inverse, above his ADV$
   *  floor, with enough observations. A fund can be scored and not offered — measuring a fund is
   *  not the same as putting it forward, and only the offered ones carry a rank. */
  in_universe: boolean
  /** Why the universe leaves it out, straight from `universe_snapshot`; null when it is in. */
  exclusion_reason: string | null
  /** True for the one fund the builder chose to stand for this market. */
  is_representative: boolean
  rs: Record<RsWindow, string | null>
}

export type CountryDetail = {
  row: CountryRow
  funds: CountryFund[]
  date: string
}
