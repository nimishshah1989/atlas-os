// src/lib/queries/pulse.ts — BREADTH: how many instruments are doing the thing, not what the
// index did. Reads ONLY atlas_global (the schema gate scans this directory): technical_daily,
// universe_snapshot, instrument_master, lens_scores_daily, etf_scores_daily, macro_daily.
// Cached under the `eod` tag so the nightly publish flushes it.
//
// WHY BREADTH IS A DIFFERENT QUESTION FROM THE INDEX. The S&P 500 is capitalisation-weighted, so
// seven companies can carry it while four hundred fall. "SPY is up 1 percent" and "62 percent of
// the index is above its 200-day average" are not two ways of saying one thing; the second is the
// one that says whether a rally is worth joining. This is the same read India's market-pulse
// breadth charts give, over the instruments this board actually scores.
//
// COUNTED OVER THE UNIVERSE, NOT THE DIRECTORY. Breadth over 13,166 listed instruments would be a
// statement about the ETF industry's long tail. Every count below is inside `universe_snapshot`'s
// own cut — current S&P 500 members for stocks, liquid unleveraged funds for ETFs — so the
// denominator is the population the board ranks.
//
// A MISSING MEASURE IS NOT A "NO". `above_ema_200` is null until an instrument has 200 sessions,
// and a young fund has not failed a test nobody could run on it. Every row therefore carries its
// own denominator (`measured`) beside the count, and the page prints the share of what was
// MEASURED — never of what was listed (rule #0).
import 'server-only'
import { eodCached } from '@/lib/cache'
import { db, dbAvailable } from '@/lib/db'
import type { AssetClass } from '@/lib/facts'
import { NEAR_52W_PCT } from '@/lib/breadth'
import { ANCHOR, type Anchor } from './instruments'

/** One population's breadth on one date. `measured` is the denominator every share is over. */
export type Breadth = {
  asset_class: AssetClass
  /** Rows in the universe with a technical row at all. */
  members: number
  measured_ema200: number
  above_ema200: number
  measured_ema50: number
  above_ema50: number
  /** 21 > 50 > 200 — the full uptrend stack. */
  measured_stack: number
  stacked_up: number
  /** Within 2 percent of the 52-week high, and within 2 percent of the low. */
  measured_52w: number
  near_high: number
  near_low: number
  /** Beating SPY over 3 and 12 months, in the relative form. */
  measured_rs_3m: number
  beating_3m: number
  measured_rs_12m: number
  beating_12m: number
  /** Median 3-month total return of the population — one number for "what did the middle do". */
  median_ret_3m: string | null
}

/** Breadth inside one GICS sector (stocks) — the same shape, cut by sector. */
export type SectorBreadth = {
  sector: string
  /** `taxonomy_sector.id` for the same GICS level-1 name, so the row can open the drill-down.
   *  Null when the taxonomy has not been seeded — the row still renders, it just does not link,
   *  rather than sending a reader to /sectors#undefined. */
  sector_id: string | null
  members: number
  measured_ema200: number
  above_ema200: number
  measured_rs_3m: number
  beating_3m: number
  median_ret_3m: string | null
  /** Mean composite of the sector's scored members — null while nothing is scored. */
  mean_composite: string | null
}

export type MacroRead = {
  date: string
  vixcls: string | null
  dgs10: string | null
  dtb3: string | null
  dtwexbgs: string | null
}

export type Pulse = Anchor & {
  breadth: Breadth[]
  sectors: SectorBreadth[]
  macro: MacroRead | null
}

// The counts. `count(x)` counts NON-NULL, which is exactly the "measured" denominator this file is
// about: `count(t.above_ema_200)` is how many instruments HAVE a 200-day average, and
// `count(*) FILTER (WHERE t.above_ema_200)` is how many are above it. The two are different
// numbers and the page shows both.
//
// NEAR THE HIGH is within NEAR_52W_PCT of 100 on pos_52w's 0–100 scale (src/lib/breadth.ts — the
// same constant the board's 52-week facet reads, so a count here opens the same rows there).
const BREADTH_COLUMNS = `
  count(*)                                                          AS members,
  count(t.above_ema_200)                                            AS measured_ema200,
  count(*) FILTER (WHERE t.above_ema_200)                           AS above_ema200,
  count(t.above_ema_50)                                             AS measured_ema50,
  count(*) FILTER (WHERE t.above_ema_50)                            AS above_ema50,
  count(*) FILTER (WHERE t.ema_21 IS NOT NULL AND t.ema_50 IS NOT NULL AND t.ema_200 IS NOT NULL)
                                                                    AS measured_stack,
  count(*) FILTER (WHERE t.ema_21 > t.ema_50 AND t.ema_50 > t.ema_200)
                                                                    AS stacked_up,
  count(t.pos_52w)                                                  AS measured_52w,
  count(*) FILTER (WHERE t.pos_52w >= ${100 - NEAR_52W_PCT})       AS near_high,
  count(*) FILTER (WHERE t.pos_52w <= ${NEAR_52W_PCT})              AS near_low,
  count(t.rs_3m_spy)                                                AS measured_rs_3m,
  count(*) FILTER (WHERE t.rs_3m_spy > 0)                           AS beating_3m,
  count(t.rs_12m_spy)                                               AS measured_rs_12m,
  count(*) FILTER (WHERE t.rs_12m_spy > 0)                          AS beating_12m,
  -- ::numeric BEFORE ::text, ALWAYS. percentile_cont returns DOUBLE PRECISION, and postgres
  -- renders a double in scientific notation whenever the magnitude is small enough —
  -- "-1.4210854715202004e-14" is what interpolating between two neighbouring returns produces
  -- when they nearly cancel. The board's formatters refuse a string like that on purpose (a
  -- NUMERIC must never pass through a double, src/lib/format.ts), so the page threw and /pulse
  -- answered 500 in public for as long as it existed. numeric always renders plain decimal.
  percentile_cont(0.5) WITHIN GROUP (ORDER BY t.ret_3m)::numeric::text AS median_ret_3m`

const inner = eodCached(async (): Promise<Pulse> => {
  const sql = db()
  const rows = await sql<(Pulse & { breadth: never })[]>`${sql.unsafe(ANCHOR)} SELECT eod, as_of FROM a`
  const anchor: Anchor = { eod: rows[0]?.eod ?? null, as_of: rows[0]?.as_of ?? '' }

  const breadth = await sql<Breadth[]>`
    ${sql.unsafe(ANCHOR)},
    -- The universe as of the anchor. A session the snapshot has not run for has no universe, and
    -- the page says so rather than counting every listed instrument as a member.
    u AS (
      SELECT s.instrument_id, m.asset_class
      FROM atlas_global.universe_snapshot s
      JOIN atlas_global.instrument_master m ON m.instrument_id = s.instrument_id
      CROSS JOIN a
      WHERE s.date = (SELECT MAX(date) FROM atlas_global.universe_snapshot WHERE date <= a.as_of_d)
        AND s.in_universe AND m.is_active
    )
    SELECT u.asset_class, ${sql.unsafe(BREADTH_COLUMNS)}
    FROM u
    JOIN atlas_global.technical_daily t
      ON t.instrument_id = u.instrument_id
     AND t.date = (SELECT MAX(date) FROM atlas_global.technical_daily WHERE date <= (SELECT as_of_d FROM a))
    GROUP BY u.asset_class
    ORDER BY u.asset_class
  `

  const sectors = await sql<SectorBreadth[]>`
    ${sql.unsafe(ANCHOR)},
    u AS (
      SELECT s.instrument_id, m.sector_gics AS sector
      FROM atlas_global.universe_snapshot s
      JOIN atlas_global.instrument_master m ON m.instrument_id = s.instrument_id
      CROSS JOIN a
      WHERE s.date = (SELECT MAX(date) FROM atlas_global.universe_snapshot WHERE date <= a.as_of_d)
        AND s.in_universe AND m.is_active AND m.asset_class = 'stock' AND m.sector_gics IS NOT NULL
    ),
    scored AS (
      SELECT l.instrument_id, l.composite
      FROM atlas_global.lens_scores_daily l
      WHERE l.date = (SELECT MAX(date) FROM atlas_global.lens_scores_daily
                      WHERE date <= (SELECT as_of_d FROM a))
    )
    SELECT u.sector,
           -- The id comes from taxonomy_sector, never from slugging the display name here: the
           -- two spellings are maintained in different files and the day they diverge, a derived
           -- slug produces a dead anchor with nothing to catch it.
           max(tx.id)                                                  AS sector_id,
           count(*)                                                    AS members,
           count(t.above_ema_200)                                      AS measured_ema200,
           count(*) FILTER (WHERE t.above_ema_200)                     AS above_ema200,
           count(t.rs_3m_spy)                                          AS measured_rs_3m,
           count(*) FILTER (WHERE t.rs_3m_spy > 0)                     AS beating_3m,
           percentile_cont(0.5) WITHIN GROUP (ORDER BY t.ret_3m)::numeric::text AS median_ret_3m,
           avg(scored.composite)::text                                 AS mean_composite
    FROM u
    JOIN atlas_global.technical_daily t
      ON t.instrument_id = u.instrument_id
     AND t.date = (SELECT MAX(date) FROM atlas_global.technical_daily WHERE date <= (SELECT as_of_d FROM a))
    LEFT JOIN scored ON scored.instrument_id = u.instrument_id
    LEFT JOIN atlas_global.taxonomy_sector tx
           ON tx.level = 1 AND tx.is_active AND lower(tx.name) = lower(u.sector)
    GROUP BY u.sector
    ORDER BY u.sector
  `

  const [macro] = await sql<MacroRead[]>`
    SELECT date::text, vixcls::text, dgs10::text, dtb3::text, dtwexbgs::text
    FROM atlas_global.macro_daily
    ORDER BY date DESC
    LIMIT 1
  `

  return { ...anchor, breadth, sectors, macro: macro ?? null }
}, 'pulse')

/** The market's breadth at the anchor session — empty everywhere the producers have not run. */
export async function getPulse(): Promise<Pulse> {
  if (!dbAvailable) return { eod: null, as_of: '', breadth: [], sectors: [], macro: null }
  return inner()
}
