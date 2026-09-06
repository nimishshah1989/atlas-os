// src/lib/queries/instruments.ts — the facts surfaces: /etfs, /stocks and their detail pages.
// Reads ONLY atlas_global (the schema gate scans this directory): instrument_master, index_membership,
// symbol_alias, ohlcv_daily, technical_daily, universe_snapshot. Every query is cached under the
// `eod` tag (src/lib/cache.ts) so the nightly publish flushes these pages.
//
// The anchor is the latest SPY session on or before today's New York date — SPY's bars define the
// calendar (atlas/global_market/calendar.py; freshness_guard.py anchors the same way). With no SPY
// bar at all there is no price session: membership is then read as of today and `eod` is null.
import 'server-only'
import { eodCached } from '@/lib/cache'
import { db, dbAvailable } from '@/lib/db'
import {
  packRows,
  toInstrumentRow,
  type AssetClass,
  type BarsRow,
  type InstrumentDbRow,
  type MembershipInterval,
  type PackedRows,
} from '@/lib/facts'

// One row: eod (text, null with no SPY bar), as_of (text) and as_of_d (date) = eod, else today.
const ANCHOR = `
  WITH today AS (SELECT (now() AT TIME ZONE 'America/New_York')::date AS d),
  anchor AS (
    SELECT (SELECT MAX(o.date) FROM atlas_global.ohlcv_daily o
             JOIN atlas_global.instrument_master m ON m.instrument_id = o.instrument_id
             WHERE m.symbol = 'SPY' AND m.is_active AND o.date <= today.d) AS eod,
           today.d AS today
    FROM today
  ),
  a AS (SELECT eod::text AS eod, COALESCE(eod, today)::text AS as_of, COALESCE(eod, today) AS as_of_d FROM anchor)`

type Anchor = { eod: string | null; as_of: string }

// Membership at the anchor date. effective_to is EXCLUSIVE: the member is out on that date.
const MEMBERSHIP_COLUMNS = `
  EXISTS (SELECT 1 FROM atlas_global.index_membership im
          WHERE im.instrument_id = m.instrument_id AND im.index_code = 'SP500'
            AND im.effective_from <= a.as_of_d AND (im.effective_to IS NULL OR im.effective_to > a.as_of_d)) AS sp500,
  (SELECT im.weight_frac::text FROM atlas_global.index_membership im
   WHERE im.instrument_id = m.instrument_id AND im.index_code = 'SP500' AND im.source = 'ssga' AND im.effective_to IS NULL
   ORDER BY im.effective_from DESC LIMIT 1) AS spy_weight`

// ── the explorer list ───────────────────────────────────────────────────────

/** The anchor and every row, packed (src/lib/facts.ts expandRows restores InstrumentRow[]). */
export type InstrumentList = Anchor & PackedRows

const listInner = eodCached(async (assetClass: AssetClass): Promise<InstrumentList> => {
  const rows = await db()<(InstrumentDbRow & Anchor)[]>`
    ${db().unsafe(ANCHOR)}
    SELECT
      m.symbol, m.name, m.exchange, m.asset_class, m.listing_date::text AS listing_date,
      m.cik, m.series_id, m.class_id, m.sector_gics,
      ${db().unsafe(MEMBERSHIP_COLUMNS)},
      o.close_adj::text            AS price_adj,
      t.ret_1m::text               AS ret_1m,
      t.ret_3m::text               AS ret_3m,
      t.ret_6m::text               AS ret_6m,
      t.ret_12m::text              AS ret_12m,
      t.rs_3m_spy::text            AS rs_3m_spy,
      t.pos_52w::text              AS pos_52w,
      t.adv_usd_60d_median::text   AS adv_usd,
      u.in_universe,
      u.exclusion_reason           AS universe_exclusion,
      a.eod, a.as_of
    FROM atlas_global.instrument_master m
    CROSS JOIN a
    LEFT JOIN atlas_global.technical_daily t   ON t.instrument_id = m.instrument_id AND t.date = a.as_of_d
    LEFT JOIN atlas_global.universe_snapshot u ON u.instrument_id = m.instrument_id AND u.date = a.as_of_d
    LEFT JOIN atlas_global.ohlcv_daily o       ON o.instrument_id = m.instrument_id AND o.date = a.as_of_d
    WHERE m.is_active AND m.asset_class = ${assetClass}
    ORDER BY m.symbol
  `
  const first = rows[0]
  return { eod: first?.eod ?? null, as_of: first?.as_of ?? '', ...packRows(rows.map(toInstrumentRow)) }
}, 'instrument-list')

/** Every active instrument of the class with its facts and the price-derived columns at EOD. */
export async function getInstrumentList(assetClass: AssetClass): Promise<InstrumentList> {
  if (!dbAvailable) return { eod: null, as_of: '', keys: [], cells: [] }
  return listInner(assetClass)
}

// ── one instrument ──────────────────────────────────────────────────────────

export type InstrumentFacts = {
  symbol: string
  name: string | null
  exchange: string | null
  asset_class: AssetClass
  listing_date: string | null
  cik: string | null
  series_id: string | null
  class_id: string | null
  sector_gics: string | null
  source: string
  /** ISO instant (UTC) of instrument_master.updated_at — build_identity's freshness signal. */
  updated_at: string
  sp500: boolean
  spy_weight: string | null
}

export type SymbolAlias = {
  source: string
  source_symbol: string
  valid_from: string
  valid_to: string | null
  note: string | null
}

export type InstrumentDetail = Anchor & {
  facts: InstrumentFacts
  aliases: SymbolAlias[]
  membership: MembershipInterval[]
  bars: BarsRow[]
}

const detailInner = eodCached(async (assetClass: AssetClass, symbol: string): Promise<InstrumentDetail | null> => {
  const found = await db()<(InstrumentFacts & Anchor & { instrument_id: string })[]>`
    ${db().unsafe(ANCHOR)}
    SELECT
      m.instrument_id::text AS instrument_id,
      m.symbol, m.name, m.exchange, m.asset_class,
      m.listing_date::text  AS listing_date,
      m.cik, m.series_id, m.class_id, m.sector_gics, m.source,
      to_char(m.updated_at AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"') AS updated_at,
      ${db().unsafe(MEMBERSHIP_COLUMNS)},
      a.eod, a.as_of
    FROM atlas_global.instrument_master m
    CROSS JOIN a
    WHERE m.is_active AND m.asset_class = ${assetClass} AND m.symbol = ${symbol}
    LIMIT 1
  `
  const row = found[0]
  if (!row) return null
  const { instrument_id, eod, as_of, ...facts } = row
  const [aliases, membership, bars] = await Promise.all([
    db()<SymbolAlias[]>`
      SELECT source, source_symbol, valid_from::text AS valid_from, valid_to::text AS valid_to, note
      FROM atlas_global.symbol_alias
      WHERE instrument_id = ${instrument_id}::uuid
      ORDER BY source, valid_from
    `,
    db()<MembershipInterval[]>`
      SELECT index_code, effective_from::text AS effective_from, effective_to::text AS effective_to,
             weight_frac::text AS weight_frac, source
      FROM atlas_global.index_membership
      WHERE instrument_id = ${instrument_id}::uuid
      ORDER BY effective_from, source
    `,
    db()<BarsRow[]>`
      SELECT source, adjustment_source,
             MIN(date)::text        AS first_date,
             MAX(date)::text        AS last_date,
             COUNT(*)::int          AS sessions,
             COUNT(close_adj)::int  AS adjusted,
             COUNT(close_tr)::int   AS total_return
      FROM atlas_global.ohlcv_daily
      WHERE instrument_id = ${instrument_id}::uuid
      GROUP BY source, adjustment_source
      ORDER BY first_date
    `,
  ])
  return { eod, as_of, facts, aliases, membership, bars }
}, 'instrument-detail')

/** One active instrument by class and symbol with its identity, membership and bars; null if absent. */
export async function getInstrumentDetail(assetClass: AssetClass, symbol: string): Promise<InstrumentDetail | null> {
  if (!dbAvailable) return null
  return detailInner(assetClass, symbol)
}
