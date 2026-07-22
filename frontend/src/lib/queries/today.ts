// ── Today (the Pulse change-feed) — "what changed overnight", conviction-ranked ──
//
// Aggregation-only over existing atlas_foundation nightly output: NO new tables,
// ingestion, or cron. Every number traces to a real produced row (RULE #0).
//
// Three reads power the /today modules:
//   getConvictionMoves() — diff composite/decile between the latest two trading days
//   getTodayCatalysts()  — the most recent day's exchange filings, tagged by conviction
//   getTodayMovers()     — EOD price change over the latest two trading days
//
//   T   = latest trading date, T-1 = the PRIOR DISTINCT trading date (holiday/weekend
//   safe — never `date - 1`). Deciles are cut within cap cohort PER DATE, exactly like
//   getStocksDecileList, so "entered D>=LEAD_DECILE" is apples-to-apples across days.
//
// Verified on the live DB 2026-07-22: atlas_lens_scores_daily holds 1875 trading days
// (2019-01-01 -> 2026-07-21), 498 stocks/day. The universe is Nifty 500, so movers are
// naturally liquid — no micro-cap noise.
import 'server-only'
import sql from '@/lib/db'
import { toNumber } from '@/lib/decimal'
import { LEAD_DECILE } from './stock_lens'

// The cap-cohort CTE, verbatim from getStockDecile / getStocksDecileList. Duplicated
// (not shared) to match the existing codebase convention and keep each query self-contained.
// large/mid/small by NSE index membership; everything else is micro.
const CAP_CTE = sql`
  cap AS (
    SELECT instrument_id,
      CASE WHEN bool_or(index_code='NIFTY 100') THEN 'large'
           WHEN bool_or(index_code='NIFTY MIDCAP 150') THEN 'mid'
           WHEN bool_or(index_code='NIFTY SMLCAP 250') THEN 'small' ELSE 'micro' END AS cap
    FROM atlas_foundation.de_index_constituents
    WHERE effective_to IS NULL AND index_code IN ('NIFTY 100','NIFTY MIDCAP 150','NIFTY SMLCAP 250')
    GROUP BY instrument_id
  )`

export type TodayDates = { asOf: string | null; prevOf: string | null }

// The latest two DISTINCT trading dates in the scored series (T, T-1). Both null when
// the pipeline has never run; prevOf null when only one day exists (empty-state guard).
export async function getTodayDates(): Promise<TodayDates> {
  const r = await sql<{ d: string }[]>`
    SELECT to_char(date,'YYYY-MM-DD') AS d
    FROM (SELECT DISTINCT date FROM atlas_foundation.atlas_lens_scores_daily WHERE asset_class='stock'
          ORDER BY date DESC LIMIT 2) z
    ORDER BY d DESC`
  return { asOf: r[0]?.d ?? null, prevOf: r[1]?.d ?? null }
}

// ── 1. Conviction moves ──────────────────────────────────────────────────────
export type ConvictionMove = {
  symbol: string; name: string | null; sector: string | null; cap: string
  dec_prev: number | null; dec_now: number | null
  comp_prev: number | null; comp_now: number | null; delta: number | null
}
export type ConvictionMoves = {
  asOf: string | null; prevOf: string | null
  entered: ConvictionMove[]   // crossed UP into leadership (D>=LEAD_DECILE)
  fellOut: ConvictionMove[]   // dropped OUT of leadership
  jumps: ConvictionMove[]     // biggest |composite| swings, either direction
}

const MOVE_LIMIT = 8

export async function getConvictionMoves(): Promise<ConvictionMoves> {
  const { asOf, prevOf } = await getTodayDates()
  if (!asOf || !prevOf) return { asOf, prevOf, entered: [], fellOut: [], jumps: [] }

  // Decile is cut within (date, cap) so each day ranks against its own cohort. Join the
  // two days per instrument; classify + sort in JS (498 rows is trivial to return whole).
  const rows = await sql<Record<string, string>[]>`
    WITH ${CAP_CTE},
    scored AS (
      SELECT l.date, l.instrument_id, im.symbol, im.name, im.sector,
             COALESCE(c.cap,'micro') AS cap, l.composite::float AS comp,
             CASE WHEN l.composite IS NULL THEN NULL
                  ELSE ntile(10) OVER (PARTITION BY l.date, COALESCE(c.cap,'micro'), (l.composite IS NULL) ORDER BY l.composite) END AS dec
      FROM atlas_foundation.atlas_lens_scores_daily l
      JOIN atlas_foundation.instrument_master im ON im.instrument_id = l.instrument_id
      LEFT JOIN cap c ON c.instrument_id = l.instrument_id
      WHERE l.asset_class='stock' AND l.date IN (${asOf}::date, ${prevOf}::date)
    )
    SELECT n.symbol, n.name, n.sector, n.cap,
           p.dec AS dec_prev, n.dec AS dec_now,
           p.comp AS comp_prev, n.comp AS comp_now
    FROM scored n
    JOIN scored p ON p.instrument_id = n.instrument_id AND p.date = ${prevOf}::date
    WHERE n.date = ${asOf}::date`

  const n = (v: string | null) => (v == null ? null : toNumber(v))
  const moves: ConvictionMove[] = rows.map(r => {
    const comp_prev = n(r.comp_prev), comp_now = n(r.comp_now)
    return {
      symbol: r.symbol, name: r.name, sector: r.sector, cap: r.cap,
      dec_prev: n(r.dec_prev), dec_now: n(r.dec_now),
      comp_prev, comp_now,
      delta: comp_prev == null || comp_now == null ? null : comp_now - comp_prev,
    }
  })

  const led = (d: number | null) => d != null && d >= LEAD_DECILE
  const entered = moves
    .filter(m => !led(m.dec_prev) && led(m.dec_now))
    .sort((a, b) => (b.delta ?? 0) - (a.delta ?? 0))
    .slice(0, MOVE_LIMIT)
  const fellOut = moves
    .filter(m => led(m.dec_prev) && !led(m.dec_now))
    .sort((a, b) => (a.delta ?? 0) - (b.delta ?? 0))
    .slice(0, MOVE_LIMIT)
  const jumps = moves
    .filter(m => m.delta != null)
    .sort((a, b) => Math.abs(b.delta!) - Math.abs(a.delta!))
    .slice(0, MOVE_LIMIT)

  return { asOf, prevOf, entered, fellOut, jumps }
}

// ── 2. Catalysts today ───────────────────────────────────────────────────────
export type TodayCatalyst = {
  date: string; category: string | null; bucket: string | null; priority: string | null
  subject: string | null; url: string | null
  symbol: string | null; name: string | null
  composite: number | null; decile: number | null; liked: boolean
}

const CATALYST_LIMIT = 15
const CATALYST_WINDOW_DAYS = 60

// The most recent exchange filings (trailing CATALYST_WINDOW_DAYS), tagged with each
// name's current Atlas conviction (composite + within-cohort decile) so the "★ liked"
// names stand out. Recency-first: newest filings lead, priority + conviction break ties.
//
// A trailing window (not "just the latest day") because the catalyst feed runs sparse —
// a single day often carries 0-2 filings, so a one-day cut would leave the module empty.
// Each row shows its own date, which also makes feed staleness visible rather than hidden.
export async function getTodayCatalysts(): Promise<{ catalysts: TodayCatalyst[]; asOf: string | null; total: number }> {
  const rows = await sql<Record<string, string>[]>`
    WITH latest AS (SELECT max(filing_date) AS d FROM atlas_foundation.lens_filings),
    lens_latest AS (SELECT max(date) AS d FROM atlas_foundation.atlas_lens_scores_daily WHERE asset_class='stock'),
    ${CAP_CTE},
    ln AS (
      SELECT l.instrument_id, l.composite::float AS comp,
             CASE WHEN l.composite IS NULL THEN NULL
                  ELSE ntile(10) OVER (PARTITION BY COALESCE(c.cap,'micro'), (l.composite IS NULL) ORDER BY l.composite) END AS dec
      FROM atlas_foundation.atlas_lens_scores_daily l
      LEFT JOIN cap c ON c.instrument_id = l.instrument_id
      WHERE l.asset_class='stock' AND l.date=(SELECT d FROM lens_latest)
    )
    SELECT to_char(f.filing_date,'YYYY-MM-DD') AS date, f.category, f.category_bucket AS bucket,
           f.signal_priority AS priority, f.subject_text AS subject, f.source_url AS url,
           im.symbol, im.name, ln.comp AS composite, ln.dec AS decile
    FROM atlas_foundation.lens_filings f
    JOIN atlas_foundation.instrument_master im ON im.instrument_id = f.instrument_id
    LEFT JOIN ln ON ln.instrument_id = f.instrument_id
    WHERE f.filing_date >= (SELECT d FROM latest) - (${CATALYST_WINDOW_DAYS} || ' days')::interval
    ORDER BY f.filing_date DESC,
             CASE upper(f.signal_priority) WHEN 'HIGH' THEN 0 WHEN 'MEDIUM' THEN 1 ELSE 2 END,
             ln.dec DESC NULLS LAST, f.nse_seq_id DESC`

  const n = (v: string | null) => (v == null ? null : toNumber(v))
  const catalysts: TodayCatalyst[] = rows.slice(0, CATALYST_LIMIT).map(r => {
    const decile = n(r.decile)
    return {
      date: r.date, category: r.category, bucket: r.bucket, priority: r.priority,
      subject: r.subject, url: r.url, symbol: r.symbol, name: r.name,
      composite: n(r.composite), decile, liked: decile != null && decile >= LEAD_DECILE,
    }
  })
  return { catalysts, asOf: rows[0]?.date ?? null, total: rows.length }
}

// ── 3. Movers ────────────────────────────────────────────────────────────────
export type Mover = { symbol: string; name: string | null; close: number | null; pct: number | null }

const MOVER_LIMIT = 8

// EOD price change over the latest two trading days, scoped to the SCORED universe
// (Nifty 500) so the list is liquid by construction. Gainers = top, losers = bottom.
export async function getTodayMovers(): Promise<{ gainers: Mover[]; losers: Mover[]; asOf: string | null }> {
  const rows = await sql<Record<string, string>[]>`
    WITH dts AS (SELECT DISTINCT date d FROM atlas_foundation.ohlcv_stock ORDER BY d DESC LIMIT 2),
    t_now AS (SELECT max(d) d FROM dts), t_prev AS (SELECT min(d) d FROM dts),
    scored AS (
      SELECT instrument_id FROM atlas_foundation.atlas_lens_scores_daily
      WHERE asset_class='stock'
        AND date=(SELECT max(date) FROM atlas_foundation.atlas_lens_scores_daily WHERE asset_class='stock')
    ),
    px AS (
      SELECT o.instrument_id, im.symbol, im.name,
        max(o.close) FILTER (WHERE o.date=(SELECT d FROM t_now))  AS c_now,
        max(o.close) FILTER (WHERE o.date=(SELECT d FROM t_prev)) AS c_prev
      FROM atlas_foundation.ohlcv_stock o
      JOIN atlas_foundation.instrument_master im ON im.instrument_id = o.instrument_id
      WHERE o.instrument_id IN (SELECT instrument_id FROM scored)
        AND o.date IN ((SELECT d FROM t_now),(SELECT d FROM t_prev)) AND o.close > 0
      GROUP BY o.instrument_id, im.symbol, im.name
    )
    SELECT symbol, name, to_char((SELECT d FROM t_now),'YYYY-MM-DD') AS as_of,
           c_now AS close, (c_now - c_prev) / c_prev * 100 AS pct
    FROM px
    WHERE c_now IS NOT NULL AND c_prev IS NOT NULL AND c_prev > 0
    ORDER BY pct DESC`

  const n = (v: string | null) => (v == null ? null : toNumber(v))
  const all: Mover[] = rows.map(r => ({ symbol: r.symbol, name: r.name, close: n(r.close), pct: n(r.pct) }))
  const asOf = rows[0]?.as_of ?? null
  return {
    gainers: all.slice(0, MOVER_LIMIT),
    losers: all.slice(-MOVER_LIMIT).reverse(),
    asOf,
  }
}
