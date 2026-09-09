// src/lib/queries/countries.ts — the country view: one tradeable fund per market.
// Reads ONLY atlas_global (the schema gate scans this directory): country, country_daily,
// instrument_master, technical_daily. Cached under the `eod` tag so the nightly publish flushes it.
//
// The rows are built by scripts/global_market/build_country_views.py, which picks the
// representative as the MOST-TRADED eligible fund — geared, inverse and currency-hedged funds
// count toward n_etfs but cannot represent a market. That decision lives in the builder, not
// here: this file reads what the nightly decided and never re-decides it, so the page and the
// journal can never disagree about which fund is Japan's.
//
// RANK AND DECILE ARE CUT HERE, ON READ, and deliberately not stored — the same rule India
// applies within cap cohort (scripts/foundation/decile_core.py: "read-only, nothing
// materialised here"). A rank is a statement about a population on one date; materialising it
// would let a market's rank go stale while its score moved. Both are cut over the SCORED
// markets only: a market with no composite has no rank, rather than being placed last, which
// would read as "measured, and worst".
import 'server-only'
import { eodCached } from '@/lib/cache'
import { db, dbAvailable } from '@/lib/db'

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
  /** Relative strength vs SPY in the ADR-0002 relative form, as a fraction. */
  rs: Record<RsWindow, string | null>
}

export type CountryList = {
  /** The session every row is anchored on, or null when the table is empty. */
  date: string | null
  rows: CountryRow[]
}

type DbRow = {
  iso2: string
  name: string
  region: string | null
  date: string
  symbol: string | null
  fund_name: string | null
  adv_usd_60d_median: string | null
  n_etfs: number | null
  composite: string | null
  breadth_pct: string | null
  decile: number | null
  rank: number | null
  n_ranked: number | null
} & Record<`rs_${RsWindow}_spy`, string | null>

const EMPTY: CountryList = { date: null, rows: [] }

// The newest session country_daily holds, and every row on it. One date for the whole grid, so
// a market whose builder run lagged cannot sit beside today's and read as today's.
const listInner = eodCached(async (): Promise<CountryList> => {
  const rows = await db()<DbRow[]>`
    WITH anchor AS (SELECT MAX(date) AS d FROM atlas_global.country_daily),
    -- Ranked over the SCORED markets alone. A market with no composite is not "last": it is
    -- not in this CTE at all, so the LEFT JOIN below leaves its rank and decile null.
    ranked AS (
      SELECT d.iso2,
             NTILE(10) OVER (ORDER BY d.composite)      AS decile,
             RANK()    OVER (ORDER BY d.composite DESC) AS rank,
             COUNT(*)  OVER ()                          AS n_ranked
      FROM atlas_global.country_daily d
      JOIN anchor a ON d.date = a.d
      WHERE d.composite IS NOT NULL
    )
    SELECT c.iso2, c.name, c.region, d.date::text AS date,
           m.symbol, m.name AS fund_name,
           t.adv_usd_60d_median::text AS adv_usd_60d_median,
           d.n_etfs,
           d.composite::text   AS composite,
           d.breadth_pct::text AS breadth_pct,
           r.decile, r.rank, r.n_ranked,
           d.rs_1w_spy::text, d.rs_1m_spy::text, d.rs_3m_spy::text,
           d.rs_6m_spy::text, d.rs_12m_spy::text, d.rs_24m_spy::text
    FROM atlas_global.country_daily d
    JOIN anchor a ON d.date = a.d
    JOIN atlas_global.country c USING (iso2)
    LEFT JOIN ranked r USING (iso2)
    LEFT JOIN atlas_global.instrument_master m ON m.instrument_id = d.representative_id
    LEFT JOIN atlas_global.technical_daily t
           ON t.instrument_id = d.representative_id AND t.date = d.date
    ORDER BY c.region NULLS LAST, c.name
  `
  if (rows.length === 0) return EMPTY
  return {
    date: rows[0].date,
    rows: rows.map((r) => ({
      iso2: r.iso2,
      name: r.name,
      region: r.region,
      symbol: r.symbol,
      fund_name: r.fund_name,
      adv_usd_60d_median: r.adv_usd_60d_median,
      n_etfs: r.n_etfs ?? 0,
      composite: r.composite,
      breadth_pct: r.breadth_pct,
      decile: r.decile,
      rank: r.rank,
      n_ranked: r.n_ranked ?? 0,
      rs: Object.fromEntries(RS_WINDOWS.map((w) => [w, r[`rs_${w}_spy`]])) as CountryRow['rs'],
    })),
  }
}, 'countries')

/** Every country with a US-listed fund, on the latest session the builder wrote. */
export async function getCountries(): Promise<CountryList> {
  if (!dbAvailable) return EMPTY
  return listInner()
}
