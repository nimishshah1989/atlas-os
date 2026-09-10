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
import type { SectorLevel, SectorNode, SectorTree, SectorWindow } from '@/lib/sectors'
import { SECTOR_WINDOWS } from '@/lib/sectors'
import { MEMBERS } from '@/lib/queries/themes'

export type { SectorLevel, SectorNode, SectorTree, SectorWindow }
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
