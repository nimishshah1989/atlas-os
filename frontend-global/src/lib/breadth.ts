// src/lib/breadth.ts — the breadth conditions, named ONCE, so the pulse's counts and the board's
// facets are the same question. "312 above the 200-day" on /pulse must open exactly 312 rows on
// /sp500, and that is only true if both sides read the same column with the same cut.
//
// These are technical_daily's own units (01_prices.sql): `pos_52w` is 0–100, the `above_ema_*`
// flags are booleans that are NULL until the average exists. NEAR_52W_PCT is the pulse's
// definition of "at" a high or low — within two points of the end of the range — a counting
// convention, not a scoring threshold; nothing is ranked or weighted on it.

export const NEAR_52W_PCT = 2

/** The URL keys and values the explorer reads, and the pulse writes into its links. */
export const TREND_KEY = 'trend'
export const TREND = {
  above21: 'above21',
  above50: 'above50',
  above200: 'above200',
  /** The averages themselves in order, 21 > 50 > 200 — the pulse's "averages stacked up". */
  stacked: 'stacked',
} as const

export const POS52_KEY = 'pos52'
export const POS52 = { high: 'high', low: 'low' } as const

/** Relative strength against SPY: `rs` is the 12-month rail the board already had; `rs3` is the
 *  3-month one the pulse counts. Both are `min` rails whose "beating at all" option is '0'. */
export const RS12_KEY = 'rs'
export const RS3_KEY = 'rs3'
export const BEATING = '0'

/** The board address for a breadth row: which market, which condition. */
export function breadthHref(market: '/etfs' | '/sp500', key: string, value: string, extra?: Record<string, string>): string {
  const p = new URLSearchParams({ ...(extra ?? {}), [key]: value })
  return `${market}?${p.toString()}`
}
