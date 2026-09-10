// src/lib/queries/sectors.ts — the DRILL-DOWN: GICS sector → theme → fund, every level in the
// same columns. Reads ONLY atlas_global (the schema gate scans this directory). Cached under `eod`.
//
// THE FM'S BRIEF, and the honest answer to the question inside it: "the themes are clickable to
// their ETFs, like the way we had sectors in Atlas: themes become clickable, or we have a main
// sector, then subsector performance, and then, within that, the ETF. That's why I'm asking: what
// is the level at which we have the mapping."
//
// The mapping is TWO levels deep, not three. `taxonomy_sector` seeds 11 GICS sectors, 33
// sub-sectors and 32 themes — but every theme row's `parent_id` is a level-1 SECTOR, and nothing
// in the pipeline writes `sub_sector_id` on a fund or a stock. The 33 middle rows are also largely
// the SAME granularity as the themes said twice (`energy_nuclear_uranium` and `nuclear_uranium`
// are one idea), so inserting them would cost a click and carry no information. This file
// therefore renders sector → theme → fund and says so, rather than drawing a level nobody filled.
//
// ONE QUERY, THREE LEVELS, ASSEMBLED IN TYPESCRIPT. The alternative is three round trips whose
// medians are cut over three separately-filtered populations — which is how a sector's number
// stops being the median of the themes shown under it.
//
// MEDIAN AT EVERY ROLL-UP. Never a mean, never AUM-weighted: one $30bn fund does not make a theme.
// Every median carries `n_scored` beside it so a median of three is never read as a verdict.
//
// A RANK NEVER CHANGES POPULATION WHEN A ROW EXPANDS. A sector is ranked against the other
// sectors, a theme against the themes IN ITS SECTOR, a fund against the funds carrying ITS theme.
// The alternative — one global rank at every depth — would print "rank 214" inside a theme of six.
import 'server-only'
import { eodCached } from '@/lib/cache'
import { db, dbAvailable } from '@/lib/db'
import type {
  SectorDetail,
  SectorLevel,
  SectorNode,
  SectorPoint,
  SectorStock,
  SectorTree,
  SectorWindow,
} from '@/lib/sectors'
import { SECTOR_WINDOWS } from '@/lib/sectors'
import { MEMBERS } from '@/lib/queries/themes'

export type { SectorDetail, SectorLevel, SectorNode, SectorPoint, SectorStock, SectorTree, SectorWindow }
export { SECTOR_WINDOWS }

const EMPTY: SectorTree = { date: null, rows: [], n_unthemed: 0 }

// A fund, the theme it carries and the sector that theme hangs under. The join to
// `taxonomy_sector` is what drops a theme id with no seeded row — which is a seeding failure, not
// a fund to quietly file under nothing.
const SCOPED = `
  , scoped AS (
    SELECT m.*, tx.id AS tx_theme_id, tx.name AS theme_name,
           sec.id AS sector_id, sec.name AS sector_name
    FROM member m
    JOIN atlas_global.taxonomy_sector tx  ON tx.id = m.theme_id AND tx.level = 3 AND tx.is_active
    JOIN atlas_global.taxonomy_sector sec ON sec.id = tx.parent_id AND sec.level = 1
  )
  -- Deduped for the SECTOR roll-up: a fund carrying two themes of one sector is one fund in that
  -- sector, however many ways it is a bet on it.
  , sector_member AS (
    SELECT DISTINCT ON (sector_id, instrument_id) *
    FROM scoped ORDER BY sector_id, instrument_id, composite DESC NULLS LAST
  )
`

// The aggregate every roll-up level shares, so a column means one thing at both depths. `alias`
// names the grouping column; `src` the CTE to read.
// ::numeric before ::text on every percentile: percentile_cont returns DOUBLE PRECISION and
// postgres renders a small double in scientific notation, which the board's formatters refuse by
// design (this took /pulse down in public — see queries/pulse.ts).
const rollup = (src: string, key: string) => `
  SELECT ${key} AS group_id,
         count(*)                                     AS n_funds,
         count(composite)                             AS n_scored,
         sum(aum_usd)                                 AS aum_usd,
         percentile_cont(0.5) WITHIN GROUP (ORDER BY composite)::numeric(6,2)   AS composite,
         percentile_cont(0.5) WITHIN GROUP (ORDER BY rs_3m_spy)::numeric        AS rs_3m,
         percentile_cont(0.5) WITHIN GROUP (ORDER BY rs_6m_spy)::numeric        AS rs_6m,
         percentile_cont(0.5) WITHIN GROUP (ORDER BY rs_12m_spy)::numeric       AS rs_12m,
         -- count(x) is the MEASURED denominator: a theme whose funds are all too young for a
         -- 200-day line is null here, not 0% (rule #0).
         (count(*) FILTER (WHERE above_ema_200)::numeric
            / nullif(count(above_ema_200), 0))        AS above_ema200_frac,
         (array_agg(symbol ORDER BY composite DESC NULLS LAST))[1] AS top_symbol,
         (array_agg(name   ORDER BY composite DESC NULLS LAST))[1] AS top_name
  FROM ${src} GROUP BY ${key}
`

type NodeDbRow = {
  level: SectorLevel
  id: string
  parent_id: string | null
  name: string
  symbol: string | null
  n_funds: number
  n_scored: number
  aum_usd: string | null
  composite: string | null
  above_ema200_frac: string | null
  rank: number | null
  n_ranked: number
  top_symbol: string | null
  top_name: string | null
} & Record<`rs_${SectorWindow}`, string | null>

const rsOf = (r: Record<`rs_${SectorWindow}`, string | null>) =>
  Object.fromEntries(SECTOR_WINDOWS.map((w) => [w, r[`rs_${w}`] ?? null])) as Record<
    SectorWindow,
    string | null
  >

const treeInner = eodCached(async (): Promise<SectorTree> => {
  const rows = await db()<NodeDbRow[]>`
    ${db().unsafe(MEMBERS)}
    ${db().unsafe(SCOPED)}
    , sector_roll AS (${db().unsafe(rollup('sector_member', 'sector_id'))})
    , theme_roll  AS (${db().unsafe(rollup('scoped', 'tx_theme_id'))})
    , theme_key AS (SELECT DISTINCT tx_theme_id, theme_name, sector_id FROM scoped)
    SELECT 'sector'::text AS level, r.group_id AS id, NULL::text AS parent_id,
           sec.name, NULL::text AS symbol,
           r.n_funds, r.n_scored, r.aum_usd::text, r.composite::text,
           r.rs_3m::text, r.rs_6m::text, r.rs_12m::text, r.above_ema200_frac::text,
           RANK() OVER (ORDER BY r.composite DESC NULLS LAST)                    AS rank,
           count(*) FILTER (WHERE r.composite IS NOT NULL) OVER ()                AS n_ranked,
           r.top_symbol, r.top_name
    FROM sector_roll r
    JOIN atlas_global.taxonomy_sector sec ON sec.id = r.group_id

    UNION ALL
    SELECT 'theme', r.group_id, k.sector_id, k.theme_name, NULL,
           r.n_funds, r.n_scored, r.aum_usd::text, r.composite::text,
           r.rs_3m::text, r.rs_6m::text, r.rs_12m::text, r.above_ema200_frac::text,
           RANK() OVER (PARTITION BY k.sector_id ORDER BY r.composite DESC NULLS LAST),
           count(*) FILTER (WHERE r.composite IS NOT NULL) OVER (PARTITION BY k.sector_id),
           r.top_symbol, r.top_name
    FROM theme_roll r JOIN theme_key k ON k.tx_theme_id = r.group_id

    UNION ALL
    -- The leaf. Every column is the fund's OWN figure, which is what makes the roll-ups above
    -- readable in the same header: above_ema200_frac is 1 or 0 for ONE fund, and the median of
    -- those same ones and zeros for the node above it.
    SELECT 'fund', s.symbol, s.tx_theme_id, s.name, s.symbol,
           1, (s.composite IS NOT NULL)::int, s.aum_usd::text, s.composite::text,
           s.rs_3m_spy::text, s.rs_6m_spy::text, s.rs_12m_spy::text,
           s.above_ema_200::int::text,
           RANK() OVER (PARTITION BY s.tx_theme_id ORDER BY s.composite DESC NULLS LAST),
           count(*) FILTER (WHERE s.composite IS NOT NULL) OVER (PARTITION BY s.tx_theme_id),
           s.symbol, s.name
    FROM scoped s
  `
  const [anchor] = await db()<{ date: string | null; n_unthemed: number }[]>`
    SELECT (SELECT max(date)::text FROM atlas_global.etf_scores_daily) AS date,
           count(*) FILTER (WHERE cardinality(c.theme_ids) = 0)        AS n_unthemed
    FROM atlas_global.etf_classification c
    JOIN atlas_global.instrument_master im USING (instrument_id)
    WHERE c.valid_to IS NULL AND c.status IN ('auto', 'confirmed', 'override') AND im.is_active
  `
  if (rows.length === 0) return { ...EMPTY, n_unthemed: Number(anchor?.n_unthemed ?? 0) }

  const node = (r: NodeDbRow): SectorNode => ({
    level: r.level,
    id: r.id,
    name: r.name,
    symbol: r.symbol,
    n_children: 0,
    n_funds: Number(r.n_funds),
    n_scored: Number(r.n_scored),
    aum_usd: r.aum_usd,
    composite: r.composite,
    above_ema200_frac: r.above_ema200_frac,
    rs: rsOf(r),
    // A rank over a population where nothing is scored is not rank 1, it is no rank.
    rank: r.composite == null ? null : Number(r.rank),
    n_ranked: Number(r.n_ranked),
    top_symbol: r.top_symbol,
    top_name: r.top_name,
    children: [],
  })

  // Parent id → children, then attach. Assembled here rather than in SQL because the shape is a
  // tree and the wire is a list; the alternative is a recursive CTE that has to re-state every
  // column at every depth.
  const byParent = new Map<string, SectorNode[]>()
  const sectors: SectorNode[] = []
  for (const r of rows) {
    const n = node(r)
    if (r.level === 'sector') sectors.push(n)
    else {
      const key = r.parent_id ?? ''
      const list = byParent.get(key)
      if (list) list.push(n)
      else byParent.set(key, [n])
    }
  }
  const byRank = (a: SectorNode, b: SectorNode) =>
    (a.rank ?? Infinity) - (b.rank ?? Infinity) ||
    b.n_funds - a.n_funds ||
    a.name.localeCompare(b.name)

  for (const s of sectors) {
    s.children = (byParent.get(s.id) ?? []).sort(byRank)
    s.n_children = s.children.length
    for (const t of s.children) {
      t.children = (byParent.get(t.id) ?? []).sort(byRank)
      t.n_children = t.children.length
    }
  }
  return {
    date: anchor?.date ?? null,
    rows: sectors.sort(byRank),
    n_unthemed: Number(anchor?.n_unthemed ?? 0),
  }
}, 'sectors')

/** Every GICS sector with a themed fund, each carrying its themes and each theme its funds. */
export async function getSectorTree(): Promise<SectorTree> {
  if (!dbAvailable) return EMPTY
  return treeInner()
}

// ── one sector's own page ───────────────────────────────────────────────────

/** How far back the sector's own line is drawn, in SESSIONS not calendar days — the same window
 *  rule queries/series.ts states: a LIMIT over trading days gives every instrument the same number
 *  of observations whoever was closed for a holiday. Three years is the shortest window in which a
 *  sector rotation is visible at all. */
const HISTORY_SESSIONS = 756

/** …and only every fifth of them is plotted. A three-year trend line is the SAME line at weekly
 *  resolution, and this is a page load: the daily version made a cold sector page take 24 seconds
 *  on the live board, because a median has to be computed per date over every member fund. The
 *  oldest session is always kept whatever the stride lands on — it is the base every fund is
 *  rebased to, so losing it would lose the line. */
const HISTORY_STRIDE = 5

type StockDbRow = {
  symbol: string
  name: string | null
  rank: number | null
  n_ranked: number
  composite: string | null
  decile: number | null
  rs_3m_spy: string | null
  rs_12m_spy: string | null
  above_ema_200: boolean | null
  adv_usd: string | null
}

type PointDbRow = { date: string; index: string | null; spy: string | null }

const detailInner = eodCached(async (id: string): Promise<SectorDetail | null> => {
  const tree = await treeInner()
  const node = tree.rows.find((r) => r.id === id)
  if (!node) return null

  // THE TWO RANKINGS ARE CUT OVER TWO POPULATIONS, IN THAT ORDER, AND THE ORDER IS THE POINT.
  //
  // The DECILE is cut first, over the WHOLE scored index inside each cap cohort — the same cut
  // queries/scores.ts makes for /sp500, so a company shows the same decile on both pages. Cutting
  // it after the sector filter would rank Energy's mega-caps against Energy's mega-caps and call
  // the result "decile 9", which is a different sentence wearing the same word.
  //
  // The RANK is cut second, after the filter, because "which name in Energy" is a question about
  // Energy. Two numbers, two populations, and neither is allowed to be mistaken for the other.
  const stocks = await db()<StockDbRow[]>`
    WITH anchor AS (
      SELECT max(date) AS d FROM atlas_global.lens_scores_daily WHERE asset_class = 'stock'
    ),
    universe AS (
      SELECT instrument_id FROM atlas_global.universe_snapshot
      WHERE date = (SELECT max(date) FROM atlas_global.universe_snapshot) AND in_universe
    ),
    scored AS (
      SELECT im.instrument_id, im.symbol, im.name, im.sector_gics,
             s.composite,
             CASE WHEN s.composite IS NULL THEN NULL ELSE
               ntile(10) OVER (PARTITION BY s.cap_cohort, (s.composite IS NULL) ORDER BY s.composite)
             END AS decile
      FROM atlas_global.instrument_master im
      CROSS JOIN anchor a
      JOIN universe u ON u.instrument_id = im.instrument_id
      LEFT JOIN atlas_global.lens_scores_daily s
             ON s.instrument_id = im.instrument_id AND s.date = a.d AND s.asset_class = 'stock'
      WHERE im.is_active AND im.asset_class = 'stock'
    ),
    mine AS (
      SELECT sc.*
      FROM scored sc
      JOIN atlas_global.taxonomy_sector tx
        ON tx.level = 1 AND tx.is_active AND lower(tx.name) = lower(sc.sector_gics)
      WHERE tx.id = ${id}
    )
    SELECT m.symbol, m.name,
           RANK() OVER (ORDER BY m.composite DESC NULLS LAST)          AS rank,
           count(m.composite) OVER ()                                  AS n_ranked,
           m.composite::text AS composite,
           m.decile,
           t.rs_3m_spy::text AS rs_3m_spy, t.rs_12m_spy::text AS rs_12m_spy,
           t.above_ema_200, t.adv_usd_60d_median::text AS adv_usd
    FROM mine m
    CROSS JOIN anchor a
    LEFT JOIN atlas_global.technical_daily t
           ON t.instrument_id = m.instrument_id AND t.date = a.d
    ORDER BY m.composite DESC NULLS LAST, t.adv_usd_60d_median DESC NULLS LAST
  `

  // The sector's own line. Each member fund is rebased to its OWN close on the window's first
  // session, and the sector is the MEDIAN of those growth factors — never a mean, never
  // AUM-weighted, for the same reason every roll-up on this board is a median.
  //
  // MEMBERSHIP IS FIXED AT THE WINDOW'S START, which is a survivorship claim and is printed as
  // one: a fund listed since is not in this line, and one that closed is not either. The honest
  // alternative — a chained index over changing membership — is a producer's job, not a page's,
  // and inventing one here would be a number nobody computed (rule #0).
  const points = await db()<PointDbRow[]>`
    WITH spy_cal AS (
      SELECT o.date, o.close_tr, row_number() OVER (ORDER BY o.date DESC) AS rn
      FROM atlas_global.ohlcv_daily o
      JOIN atlas_global.instrument_master m USING (instrument_id)
      WHERE m.symbol = 'SPY' AND m.is_active AND o.close_tr > 0
    ),
    cal AS (
      SELECT date, close_tr FROM spy_cal
      WHERE rn <= ${HISTORY_SESSIONS}
        AND (rn % ${HISTORY_STRIDE} = 1 OR rn = ${HISTORY_SESSIONS})
    ),
    d0 AS (SELECT min(date) AS d FROM cal),
    member AS (
      SELECT DISTINCT im.instrument_id
      FROM atlas_global.etf_classification c
      JOIN atlas_global.instrument_master im USING (instrument_id)
      JOIN atlas_global.taxonomy_sector tx ON tx.id = ANY (c.theme_ids) AND tx.level = 3
      WHERE c.valid_to IS NULL AND c.status IN ('auto', 'confirmed', 'override')
        AND im.is_active AND tx.parent_id = ${id}
    ),
    base AS (
      SELECT o.instrument_id, o.close_tr
      FROM atlas_global.ohlcv_daily o
      JOIN member USING (instrument_id)
      WHERE o.date = (SELECT d FROM d0) AND o.close_tr > 0
    ),
    spy0 AS (SELECT close_tr FROM cal WHERE date = (SELECT d FROM d0))
    SELECT o.date::text,
           -- ::numeric before ::text: percentile_cont returns DOUBLE PRECISION and postgres
           -- renders a small double in scientific notation, which the board's formatters refuse.
           (percentile_cont(0.5) WITHIN GROUP (ORDER BY o.close_tr / b.close_tr) * 100)
             ::numeric(12,4)::text                                                  AS index,
           (max(cal.close_tr) / (SELECT close_tr FROM spy0) * 100)::numeric(12,4)::text AS spy
    FROM atlas_global.ohlcv_daily o
    JOIN base b ON b.instrument_id = o.instrument_id
    JOIN cal ON cal.date = o.date
    -- The lower bound is the point of this line: ohlcv_daily is keyed (instrument_id, date), and
    -- without it the planner has no range to scan and reads every bar these funds ever had.
    WHERE o.date >= (SELECT d FROM d0) AND o.close_tr > 0
    GROUP BY o.date
    ORDER BY o.date
  `

  const history: SectorPoint[] = points
    .filter((p) => p.index != null)
    .map((p) => ({ date: p.date, index: Number(p.index), spy: p.spy == null ? null : Number(p.spy) }))

  return {
    node,
    rank: node.rank,
    n_ranked: node.n_ranked,
    date: tree.date,
    stocks: stocks.map((r): SectorStock => ({
      symbol: r.symbol,
      name: r.name,
      rank: r.composite == null ? null : Number(r.rank),
      n_ranked: Number(r.n_ranked),
      composite: r.composite,
      decile: r.decile == null ? null : Number(r.decile),
      rs_3m_spy: r.rs_3m_spy,
      rs_12m_spy: r.rs_12m_spy,
      above_ema_200: r.above_ema_200,
      adv_usd: r.adv_usd,
    })),
    history,
    history_members: history.length ? node.n_funds : 0,
    history_from: history[0]?.date ?? null,
  }
}, 'sector')

/** One sector: its themes and funds from the same tree /sectors ranks, its S&P 500 members, and
 *  its own three-year line against the index. Null when the id is not a level-1 sector with a
 *  themed fund under it. */
export async function getSector(id: string): Promise<SectorDetail | null> {
  if (!dbAvailable) return null
  return detailInner(id)
}
