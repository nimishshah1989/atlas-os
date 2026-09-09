// src/lib/queries/holdings.ts — what a fund HOLDS and what it is WORTH, from its own SEC filing.
// Reads ONLY atlas_global (the schema gate scans this directory): etf_meta, etf_exposure_daily,
// etf_holdings, instrument_master. Cached under the `eod` tag so the nightly publish flushes it.
//
// THE SNAPSHOT IS TWO MONTHS OLD AND THE PAGE SAYS SO. Form N-PORT-P is public for the third
// month of each filer's FISCAL quarter and appears about sixty days later, so `as_of` is never
// today and must never be shown as if it were. Every figure here carries that date.
//
// AUM IS THE SERIES', AND FOR A MULTI-CLASS SERIES THAT IS NOT THE ETF'S. One filing covers one
// series, and a series can have several share classes — VOO is one of four in a fund whose filed
// net assets are the whole thing. So `aum_usd` is filled by the ingest only where the series has
// ONE class; `series_net_assets_usd` and `series_class_count` are carried beside it so the card
// can say "this is the fund's, not this share class's" instead of showing a wrong number.
import 'server-only'
import { eodCached } from '@/lib/cache'
import { db, dbAvailable } from '@/lib/db'

/** How many holdings the card lists. The rest are counted, never hidden silently. */
export const TOP_HOLDINGS = 15

export type FundMeta = {
  /** The ETF's own AUM — null where the series has several share classes. */
  aum_usd: string | null
  aum_as_of: string | null
  aum_source: string | null
  /** The filed net assets of the whole SERIES, whatever its class count. */
  series_net_assets_usd: string | null
  series_class_count: number | null
  /** Share of net assets marked in derivatives, and share of net assets in their NOTIONAL. */
  derivatives_share: string | null
  derivative_notional_share: string | null
  source: string | null
}

export type Weighted = { key: string; weight: string }

export type FundExposure = {
  as_of_date: string
  n_holdings: number
  sum_abs_weight: string | null
  top_country: string | null
  top_country_w: string | null
  equity_w: string | null
  top10_w: string | null
  hhi: string | null
  lookthrough_scored_w: string | null
  holdings_source: string | null
  country: Weighted[]
  sector: Weighted[]
  asset: Weighted[]
}

export type Holding = {
  holding_key: string
  name: string | null
  ticker: string | null
  cusip: string | null
  weight_frac: string | null
  market_value_usd: string | null
  country_iso2: string | null
  asset_category: string | null
  derivative_category: string | null
  /** Set when the holding resolved to a scored S&P 500 instrument. */
  held_symbol: string | null
}

export type FundHoldings = {
  meta: FundMeta | null
  exposure: FundExposure | null
  holdings: Holding[]
}

const EMPTY: FundHoldings = { meta: null, exposure: null, holdings: [] }

/** A jsonb vector of weight strings → the entries, heaviest first. */
function vector(raw: unknown): Weighted[] {
  if (!raw || typeof raw !== 'object') return []
  return Object.entries(raw as Record<string, string>)
    .map(([key, weight]) => ({ key, weight: String(weight) }))
    .sort((a, b) => Number(b.weight) - Number(a.weight))
}

const inner = eodCached(async (symbol: string): Promise<FundHoldings> => {
  const [meta] = await db()<FundMeta[]>`
    SELECT m.aum_usd::text, m.aum_as_of::text, m.aum_source,
           m.series_net_assets_usd::text, m.series_class_count,
           m.derivatives_share::text, m.derivative_notional_share::text, m.source
    FROM atlas_global.etf_meta m
    JOIN atlas_global.instrument_master im USING (instrument_id)
    WHERE im.symbol = ${symbol} AND im.is_active
  `
  // The LATEST snapshot, and only that one: exposures are keyed by the holdings' date, and a
  // fund accumulates one per quarter.
  const [exposure] = await db()<(FundExposure & { country_vec: unknown })[]>`
    SELECT e.as_of_date::text, e.n_holdings, e.sum_abs_weight::text,
           e.top_country, e.top_country_w::text, e.equity_w::text, e.top10_w::text,
           e.hhi::text, e.lookthrough_scored_w::text, e.holdings_source,
           e.country_vec, e.sector_vec, e.asset_vec
    FROM atlas_global.etf_exposure_daily e
    JOIN atlas_global.instrument_master im USING (instrument_id)
    WHERE im.symbol = ${symbol} AND im.is_active
    ORDER BY e.as_of_date DESC
    LIMIT 1
  `
  const holdings = exposure
    ? await db()<Holding[]>`
        SELECT h.holding_key, h.holding_name AS name, h.holding_ticker AS ticker, h.cusip,
               h.weight_frac::text, h.market_value_usd::text, h.country_iso2,
               h.asset_category, h.derivative_category,
               held.symbol AS held_symbol
        FROM atlas_global.etf_holdings h
        JOIN atlas_global.instrument_master im ON im.instrument_id = h.instrument_id
        LEFT JOIN atlas_global.instrument_master held
               ON held.instrument_id = h.holding_instrument_id
        WHERE im.symbol = ${symbol} AND im.is_active
          AND h.as_of_date = ${exposure.as_of_date}::date
        ORDER BY ABS(COALESCE(h.weight_frac, 0)) DESC
        LIMIT ${TOP_HOLDINGS}
      `
    : []

  const raw = exposure as unknown as Record<string, unknown> | undefined
  return {
    meta: meta ?? null,
    exposure: exposure
      ? {
          ...exposure,
          country: vector(raw?.country_vec),
          sector: vector(raw?.sector_vec),
          asset: vector(raw?.asset_vec),
        }
      : null,
    holdings,
  }
}, 'fund-holdings')

/** One fund's N-PORT facts, exposures and largest positions — empty until the feed has run. */
export async function getFundHoldings(symbol: string): Promise<FundHoldings> {
  if (!dbAvailable) return EMPTY
  return inner(symbol)
}
