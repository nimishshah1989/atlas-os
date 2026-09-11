// src/lib/queries/baskets.ts — the basket product's reads and its ONE write (create).
// Reads ONLY atlas_global (the schema gate scans this directory): basket_master,
// basket_constituents, basket_trades, basket_nav_daily, instrument_master, benchmark_master,
// ohlcv_daily, atlas_thresholds.
//
// NOT cached under the `eod` tag on purpose: a basket is created during the day and its page
// must show the new row at once, then its first mark minutes later when the worker has booked
// it (scripts/global_market/basket_job_worker.py). The root layout is force-dynamic.
//
// NUMERICs are selected as text and rendered as text (src/lib/format.ts); the only numbers here
// are the chart's series and the window metrics, which are display arithmetic over floats the
// same way India's portfolio pages do it. Every figure on a page is a stored row — the NAV, the
// cash, the fills — computed by mark_baskets.py, never here. The two ratios computed in SQL
// (since-inception, vs SPY in the relative form (1+r)/(1+b) − 1) are arithmetic over stored
// rows in NUMERIC, not floats.
import 'server-only'
import type { Constituent, DraftLimits, ParsedDraft, ResolvedInstrument, Suggestion } from '@/lib/basketDraft'
import { db, dbAvailable } from '@/lib/db'

export type BasketSummary = {
  id: string
  name: string
  kind: 'etf' | 'country' | 'stock'
  created_by: string
  initial_capital: string | null
  inception_date: string | null
  current_version: number
  n_constituents: number
  /** The latest live NAV row, or nulls while the worker has not booked the basket yet. */
  nav_date: string | null
  nav: string | null
  cash: string | null
  n_positions: number | null
  /** nav / initial_capital − 1, as a NUMERIC fraction string. */
  since_inception: string | null
  /** SPY close_tr[latest NAV date] / close_tr[first NAV date] − 1. */
  spy_since_inception: string | null
  /** (1 + r) / (1 + b) − 1 — the board's relative form (ADR-0002). */
  vs_spy: string | null
}

const SUMMARY_SQL = `
  SELECT m.basket_id::text AS id, m.name, m.kind, m.created_by,
         m.initial_capital::text AS initial_capital,
         m.inception_date::text AS inception_date,
         m.current_version,
         (SELECT count(*) FROM atlas_global.basket_constituents c
           WHERE c.basket_id = m.basket_id AND c.version = m.current_version)::int AS n_constituents,
         ln.date::text AS nav_date, ln.nav::text AS nav, ln.cash::text AS cash, ln.n_positions,
         CASE WHEN ln.nav IS NOT NULL AND m.initial_capital > 0
              THEN (ln.nav / m.initial_capital - 1)::text END AS since_inception,
         spy.ret::text AS spy_since_inception,
         CASE WHEN ln.nav IS NOT NULL AND m.initial_capital > 0 AND spy.ret IS NOT NULL
              THEN ((ln.nav / m.initial_capital) / (1 + spy.ret) - 1)::text END AS vs_spy
  FROM atlas_global.basket_master m
  LEFT JOIN LATERAL (
    SELECT date, nav, cash, n_positions FROM atlas_global.basket_nav_daily n
    WHERE n.basket_id = m.basket_id AND n.run_type = 'live' ORDER BY date DESC LIMIT 1
  ) ln ON true
  LEFT JOIN LATERAL (
    SELECT min(date) AS date FROM atlas_global.basket_nav_daily n
    WHERE n.basket_id = m.basket_id AND n.run_type = 'live'
  ) fn ON true
  LEFT JOIN LATERAL (
    SELECT (l.close_tr / f.close_tr - 1) AS ret
    FROM atlas_global.benchmark_master b
    JOIN LATERAL (SELECT close_tr FROM atlas_global.ohlcv_daily o
                  WHERE o.instrument_id = b.instrument_id AND o.date <= fn.date AND o.close_tr IS NOT NULL
                  ORDER BY o.date DESC LIMIT 1) f ON true
    JOIN LATERAL (SELECT close_tr FROM atlas_global.ohlcv_daily o
                  WHERE o.instrument_id = b.instrument_id AND o.date <= ln.date AND o.close_tr IS NOT NULL
                  ORDER BY o.date DESC LIMIT 1) l ON true
    WHERE b.code = m.benchmark_code AND fn.date IS NOT NULL AND ln.date IS NOT NULL AND f.close_tr > 0
  ) spy ON true
  WHERE m.status = 'active'`

/** Every active basket, newest first. */
export async function listBaskets(): Promise<BasketSummary[]> {
  if (!dbAvailable) return []
  return db()<BasketSummary[]>`${db().unsafe(SUMMARY_SQL)} ORDER BY m.created_at DESC, m.basket_id`
}

export type ConstituentRow = {
  instrument_id: string
  symbol: string
  name: string | null
  asset_class: string
  target_weight_frac: string
}

export type HoldingRow = {
  instrument_id: string
  symbol: string
  name: string | null
  asset_class: string
  /** basket_constituents.target_weight_frac for the current version, or null if the name left it. */
  target_weight_frac: string | null
  qty: string
  entry_date: string | null
  fill_price: string | null
  /** The last real print on or before the latest NAV date: close_adj, or close_tr on an archive row. */
  last_price: string | null
  last_date: string | null
  /** Total return since entry (close_tr ratio; close_adj where close_tr is NULL), a fraction. */
  ret_since_entry: string | null
  /** qty × fill × (1 + ret_since_entry) — what the NAV carries this name at. */
  value: string | null
}

export type TradeRow = {
  date: string
  symbol: string
  side: 'buy' | 'sell'
  qty: string
  price: string
  value: string
  cost: string | null
  reason: string
  rationale: string | null
  run_type: string
  version: number | null
}

export type NavPoint = { d: string; nav: number }
export type BenchPoint = { d: string; close_tr: number }

export type BasketDetail = {
  summary: BasketSummary
  constituents: ConstituentRow[]
  holdings: HoldingRow[]
  /** Live NAV rows, oldest first (empty until the worker has booked the basket). */
  nav: NavPoint[]
  /** The benchmark's close_tr over the NAV dates, for the growth-of-100 comparison. */
  bench: BenchPoint[]
  trades: TradeRow[]
}

const HOLDINGS_SQL = `
  WITH latest AS (
    SELECT max(date) AS d FROM atlas_global.basket_nav_daily WHERE basket_id = $1::uuid AND run_type = 'live'
  ),
  pos AS (
    SELECT t.instrument_id, t.symbol, t.asset_class,
           sum(CASE WHEN t.side = 'buy' THEN t.qty ELSE -t.qty END) AS qty,
           max(t.trade_date) FILTER (WHERE t.side = 'buy') AS entry
    FROM atlas_global.basket_trades t
    WHERE t.basket_id = $1::uuid AND t.run_type = 'live'
    GROUP BY 1, 2, 3
    HAVING sum(CASE WHEN t.side = 'buy' THEN t.qty ELSE -t.qty END) <> 0
  )
  SELECT p.instrument_id::text AS instrument_id, p.symbol, im.name, p.asset_class,
         c.target_weight_frac::text AS target_weight_frac,
         p.qty::text AS qty, p.entry::text AS entry_date, e.price::text AS fill_price,
         coalesce(x.close_adj, x.close_tr)::text AS last_price, x.date::text AS last_date,
         r.ratio::text AS ret_since_entry_plus_one,
         (p.qty * e.price * r.ratio)::text AS value
  FROM pos p
  JOIN atlas_global.instrument_master im ON im.instrument_id = p.instrument_id
  JOIN atlas_global.basket_master m ON m.basket_id = $1::uuid
  LEFT JOIN atlas_global.basket_constituents c
         ON c.basket_id = m.basket_id AND c.version = m.current_version AND c.instrument_id = p.instrument_id
  LEFT JOIN LATERAL (
    SELECT t.price, o.close_tr, o.close_adj
    FROM atlas_global.basket_trades t
    LEFT JOIN atlas_global.ohlcv_daily o ON o.instrument_id = t.instrument_id AND o.date = t.trade_date
    WHERE t.basket_id = $1::uuid AND t.run_type = 'live' AND t.instrument_id = p.instrument_id
      AND t.side = 'buy' AND t.trade_date = p.entry
    ORDER BY t.trade_id DESC LIMIT 1
  ) e ON true
  LEFT JOIN LATERAL (
    SELECT o.date, o.close_tr, o.close_adj
    FROM atlas_global.ohlcv_daily o CROSS JOIN latest
    WHERE o.instrument_id = p.instrument_id AND o.date <= coalesce(latest.d, o.date)
      AND (o.close_tr IS NOT NULL OR o.close_adj IS NOT NULL)
    ORDER BY o.date DESC LIMIT 1
  ) x ON true
  LEFT JOIN LATERAL (
    SELECT CASE WHEN e.close_tr IS NOT NULL AND x.close_tr IS NOT NULL THEN x.close_tr / e.close_tr
                WHEN e.close_adj IS NOT NULL AND x.close_adj IS NOT NULL THEN x.close_adj / e.close_adj
           END AS ratio
  ) r ON true
  ORDER BY p.qty * e.price * r.ratio DESC NULLS LAST, p.symbol`

type HoldingDbRow = Omit<HoldingRow, 'ret_since_entry'> & { ret_since_entry_plus_one: string | null }

// "1.0523" − 1 on the string, so the fraction never passes through a double.
function minusOne(ratio: string | null): string | null {
  if (ratio == null) return null
  const negative = ratio.startsWith('-')
  if (negative) return null // a ratio of prices is never negative; a sign here is a data fault
  const [i, f = ''] = ratio.split('.')
  const whole = BigInt(i)
  if (whole >= 1n) return `${whole - 1n}${f ? '.' + f : ''}`
  // 0.9xx → −0.0yy: subtract from 1 on the fraction digits
  const scale = 10n ** BigInt(f.length || 1)
  const frac = f ? BigInt(f) : 0n
  const diff = scale - frac // (1 − 0.f) × scale
  return `-0.${diff.toString().padStart(f.length || 1, '0')}`
}

/** One basket with everything its page shows, or null when the id is not an active basket. */
export async function getBasket(id: string): Promise<BasketDetail | null> {
  if (!dbAvailable) return null
  if (!/^[0-9a-f-]{36}$/i.test(id)) return null
  const sql = db()
  const summaries = await sql<BasketSummary[]>`${sql.unsafe(SUMMARY_SQL)} AND m.basket_id = ${id}::uuid`
  const summary = summaries[0]
  if (!summary) return null
  const [constituents, holdingRows, nav, trades] = await Promise.all([
    sql<ConstituentRow[]>`
      SELECT c.instrument_id::text AS instrument_id, im.symbol, im.name, im.asset_class,
             c.target_weight_frac::text AS target_weight_frac
      FROM atlas_global.basket_constituents c
      JOIN atlas_global.instrument_master im USING (instrument_id)
      WHERE c.basket_id = ${id}::uuid AND c.version = ${summary.current_version}
      ORDER BY c.target_weight_frac DESC, im.symbol`,
    sql.unsafe<HoldingDbRow[]>(HOLDINGS_SQL, [id]),
    sql<NavPoint[]>`
      SELECT date::text AS d, nav::float8 AS nav FROM atlas_global.basket_nav_daily
      WHERE basket_id = ${id}::uuid AND run_type = 'live' ORDER BY date`,
    sql<TradeRow[]>`
      SELECT trade_date::text AS date, symbol, side, qty::text AS qty, price::text AS price,
             value::text AS value, cost::text AS cost, reason, rationale, run_type, version
      FROM atlas_global.basket_trades
      WHERE basket_id = ${id}::uuid
      ORDER BY trade_date DESC, trade_id DESC LIMIT 400`,
  ])
  const bench =
    nav.length > 0
      ? await sql<BenchPoint[]>`
          SELECT o.date::text AS d, o.close_tr::float8 AS close_tr
          FROM atlas_global.ohlcv_daily o
          JOIN atlas_global.benchmark_master b ON b.instrument_id = o.instrument_id
          JOIN atlas_global.basket_master m ON m.benchmark_code = b.code
          WHERE m.basket_id = ${id}::uuid AND o.close_tr IS NOT NULL
            AND o.date BETWEEN ${nav[0].d}::date AND ${nav[nav.length - 1].d}::date
          ORDER BY o.date`
      : []
  const holdings: HoldingRow[] = holdingRows.map(({ ret_since_entry_plus_one, ...h }) => ({
    ...h,
    ret_since_entry: minusOne(ret_since_entry_plus_one),
  }))
  return { summary, constituents, holdings, nav, bench, trades }
}

// ── the builder's inputs and its one write ──────────────────────────────────

const LIMIT_KEYS = {
  basket_default_capital_usd: 'defaultCapitalUsd',
  basket_max_position_pct: 'maxPositionFrac',
  basket_min_weight_frac: 'minWeightFrac',
} as const

/** The three M2 thresholds the builder validates against. Throws naming any missing row. */
export async function getBasketLimits(): Promise<DraftLimits> {
  const rows = await db()<{ threshold_key: keyof typeof LIMIT_KEYS; threshold_value: string }[]>`
    SELECT threshold_key, threshold_value::text AS threshold_value
    FROM atlas_global.atlas_thresholds
    WHERE is_active AND threshold_key IN ('basket_default_capital_usd', 'basket_max_position_pct', 'basket_min_weight_frac')`
  const found = new Map(rows.map((r) => [r.threshold_key, r.threshold_value]))
  const missing = (Object.keys(LIMIT_KEYS) as (keyof typeof LIMIT_KEYS)[]).filter((k) => !found.has(k))
  if (missing.length)
    throw new Error(
      `atlas_global.atlas_thresholds is missing ${missing.join(', ')} — run scripts/global_market/seed_thresholds.py (FM approval first); there are no defaults.`,
    )
  return {
    defaultCapitalUsd: found.get('basket_default_capital_usd')!,
    maxPositionFrac: found.get('basket_max_position_pct')!,
    minWeightFrac: found.get('basket_min_weight_frac')!,
  }
}

/** Every ACTIVE instrument whose symbol is in the list (one per symbol by the partial unique index). */
export async function resolveSymbols(symbols: string[]): Promise<ResolvedInstrument[]> {
  if (symbols.length === 0) return []
  return db()<ResolvedInstrument[]>`
    SELECT instrument_id::text AS instrument_id, symbol, asset_class, name, is_active, fractionable
    FROM atlas_global.instrument_master
    WHERE is_active AND symbol = ANY(${symbols}::text[])`
}

/** The symbol box's suggestions: active instruments of the basket's kind whose symbol starts with
 *  the text, or whose name contains it, symbol matches first, with the universe verdict at the
 *  latest snapshot. Bounded to a dozen — a suggestion list is a shortlist, not a directory. */
export async function searchInstruments(q: string, kind: 'etf' | 'stock', limit = 12): Promise<Suggestion[]> {
  const needle = q.trim().toUpperCase().replace(/[%_\\]/g, '')
  if (!needle) return []
  return db()<Suggestion[]>`
    SELECT m.symbol, m.name, u.in_universe
    FROM atlas_global.instrument_master m
    LEFT JOIN LATERAL (
      SELECT s.in_universe FROM atlas_global.universe_snapshot s
      WHERE s.instrument_id = m.instrument_id ORDER BY s.date DESC LIMIT 1
    ) u ON true
    WHERE m.is_active AND m.asset_class = ${kind}
      AND (m.symbol LIKE ${needle + '%'} OR upper(m.name) LIKE ${'%' + needle + '%'})
    ORDER BY (m.symbol LIKE ${needle + '%'}) DESC, (u.in_universe IS TRUE) DESC, length(m.symbol), m.symbol
    LIMIT ${limit}`
}

/** The latest SPY session — the inception date a new basket is stamped with; null with no bars. */
export async function latestSession(): Promise<string | null> {
  const rows = await db()<{ d: string | null }[]>`
    SELECT max(o.date)::text AS d
    FROM atlas_global.ohlcv_daily o
    JOIN atlas_global.instrument_master m ON m.instrument_id = o.instrument_id
    WHERE m.symbol = 'SPY' AND m.is_active`
  return rows[0]?.d ?? null
}

/** basket_master + basket_constituents in ONE transaction; returns the new basket_id. Nothing
 *  else is written here — the fills and the NAV are mark_baskets.py's (via the worker). */
export async function insertBasket(
  draft: ParsedDraft,
  constituents: Constituent[],
  createdBy: string,
  inceptionDate: string | null,
): Promise<string> {
  const id = await db().begin(async (tx) => {
    const [row] = await tx<{ id: string }[]>`
      INSERT INTO atlas_global.basket_master
        (name, kind, status, current_version, initial_capital, inception_date, benchmark_code, created_by)
      VALUES (${draft.name}, ${draft.kind}, 'active', 1, ${draft.capital}::numeric, ${inceptionDate}::date, 'SPY', ${createdBy})
      RETURNING basket_id::text AS id`
    for (const c of constituents) {
      await tx`
        INSERT INTO atlas_global.basket_constituents
          (basket_id, version, instrument_id, target_weight_frac, effective_from)
        VALUES (${row.id}::uuid, 1, ${c.instrument_id}::uuid, ${c.weight_frac}::numeric,
                coalesce(${inceptionDate}::date, (now() AT TIME ZONE 'America/New_York')::date))`
    }
    return row.id
  })
  return id as string
}
