// src/lib/queries/themes.ts — the THEME view: what a fund is actually about, and which fund to buy
// for it. Reads ONLY atlas_global (the schema gate scans this directory). Cached under `eod`.
//
// WHY THIS SURFACE EXISTS. The FM, on the classification as it stood: "what I meant is
// categorization. If there is something like an ETF which is focused on AI, then creating that
// artificial intelligence. I told you that it's not just energy, it's energy sources, like those
// kinds of classifications... We want to create centered funds, like funds around, let's just say,
// gold and silver miners. We want to create funds around water and food security. Within the
// category... there should be a rank: the right fund within that particular category."
//
// So a theme is a level-3 node of `taxonomy_sector`, a fund carries up to three of them in
// `etf_classification.theme_ids`, and this file answers the two questions in that order: which
// themes are working, and inside one, which fund is the way to own it.
//
// TWO RANKINGS, NEVER CONFLATED. A fund's decile on /etfs is cut in its global peer group; the
// rank here is cut across the funds CARRYING THIS THEME. "Best AI fund" and "best fund" are
// different sentences and the page must never let one be read as the other.
//
// MEDIAN, NOT MEAN, for a theme's own figures. A theme with one $30bn fund and nine $50m ones is
// not that one fund, and an AUM-weighted mean would say it was. The median names the typical
// member; `n_scored` is printed beside it so a median of three is never read as a verdict.
//
// RANK ALWAYS, DECILE ONLY WHEN THE POPULATION CARRIES ONE. "3 of 14" is exact at any size.
// A decile is not: ntile(10) over six funds prints "decile 6 of 10" for sixth of six, which is the
// defect scores.ts already guards against for peer groups. The cut-off is the FM's own
// `peer_group_min_members`, read from atlas_thresholds — there is no default (rule #1), and a
// missing row is an error rather than a number this file chose.
import 'server-only'
import { eodCached } from '@/lib/cache'
import { db, dbAvailable } from '@/lib/db'
import type { ThemeDetail, ThemeFund, ThemeList, ThemeRow, ThemeWindow } from '@/lib/themes'
import { THEME_WINDOWS } from '@/lib/themes'

export type { ThemeDetail, ThemeFund, ThemeList, ThemeRow, ThemeWindow }
export { THEME_WINDOWS }

const EMPTY: ThemeList = { date: null, rows: [] }

// Every classified fund, exploded over the themes it carries, with the score and metric row of
// the anchor session. A fund in three themes counts in all three — it IS an AI fund and a
// semiconductor fund, and dropping it from two of them to keep the counts tidy would be a lie
// about what it holds.
// Exported because `queries/sectors.ts` rolls the SAME rows up one more level. Two surfaces
// deriving membership from the same columns twice is how a fund ends up in a theme on one page
// and out of it on the next.
export const MEMBERS = `
  WITH anchor AS (SELECT max(date) AS d FROM atlas_global.etf_scores_daily),
  member AS (
    SELECT unnest(c.theme_ids)         AS theme_id,
           im.instrument_id, im.symbol, im.name,
           c.leveraged, c.inverse, c.hedged, c.role_id,
           s.composite, s.technical, s.risk, s.cost_liquidity,
           t.adv_usd_60d_median, t.above_ema_200,
           t.rs_3m_spy, t.rs_6m_spy, t.rs_12m_spy,
           em.expense_ratio, em.aum_usd
    FROM atlas_global.etf_classification c
    JOIN atlas_global.instrument_master im USING (instrument_id)
    CROSS JOIN anchor a
    LEFT JOIN atlas_global.etf_scores_daily s
           ON s.instrument_id = im.instrument_id AND s.date = a.d
    LEFT JOIN atlas_global.technical_daily t
           ON t.instrument_id = im.instrument_id AND t.date = a.d
    LEFT JOIN atlas_global.etf_meta em ON em.instrument_id = im.instrument_id
    WHERE c.valid_to IS NULL
      AND c.status IN ('auto', 'confirmed', 'override')
      AND cardinality(c.theme_ids) > 0
      AND im.is_active
  )
`

type ThemeDbRow = {
  id: string
  name: string
  sector_id: string | null
  sector_name: string | null
  n_funds: number | null
  n_scored: number | null
  aum_usd: string | null
  median_composite: string | null
  above_ema200_frac: string | null
  top_symbol: string | null
  top_name: string | null
  top_composite: string | null
  top_decile: number | null
  date: string | null
} & Record<`rs_${ThemeWindow}`, string | null>

const rsOf = (r: Record<`rs_${ThemeWindow}`, string | null>) =>
  Object.fromEntries(THEME_WINDOWS.map((w) => [w, r[`rs_${w}`] ?? null])) as Record<ThemeWindow, string | null>

/** The FM's minimum population for a decile, from his table. No default: a board that invented one
 *  would rank six funds into ten buckets and call the worst of them "decile 6". */
const MIN_MEMBERS_KEY = 'peer_group_min_members'

export async function peerGroupMinMembers(): Promise<number> {
  // The columns are `threshold_key` / `threshold_value` and the row must be active — India's
  // shape, which this table copies verbatim so load_thresholds and the admin panel work on both
  // boards. Guessing `key` / `value` is what took /themes down on its first deploy.
  const [row] = await db()<{ threshold_value: string }[]>`
    SELECT threshold_value::text AS threshold_value
    FROM atlas_global.atlas_thresholds
    WHERE is_active AND threshold_key = ${MIN_MEMBERS_KEY}
  `
  if (!row) {
    throw new Error(
      `atlas_global.atlas_thresholds is missing ${MIN_MEMBERS_KEY} — run ` +
        'scripts/global_market/seed_thresholds.py (FM approval first); there are no defaults.',
    )
  }
  return Number(row.threshold_value)
}

const listInner = eodCached(async (): Promise<ThemeList> => {
  const min = await peerGroupMinMembers()
  const rows = await db()<ThemeDbRow[]>`
    ${db().unsafe(MEMBERS)}
    , ranked AS (
      SELECT m.*,
             RANK()   OVER (PARTITION BY m.theme_id ORDER BY m.composite DESC) AS rank_in_theme,
             CASE WHEN count(*) OVER (PARTITION BY m.theme_id) >= ${min}
                  THEN ntile(10) OVER (PARTITION BY m.theme_id ORDER BY m.composite)
             END AS decile_in_theme
      FROM member m WHERE m.composite IS NOT NULL
    )
    SELECT tx.id, tx.name,
           parent.id   AS sector_id,
           parent.name AS sector_name,
           (SELECT max(date)::text FROM atlas_global.etf_scores_daily) AS date,
           count(m.instrument_id)                                  AS n_funds,
           count(m.composite)                                      AS n_scored,
           sum(m.aum_usd)::text                                    AS aum_usd,
           -- ::numeric before ::text on every one of these: see the note in pulse.ts. A double
           -- rendered as "5e-17" is what a percentile between two near-equal returns produces,
           -- and the board's formatters refuse that string by design.
           percentile_cont(0.5) WITHIN GROUP (ORDER BY m.composite)::numeric(6,2)::text  AS median_composite,
           percentile_cont(0.5) WITHIN GROUP (ORDER BY m.rs_3m_spy)::numeric::text                AS rs_3m,
           percentile_cont(0.5) WITHIN GROUP (ORDER BY m.rs_6m_spy)::numeric::text                AS rs_6m,
           percentile_cont(0.5) WITHIN GROUP (ORDER BY m.rs_12m_spy)::numeric::text               AS rs_12m,
           -- share of MEASURED members above their own 200-day EMA: count(x) is the measured
           -- denominator, so a theme whose members are too young for a 200-day line is null
           -- rather than 0% (rule #0).
           (count(*) FILTER (WHERE m.above_ema_200)::numeric
              / nullif(count(m.above_ema_200), 0))::text           AS above_ema200_frac,
           lead.symbol                                             AS top_symbol,
           lead.name                                               AS top_name,
           lead.composite::text                                    AS top_composite,
           lead.decile                                             AS top_decile
    FROM atlas_global.taxonomy_sector tx
    LEFT JOIN atlas_global.taxonomy_sector parent ON parent.id = tx.parent_id
    LEFT JOIN member m ON m.theme_id = tx.id
    -- The strongest fund carrying the theme. Its decile is 10 by construction when the theme is
    -- big enough to be cut into ten, and NULL when it is not — never a manufactured "3 of 10"
    -- because three funds happened to be measured.
    LEFT JOIN LATERAL (
      SELECT r.symbol, r.name, r.composite, r.decile_in_theme AS decile
      FROM ranked r
      WHERE r.theme_id = tx.id AND r.rank_in_theme = 1
      LIMIT 1
    ) lead ON true
    WHERE tx.level = 3 AND tx.is_active
    GROUP BY tx.id, tx.name, parent.id, parent.name,
             lead.symbol, lead.name, lead.composite, lead.decile
    ORDER BY count(m.composite) DESC, count(m.instrument_id) DESC, tx.name
  `
  if (rows.length === 0) return EMPTY
  return {
    date: rows[0].date,
    rows: rows.map((r): ThemeRow => ({
      id: r.id,
      name: r.name,
      sector_id: r.sector_id,
      sector_name: r.sector_name,
      n_funds: r.n_funds ?? 0,
      n_scored: r.n_scored ?? 0,
      aum_usd: r.aum_usd,
      median_composite: r.median_composite,
      above_ema200_frac: r.above_ema200_frac,
      top_symbol: r.top_symbol,
      top_name: r.top_name,
      top_composite: r.top_composite,
      top_decile: r.top_decile,
      rs: rsOf(r),
    })),
  }
}, 'themes')

/** Every theme a classified fund carries, strongest-populated first. */
export async function getThemes(): Promise<ThemeList> {
  if (!dbAvailable) return EMPTY
  return listInner()
}

type FundDbRow = {
  instrument_id: string
  symbol: string
  name: string
  rank: number | null
  composite: string | null
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
} & Record<`rs_${ThemeWindow}`, string | null>

const detailInner = eodCached(async (id: string): Promise<ThemeDetail | null> => {
  const list = await listInner()
  const row = list.rows.find((r) => r.id === id)
  if (!row || !list.date) return null
  const min = await peerGroupMinMembers()

  const funds = await db()<FundDbRow[]>`
    ${db().unsafe(MEMBERS)}
    , mine AS (SELECT * FROM member WHERE theme_id = ${id})
    , scored AS (
      SELECT instrument_id,
             RANK() OVER (ORDER BY composite DESC) AS rank,
             CASE WHEN count(*) OVER () >= ${min}
                  THEN ntile(10) OVER (ORDER BY composite) END AS decile
      FROM mine WHERE composite IS NOT NULL
    )
    SELECT m.instrument_id::text AS instrument_id, m.symbol, m.name,
           sc.rank, sc.decile,
           m.composite::text      AS composite,
           m.technical::text      AS technical,
           m.risk::text           AS risk,
           m.cost_liquidity::text AS cost_liquidity,
           m.adv_usd_60d_median::text AS adv_usd_60d_median,
           m.expense_ratio::text  AS expense_ratio,
           m.aum_usd::text        AS aum_usd,
           m.leveraged, m.inverse, m.hedged, m.role_id,
           m.rs_3m_spy::text  AS rs_3m,
           m.rs_6m_spy::text  AS rs_6m,
           m.rs_12m_spy::text AS rs_12m
    FROM mine m
    LEFT JOIN scored sc USING (instrument_id)
    -- Scored funds first, strongest down; then the unscored, most-traded first. An unscored fund
    -- is geared, inverse, hedged or below the liquidity floor — not weak.
    ORDER BY sc.rank NULLS LAST, m.adv_usd_60d_median DESC NULLS LAST
  `
  return {
    row,
    date: list.date,
    funds: funds.map((f): ThemeFund => ({
      instrument_id: f.instrument_id,
      symbol: f.symbol,
      name: f.name,
      rank: f.rank,
      composite: f.composite,
      decile: f.decile,
      technical: f.technical,
      risk: f.risk,
      cost_liquidity: f.cost_liquidity,
      adv_usd_60d_median: f.adv_usd_60d_median,
      expense_ratio: f.expense_ratio,
      aum_usd: f.aum_usd,
      leveraged: f.leveraged,
      inverse: f.inverse,
      hedged: f.hedged,
      role_id: f.role_id,
      rs: rsOf(f),
    })),
  }
}, 'theme')

/** One theme: its summary row, and every fund carrying it, ranked within it. */
export async function getTheme(id: string): Promise<ThemeDetail | null> {
  if (!dbAvailable) return null
  return detailInner(id)
}
