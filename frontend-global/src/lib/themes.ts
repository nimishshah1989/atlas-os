// src/lib/themes.ts — the theme view's SHARED SHAPE. No I/O, no `server-only`: the grid and the
// fund table are client components (rows navigate, headers sort) and the query module is not.

import type { SectorPoint } from './sectors'

export type { SectorPoint }

/** The relative-strength windows a theme is summarised over, shortest first. */
export const THEME_WINDOWS = ['3m', '6m', '12m'] as const
export type ThemeWindow = (typeof THEME_WINDOWS)[number]

export type ThemeRow = {
  id: string
  name: string
  /** The level-1 sector the theme hangs under — "Artificial Intelligence" under Information
   *  Technology — so a reader can see that two themes are neighbours. */
  sector_id: string | null
  sector_name: string | null
  /** Every classified fund carrying this theme, whether or not it is scored. */
  n_funds: number
  /** How many of them the scorer MEASURED. Coverage, not a population. */
  n_scored: number
  /** How many of those the FM's universe rules OFFER — the population every median, the
   *  ranking and the headline fund on this theme are cut over. A fund can be measured and not
   *  offered; only the offered ones answer "which fund do I buy". */
  n_offered: number
  /** How many carry a score that is COMPARABLE with the others — everything the scorer graded
   *  except the geared and inverse, whose returns are a multiple or a negation of the thing. This
   *  is the population behind the median, the relative strengths and the breadth. */
  n_comparable: number
  aum_usd: string | null
  /** The MEDIAN member composite. Median, not mean: a theme with one giant fund and nine tiny
   *  ones should not read as the giant. */
  median_composite: string | null
  /** Share of scored members trading above their own 200-day EMA, 0–1. Atlas India's sector
   *  breadth measure, and the one that needs no threshold to state. */
  above_ema200_frac: string | null
  /** The strongest scored fund in the theme. */
  top_symbol: string | null
  top_name: string | null
  top_composite: string | null
  top_decile: number | null
  /** Median member relative strength vs SPY, in the ADR-0002 relative form. */
  rs: Record<ThemeWindow, string | null>
}

export type ThemeList = { date: string | null; rows: ThemeRow[] }

/** One fund inside a theme, ranked against the others that carry it. */
export type ThemeFund = {
  instrument_id: string
  symbol: string
  name: string
  /** 1 = the strongest SCORED fund in this theme. Null when the fund carries no score. */
  rank: number | null
  composite: string | null
  /** Cut across this THEME's scored funds — which fund to buy for the theme, not whether the
   *  theme is worth buying. Two questions, two populations. */
  decile: number | null
  technical: string | null
  risk: string | null
  cost_liquidity: string | null
  adv_usd_60d_median: string | null
  expense_ratio: string | null
  aum_usd: string | null
  leveraged: boolean | null
  inverse: boolean | null
  hedged: boolean | null
  role_id: string | null
  /** Whether the FM's universe rules OFFER this fund. Only the offered carry a rank. */
  in_universe: boolean
  /** Which rule leaves it out, from `universe_snapshot`; null when it is in. */
  exclusion_reason: string | null
  rs: Record<ThemeWindow, string | null>
}

export type ThemeDetail = {
  row: ThemeRow
  funds: ThemeFund[]
  date: string
  /** Three years of the theme's own median-member line, and SPY on the same axes. Empty where the
   *  theme's funds are too young to have a common base session. Shares its shape and its query
   *  with the sector line — see `queries/sectors.ts:medianMemberHistory`. */
  history: SectorPoint[]
}
