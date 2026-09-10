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
//
// AND ON THE FUND TABLE, OVER THE OFFERED ONES. A rank on this page answers "which fund do I buy
// to own this market", so its population is `universe_snapshot.in_universe` — the FM's own rules
// about what may be bought. Everything scored keeps its composite and is listed; only what is
// offered is ranked.
//
// THE SHAPES ARE NOT DECLARED HERE. `src/lib/countries.ts` holds them, because the grid and the
// fund table are client components and this module is `server-only`: a client bundle that reached
// for RS_WINDOWS through this file would fail the build, which is the whole point of the marker.
import 'server-only'
import { eodCached } from '@/lib/cache'
import type {
  CountryDetail,
  CountryFund,
  CountryList,
  CountryRow,
  RsWindow,
} from '@/lib/countries'
import { RS_WINDOWS } from '@/lib/countries'
import { db, dbAvailable } from '@/lib/db'

export type { CountryDetail, CountryFund, CountryList, CountryRow, RsWindow }
export { RS_WINDOWS }

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
  exclusion_reason: string | null
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
           -- Whether the fund standing for this market is one the FM can actually buy. Seven
           -- markets — Belgium, Denmark, Finland, Ireland, Kuwait, Norway, Qatar — are covered
           -- only by funds under his floor, and the grid said nothing about it.
           un.exclusion_reason,
           d.rs_1w_spy::text, d.rs_1m_spy::text, d.rs_3m_spy::text,
           d.rs_6m_spy::text, d.rs_12m_spy::text, d.rs_24m_spy::text
    FROM atlas_global.country_daily d
    JOIN anchor a ON d.date = a.d
    JOIN atlas_global.country c USING (iso2)
    LEFT JOIN ranked r USING (iso2)
    LEFT JOIN atlas_global.instrument_master m ON m.instrument_id = d.representative_id
    LEFT JOIN atlas_global.technical_daily t
           ON t.instrument_id = d.representative_id AND t.date = d.date
    LEFT JOIN atlas_global.universe_snapshot un
           ON un.instrument_id = d.representative_id
          AND un.date = (SELECT max(date) FROM atlas_global.universe_snapshot)
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
      exclusion_reason: r.exclusion_reason,
      rs: Object.fromEntries(RS_WINDOWS.map((w) => [w, r[`rs_${w}_spy`]])) as CountryRow['rs'],
    })),
  }
}, 'countries')

/** Every country with a US-listed fund, on the latest session the builder wrote. */
export async function getCountries(): Promise<CountryList> {
  if (!dbAvailable) return EMPTY
  return listInner()
}

// ── one market ───────────────────────────────────────────────────────────────────────────────

// Membership is the CLASSIFIER's, read back rather than recomputed: classify_etfs.py writes the
// country its name names into `etf_classification.country_codes`, and build_country_views.py used
// the same function to build the grid. Deciding it a third time in SQL is how a page and its
// journal start disagreeing about which funds are Japan's.
const detailInner = eodCached(async (iso2: string): Promise<CountryDetail | null> => {
  const list = await listInner()
  const row = list.rows.find((r) => r.iso2 === iso2.toUpperCase())
  if (!row || !list.date) return null

  const funds = await db()<
    ({
      instrument_id: string
      symbol: string
      name: string
      rank: number | null
      composite: string | null
      decile: number | null
      adv_usd_60d_median: string | null
      expense_ratio: string | null
      aum_usd: string | null
      leveraged: boolean | null
      inverse: boolean | null
      hedged: boolean | null
      in_universe: boolean | null
      exclusion_reason: string | null
      is_representative: boolean
    } & Record<`rs_${RsWindow}_spy`, string | null>)[]
  >`
    WITH current AS (
      SELECT c.instrument_id, c.leveraged, c.inverse, c.hedged
      FROM atlas_global.etf_classification c
      WHERE c.valid_to IS NULL
        AND c.status IN ('auto', 'confirmed', 'override')
        AND c.country_codes[1] = ${iso2.toUpperCase()}
    ),
    -- MEASURED IS NOT OFFERED, and this CTE is the line between them. score_etfs.py grades every
    -- fund the FM asked it to ("we should score all the funds… coverage close to 100%"), which is
    -- right — but a score is a measurement, not an offer. universe_snapshot already carries the
    -- FM's three rules about what may be OFFERED: not geared, not inverse, and above his ADV$
    -- floor with enough observations to mean it.
    universe AS (
      SELECT instrument_id, coalesce(in_universe, false) AS in_universe, exclusion_reason
      FROM atlas_global.universe_snapshot
      WHERE date = (SELECT max(date) FROM atlas_global.universe_snapshot)
    ),
    graded AS (
      SELECT s.instrument_id, s.composite
      FROM atlas_global.etf_scores_daily s
      JOIN current c ON c.instrument_id = s.instrument_id
      WHERE s.date = ${list.date}::date AND s.composite IS NOT NULL
    ),
    scored AS (
      SELECT g.instrument_id,
             RANK()    OVER (ORDER BY g.composite DESC) AS rank,
             NTILE(10) OVER (ORDER BY g.composite)      AS decile
      FROM graded g
      JOIN universe u ON u.instrument_id = g.instrument_id AND u.in_universe
    )
    -- The COMPOSITE comes from the score table and the RANK from the CTE above, deliberately.
    -- A fund the universe does not offer keeps the number the scorer measured — hiding it would
    -- claim we never looked — and simply has no place in the ranking.
    SELECT im.instrument_id::text AS instrument_id, im.symbol, im.name,
           sc.rank, sd.composite::text AS composite, sc.decile,
           t.adv_usd_60d_median::text  AS adv_usd_60d_median,
           em.expense_ratio::text      AS expense_ratio,
           em.aum_usd::text            AS aum_usd,
           cur.leveraged, cur.inverse, cur.hedged,
           coalesce(un.in_universe, false) AS in_universe, un.exclusion_reason,
           (d.representative_id = im.instrument_id) AS is_representative,
           t.rs_1w_spy::text, t.rs_1m_spy::text, t.rs_3m_spy::text,
           t.rs_6m_spy::text, t.rs_12m_spy::text, t.rs_24m_spy::text
    FROM current cur
    JOIN atlas_global.instrument_master im USING (instrument_id)
    LEFT JOIN universe un ON un.instrument_id = im.instrument_id
    LEFT JOIN atlas_global.technical_daily t
           ON t.instrument_id = im.instrument_id AND t.date = ${list.date}::date
    LEFT JOIN atlas_global.etf_meta em ON em.instrument_id = im.instrument_id
    LEFT JOIN graded sd ON sd.instrument_id = im.instrument_id
    LEFT JOIN scored sc ON sc.instrument_id = im.instrument_id
    LEFT JOIN atlas_global.country_daily d
           ON d.iso2 = ${iso2.toUpperCase()} AND d.date = ${list.date}::date
    WHERE im.is_active
    -- Ranked funds first, strongest down; then everything the universe does not offer, most
    -- traded first. An unranked fund is not a weak one — it is geared, inverse, or below the FM's
    -- floor — and exclusion_reason says which, on the row itself.
    ORDER BY sc.rank NULLS LAST, t.adv_usd_60d_median DESC NULLS LAST
  `

  return {
    row,
    date: list.date,
    funds: funds.map((f) => ({
      instrument_id: f.instrument_id,
      symbol: f.symbol,
      name: f.name,
      rank: f.rank,
      composite: f.composite,
      decile: f.decile,
      adv_usd_60d_median: f.adv_usd_60d_median,
      expense_ratio: f.expense_ratio,
      aum_usd: f.aum_usd,
      leveraged: f.leveraged,
      inverse: f.inverse,
      hedged: f.hedged,
      in_universe: f.in_universe ?? false,
      exclusion_reason: f.exclusion_reason,
      is_representative: f.is_representative ?? false,
      rs: Object.fromEntries(RS_WINDOWS.map((w) => [w, f[`rs_${w}_spy`]])) as CountryFund['rs'],
    })),
  }
}, 'country')

/** One market: its grid row, and every US-listed fund that covers it, ranked. */
export async function getCountry(iso2: string): Promise<CountryDetail | null> {
  if (!dbAvailable) return null
  return detailInner(iso2)
}
