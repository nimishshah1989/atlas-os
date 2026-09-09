// src/lib/queries/scores.ts — the ranked board's reads. Reads ONLY atlas_global (the schema gate
// scans this directory): instrument_master, universe_snapshot, technical_daily, etf_classification,
// etf_scores_daily, lens_scores_daily, country, atlas_thresholds.
//
// DECILES ARE CUT ON READ, NEVER STORED. `ntile(10) OVER (PARTITION BY date, peer_group ORDER BY
// composite)` over NON-NULL composites only — the rule India applies within cap cohort
// (scripts/foundation/decile_core.py: "read-only, nothing materialised here"), and the rule
// scripts/global_market/score_etfs.py's docstring states for exactly this reason: a decile is a
// statement about a population on a date, and materialising it would let a fund's rank go stale
// while its score moved. Stocks partition by `cap_cohort`, ETFs by `peer_group`. Leader = decile 10.
//
// The null-flag in the PARTITION BY is India's idiom (frontend/src/lib/queries/stock_lens.ts):
// rows with no composite form their own partition and their ntile is then nulled out, so an
// unscored fund never borrows a rank from the scored population.
//
// THE SCORE SESSION IS ITS OWN ANCHOR. Prices anchor on the latest SPY session; scores anchor on
// the latest session the SCORER has written at or before it. When the scorer lags a day the board
// shows the scores it has and says which session they are from, instead of going blank.
import 'server-only'
import { eodCached } from '@/lib/cache'
import { db, dbAvailable } from '@/lib/db'
import { packRows, toInstrumentRow, type AssetClass, type InstrumentDbRow, type PackedRows } from '@/lib/facts'
import type { LensWeight } from '@/lib/scores'
import { ANCHOR, type Anchor } from './instruments'

/** The anchor, the session the scores are from, the lens weights in force, and every row packed. */
export type InstrumentList = Anchor & PackedRows & { scored_on: string | null; lenses: LensWeight[] }

type ListRow = InstrumentDbRow & Anchor & { scored_on: string | null }

// ── lens weights ────────────────────────────────────────────────────────────

// The blend's weights, from the one place a weight is allowed to live (rule #1). The denominator
// in "2 of 5 lenses" is how many of these exist, so the board never writes that number down.
// Widest segment first: the bar reads as "this is what the score is mostly made of".
const WEIGHT_PREFIX: Record<AssetClass, string> = { etf: 'etf_lens_weight_', stock: 'lens_weight_' }

const weightsInner = eodCached(async (assetClass: AssetClass): Promise<LensWeight[]> => {
  const prefix = WEIGHT_PREFIX[assetClass]
  const rows = await db()<{ threshold_key: string; weight: string }[]>`
    SELECT threshold_key, threshold_value::text AS weight
    FROM atlas_global.atlas_thresholds
    WHERE is_active AND threshold_key LIKE ${prefix + '%'}
    ORDER BY threshold_value DESC NULLS LAST, threshold_key
  `
  return rows.map((r) => ({ key: r.threshold_key.slice(prefix.length), weight: Number(r.weight ?? 0) }))
}, 'lens-weights')

/** The lens weights `atlas_thresholds` carries for this market's blend; empty with no seed rows. */
export async function getLensWeights(assetClass: AssetClass): Promise<LensWeight[]> {
  if (!dbAvailable) return []
  return weightsInner(assetClass)
}

// ── the ETF list ────────────────────────────────────────────────────────────

const etfListInner = eodCached(async (): Promise<ListRow[]> => {
  return db()<ListRow[]>`
    ${db().unsafe(ANCHOR)},
    scored_on AS (
      SELECT MAX(s.date) AS d
      FROM atlas_global.etf_scores_daily s, a
      WHERE s.date <= a.as_of_d
    ),
    -- A fund whose whole asset class has fewer than atlas_thresholds.peer_group_min_members
    -- in-universe members gets peer_group = NULL from score_etfs (its assign_groups docstring
    -- says why there is nowhere further to fall). It is scored and listed; it is NOT ranked,
    -- because ntile(10) over six rows would print "decile 6 of 10" for sixth of six.
    ranked AS (
      SELECT s.instrument_id, s.technical, s.composite, s.conviction_tier, s.peer_group,
             s.lenses_active,
             CASE WHEN s.composite IS NULL OR s.peer_group IS NULL THEN NULL ELSE
               ntile(10) OVER (PARTITION BY s.date, s.peer_group, (s.composite IS NULL)
                               ORDER BY s.composite)
             END AS composite_decile,
             CASE WHEN s.composite IS NULL OR s.peer_group IS NULL THEN NULL ELSE
               rank() OVER (PARTITION BY s.date, s.peer_group, (s.composite IS NULL)
                            ORDER BY s.composite DESC)
             END AS peer_rank,
             CASE WHEN s.peer_group IS NULL THEN NULL ELSE
               count(s.composite) OVER (PARTITION BY s.date, s.peer_group) END AS peer_n
      FROM atlas_global.etf_scores_daily s
      WHERE s.date = (SELECT d FROM scored_on)
    )
    SELECT
      m.symbol, m.name, m.asset_class, m.sector_gics,
      u.in_universe, u.exclusion_reason AS universe_exclusion,
      c.strategy, c.asset_class AS class_asset_class,
      c.leveraged, c.inverse, c.hedged, c.status AS class_status,
      co.name AS country, co.region,
      r.composite::text        AS composite,
      r.technical::text        AS technical,
      r.conviction_tier, r.peer_group,
      r.lenses_active::int     AS lenses_active,
      r.composite_decile::int  AS composite_decile,
      r.peer_rank::int         AS peer_rank,
      r.peer_n::int            AS peer_n,
      t.rs_3m_spy::text        AS rs_3m_spy,
      t.rs_6m_spy::text        AS rs_6m_spy,
      t.rs_12m_spy::text       AS rs_12m_spy,
      t.pos_52w::text          AS pos_52w,
      t.adv_usd_60d_median::text AS adv_usd,
      t.vol_252d_ann::text     AS vol_ann,
      t.mdd_12m::text          AS mdd_12m,
      a.eod, a.as_of, (SELECT d FROM scored_on)::text AS scored_on
    FROM atlas_global.instrument_master m
    CROSS JOIN a
    LEFT JOIN atlas_global.universe_snapshot u ON u.instrument_id = m.instrument_id AND u.date = a.as_of_d
    LEFT JOIN atlas_global.technical_daily   t ON t.instrument_id = m.instrument_id AND t.date = a.as_of_d
    LEFT JOIN ranked r ON r.instrument_id = m.instrument_id
    LEFT JOIN LATERAL (
      SELECT ec.strategy, ec.asset_class, ec.leveraged, ec.inverse, ec.hedged, ec.status, ec.country_codes
      FROM atlas_global.etf_classification ec
      WHERE ec.instrument_id = m.instrument_id
      ORDER BY (ec.valid_to IS NOT NULL), ec.version DESC
      LIMIT 1
    ) c ON true
    LEFT JOIN atlas_global.country co ON co.iso2::text = c.country_codes[1]
    WHERE m.is_active AND m.asset_class = 'etf'
    ORDER BY m.symbol
  `
}, 'etf-list')

// ── the stock list ──────────────────────────────────────────────────────────

// lens_scores_daily's producer is landing alongside this board, so every score column here is a
// LEFT JOIN over a table that may hold nothing: MAX(date) of an empty journal is NULL, the join
// matches no row, and the page renders its "not scored yet" state rather than failing.
const stockListInner = eodCached(async (): Promise<ListRow[]> => {
  return db()<ListRow[]>`
    ${db().unsafe(ANCHOR)},
    scored_on AS (
      SELECT MAX(s.date) AS d
      FROM atlas_global.lens_scores_daily s, a
      WHERE s.date <= a.as_of_d AND s.asset_class = 'stock'
    ),
    ranked AS (
      SELECT s.instrument_id, s.technical, s.composite, s.conviction_tier,
             s.cap_cohort AS peer_group, s.lenses_active,
             CASE WHEN s.composite IS NULL THEN NULL ELSE
               ntile(10) OVER (PARTITION BY s.date, s.cap_cohort, (s.composite IS NULL)
                               ORDER BY s.composite)
             END AS composite_decile,
             CASE WHEN s.composite IS NULL THEN NULL ELSE
               rank() OVER (PARTITION BY s.date, s.cap_cohort, (s.composite IS NULL)
                            ORDER BY s.composite DESC)
             END AS peer_rank,
             count(s.composite) OVER (PARTITION BY s.date, s.cap_cohort) AS peer_n
      FROM atlas_global.lens_scores_daily s
      WHERE s.date = (SELECT d FROM scored_on) AND s.asset_class = 'stock'
    )
    SELECT
      m.symbol, m.name, m.asset_class, m.sector_gics,
      u.in_universe, u.exclusion_reason AS universe_exclusion,
      NULL::text AS strategy, NULL::text AS class_asset_class,
      NULL::boolean AS leveraged, NULL::boolean AS inverse, NULL::boolean AS hedged,
      NULL::text AS class_status, NULL::text AS country, NULL::text AS region,
      r.composite::text        AS composite,
      r.technical::text        AS technical,
      r.conviction_tier, r.peer_group,
      r.lenses_active::int     AS lenses_active,
      r.composite_decile::int  AS composite_decile,
      r.peer_rank::int         AS peer_rank,
      r.peer_n::int            AS peer_n,
      t.rs_3m_spy::text        AS rs_3m_spy,
      t.rs_6m_spy::text        AS rs_6m_spy,
      t.rs_12m_spy::text       AS rs_12m_spy,
      t.pos_52w::text          AS pos_52w,
      t.adv_usd_60d_median::text AS adv_usd,
      t.vol_252d_ann::text     AS vol_ann,
      t.mdd_12m::text          AS mdd_12m,
      a.eod, a.as_of, (SELECT d FROM scored_on)::text AS scored_on
    FROM atlas_global.instrument_master m
    CROSS JOIN a
    LEFT JOIN atlas_global.universe_snapshot u ON u.instrument_id = m.instrument_id AND u.date = a.as_of_d
    LEFT JOIN atlas_global.technical_daily   t ON t.instrument_id = m.instrument_id AND t.date = a.as_of_d
    LEFT JOIN ranked r ON r.instrument_id = m.instrument_id
    WHERE m.is_active AND m.asset_class = 'stock'
    ORDER BY m.symbol
  `
}, 'stock-list')

/** Every active instrument of the class, ranked: the universe verdict, the classification, the
 *  score row with its on-read decile and peer rank, and the technicals at EOD. */
export async function getInstrumentList(assetClass: AssetClass): Promise<InstrumentList> {
  if (!dbAvailable) return { eod: null, as_of: '', scored_on: null, lenses: [], keys: [], cells: [] }
  const [rows, lenses] = await Promise.all([
    assetClass === 'etf' ? etfListInner() : stockListInner(),
    getLensWeights(assetClass),
  ])
  const first = rows[0]
  return {
    eod: first?.eod ?? null,
    as_of: first?.as_of ?? '',
    scored_on: first?.scored_on ?? null,
    lenses,
    ...packRows(rows.map(toInstrumentRow)),
  }
}

// ── one instrument's score, down to its sub-scores ──────────────────────────

/** Every lens and sub-score column of the journal row, as NUMERIC strings, plus the row's own
 *  evidence. Column names are the journal's; `src/lib/scores.ts` says which subs belong to which
 *  lens and what each is called in English. */
export type ScoreDetail = {
  /** The session the score is from — not necessarily the price EOD; the page prints both. */
  scored_on: string
  values: Record<string, string | null>
  conviction_tier: string | null
  peer_group: string | null
  lenses_active: number | null
  coverage_factor: string | null
  decile: number | null
  peer_rank: number | null
  peer_n: number | null
  evidence: unknown
  lenses: LensWeight[]
}

/** The rule that fired on the fund's registered name, and the words it matched. */
export type Classification = {
  strategy: string | null
  asset_class: string | null
  country_codes: string[] | null
  leveraged: boolean | null
  inverse: boolean | null
  hedged: boolean | null
  status: string
  classified_by: string
  valid_from: string
  evidence: unknown
}

type ScoreRow = Record<string, unknown>

const etfScoreRow = (symbol: string) => db()<ScoreRow[]>`
  ${db().unsafe(ANCHOR)},
  scored_on AS (
    SELECT MAX(s.date) AS d FROM atlas_global.etf_scores_daily s, a WHERE s.date <= a.as_of_d
  ),
    -- A fund whose whole asset class has fewer than atlas_thresholds.peer_group_min_members
    -- in-universe members gets peer_group = NULL from score_etfs (its assign_groups docstring
    -- says why there is nowhere further to fall). It is scored and listed; it is NOT ranked,
    -- because ntile(10) over six rows would print "decile 6 of 10" for sixth of six.
  ranked AS (
    SELECT s.*, s.peer_group AS cohort,
           CASE WHEN s.composite IS NULL OR s.peer_group IS NULL THEN NULL ELSE
             ntile(10) OVER (PARTITION BY s.date, s.peer_group, (s.composite IS NULL)
                             ORDER BY s.composite)
           END AS composite_decile,
           CASE WHEN s.composite IS NULL OR s.peer_group IS NULL THEN NULL ELSE
             rank() OVER (PARTITION BY s.date, s.peer_group, (s.composite IS NULL)
                          ORDER BY s.composite DESC)
           END AS peer_rank,
           CASE WHEN s.peer_group IS NULL THEN NULL ELSE
               count(s.composite) OVER (PARTITION BY s.date, s.peer_group) END AS peer_n
    FROM atlas_global.etf_scores_daily s
    WHERE s.date = (SELECT d FROM scored_on)
  )
  SELECT r.*, r.date::text AS scored_on
  FROM ranked r
  JOIN atlas_global.instrument_master m ON m.instrument_id = r.instrument_id
  WHERE m.is_active AND m.asset_class = 'etf' AND m.symbol = ${symbol}
  LIMIT 1
`

const stockScoreRow = (symbol: string) => db()<ScoreRow[]>`
  ${db().unsafe(ANCHOR)},
  scored_on AS (
    SELECT MAX(s.date) AS d FROM atlas_global.lens_scores_daily s, a
    WHERE s.date <= a.as_of_d AND s.asset_class = 'stock'
  ),
  ranked AS (
    SELECT s.*, s.cap_cohort AS cohort,
           CASE WHEN s.composite IS NULL THEN NULL ELSE
             ntile(10) OVER (PARTITION BY s.date, s.cap_cohort, (s.composite IS NULL)
                             ORDER BY s.composite)
           END AS composite_decile,
           CASE WHEN s.composite IS NULL THEN NULL ELSE
             rank() OVER (PARTITION BY s.date, s.cap_cohort, (s.composite IS NULL)
                          ORDER BY s.composite DESC)
           END AS peer_rank,
           count(s.composite) OVER (PARTITION BY s.date, s.cap_cohort) AS peer_n
    FROM atlas_global.lens_scores_daily s
    WHERE s.date = (SELECT d FROM scored_on) AND s.asset_class = 'stock'
  )
  SELECT r.*, r.date::text AS scored_on
  FROM ranked r
  JOIN atlas_global.instrument_master m ON m.instrument_id = r.instrument_id
  WHERE m.is_active AND m.asset_class = 'stock' AND m.symbol = ${symbol}
  LIMIT 1
`

// ntile / rank / count come back as bigint, which postgres.js hands over as text; NUMERIC scores
// are text too (no float ever touches a score). Number() at this one boundary, nothing computed.
const count = (v: unknown): number | null => (v == null ? null : Number(v))

// The decile is cut over the WHOLE scored population on that date, and this instrument's row is
// then picked out of it — never over a subset, which would make a fund's rank depend on which
// page asked. Same window as the list query, so the two surfaces cannot disagree.
type ScoreJournalRow = Omit<ScoreDetail, 'lenses'>

const scoreDetailInner = eodCached(async (assetClass: AssetClass, symbol: string): Promise<ScoreJournalRow | null> => {
  const rows = await (assetClass === 'etf' ? etfScoreRow(symbol) : stockScoreRow(symbol))
  const row = rows[0]
  if (!row) return null
  const values: Record<string, string | null> = {}
  for (const [k, v] of Object.entries(row)) {
    if (typeof v === 'string' || v === null) values[k] = v
  }
  return {
    scored_on: String(row.scored_on),
    values,
    conviction_tier: (row.conviction_tier as string | null) ?? null,
    peer_group: (row.cohort as string | null) ?? null,
    lenses_active: count(row.lenses_active),
    coverage_factor: (row.coverage_factor as string | null) ?? null,
    decile: count(row.composite_decile),
    peer_rank: count(row.peer_rank),
    peer_n: count(row.peer_n),
    evidence: row.evidence,
  }
}, 'score-detail')

/** One instrument's score with its decile, peer rank, evidence and the lens weights in force;
 *  null when it is not scored. The two reads are separate cache entries, and neither is nested
 *  inside the other's callback — an unstable_cache that wraps another is a cache nobody can reason
 *  about. */
export async function getScoreDetail(assetClass: AssetClass, symbol: string): Promise<ScoreDetail | null> {
  if (!dbAvailable) return null
  const [row, lenses] = await Promise.all([scoreDetailInner(assetClass, symbol), getLensWeights(assetClass)])
  return row && { ...row, lenses }
}

const classificationInner = eodCached(async (symbol: string): Promise<Classification | null> => {
  const rows = await db()<Classification[]>`
    SELECT c.strategy, c.asset_class, c.country_codes, c.leveraged, c.inverse, c.hedged,
           c.status, c.classified_by, c.valid_from::text AS valid_from, c.evidence
    FROM atlas_global.etf_classification c
    JOIN atlas_global.instrument_master m ON m.instrument_id = c.instrument_id
    WHERE m.is_active AND m.asset_class = 'etf' AND m.symbol = ${symbol}
    ORDER BY (c.valid_to IS NOT NULL), c.version DESC
    LIMIT 1
  `
  return rows[0] ?? null
}, 'etf-classification')

/** The current classification row for an ETF; null before classify_etfs.py has reached it. */
export async function getClassification(symbol: string): Promise<Classification | null> {
  if (!dbAvailable) return null
  return classificationInner(symbol)
}
