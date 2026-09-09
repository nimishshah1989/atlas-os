// src/lib/queries/series.ts — one instrument's PRICE HISTORY and its latest technical read.
// Reads ONLY atlas_global (the schema gate scans this directory): ohlcv_daily, technical_daily,
// instrument_master. Cached under the `eod` tag so the nightly publish flushes it.
//
// TWO CLOSES, TWO JOBS, AND THE PAGE SAYS WHICH IT IS SHOWING.
//   close_adj  is adjusted for SPLITS only. The EMAs, RSI, ATR and Bollinger width are computed on
//              it (compute_technicals.py, India's convention), so a chart that draws EMA-200 over
//              anything else is drawing two different series and calling them one.
//   close_tr   adds dividends. Every RETURN, every relative strength and every risk measure uses
//              it, because a fund's dividend is the holder's money and dropping it understates a
//              dividend-heavy fund by whole points a year.
// The chart therefore draws close_adj with its own EMAs, and the return calculator answers on
// close_tr — and each says so where it is read.
//
// SPY IS THE OVERLAY, REBASED, NOT REPRICED. Drawing SPY's dollar close beside a $40 fund would
// put the fund on the floor. Both series are indexed to 100 at the first session in the window,
// so the picture is "what a dollar did in each", which is the only comparison that means anything
// across two instruments at different prices.
//
// THE WINDOW IS SESSIONS, NOT CALENDAR DAYS. `LIMIT` over `ORDER BY date DESC` takes exactly the
// last N trading sessions the spine holds for THIS instrument, so a fund listed last year gets its
// whole life rather than an empty five-year frame.
import 'server-only'
import { eodCached } from '@/lib/cache'
import { db, dbAvailable } from '@/lib/db'

/** Roughly TEN years of sessions — the longest window the chart offers. Ranges shorter than this
 *  are cut from the same fetch in the browser, so switching range costs no round trip.
 *
 *  It is a ceiling, not a promise: `lastSessions` returns whatever the spine actually holds, so a
 *  fund listed in 2021 draws five years on the 10Y button and the axis says so. The spine's own
 *  reach is a separate question the chart's provenance line answers (BarsProvenance). */
export const MAX_SESSIONS = 2520

export type SeriesPoint = {
  date: string
  /** Split-adjusted close — what the EMAs below are computed on. */
  close_adj: string | null
  /** Total-return close — what every return is computed on. */
  close_tr: string | null
  ema_21: string | null
  ema_50: string | null
  ema_200: string | null
  volume: string | null
}

/** The latest technical_daily row, in the groups the page reads it in. Every field is nullable:
 *  a young instrument has no 200-day EMA and no 24-month relative strength, and the page prints an
 *  em dash rather than inventing one. */
export type TechnicalRead = {
  date: string
  price_basis: string
  ema_21: string | null
  ema_50: string | null
  ema_200: string | null
  above_ema_21: boolean | null
  above_ema_50: boolean | null
  above_ema_200: boolean | null
  rsi_14: string | null
  atr_14_pct: string | null
  bb_width: string | null
  pos_52w: string | null
  vol_ratio_30d: string | null
  ret_1w: string | null
  ret_1m: string | null
  ret_3m: string | null
  ret_6m: string | null
  ret_12m: string | null
  ret_24m: string | null
  ret_ytd: string | null
  rs_1w_spy: string | null
  rs_1m_spy: string | null
  rs_3m_spy: string | null
  rs_6m_spy: string | null
  rs_12m_spy: string | null
  rs_24m_spy: string | null
  vol_63d_ann: string | null
  vol_252d_ann: string | null
  downside_dev_63d: string | null
  mdd_12m: string | null
  mdd_36m: string | null
  beta_spy_252: string | null
  corr_spy_252: string | null
  sharpe_12m: string | null
  sortino_12m: string | null
  calmar_36m: string | null
  adv_usd_60d_median: string | null
}

export type InstrumentSeries = {
  /** This instrument's sessions, oldest first. */
  points: SeriesPoint[]
  /** SPY over the SAME dates, for the rebased overlay. Empty when the instrument IS SPY. */
  benchmark: { date: string; close_tr: string | null }[]
  technical: TechnicalRead | null
}

const BENCHMARK = 'SPY'

const inner = eodCached(async (symbol: string): Promise<InstrumentSeries> => {
  const sql = db()
  const points = await sql<SeriesPoint[]>`
    SELECT * FROM (
      SELECT o.date::text,
             o.close_adj::text, o.close_tr::text, o.volume::text,
             t.ema_21::text, t.ema_50::text, t.ema_200::text
      FROM atlas_global.ohlcv_daily o
      JOIN atlas_global.instrument_master m ON m.instrument_id = o.instrument_id
      LEFT JOIN atlas_global.technical_daily t
             ON t.instrument_id = o.instrument_id AND t.date = o.date
      WHERE m.symbol = ${symbol} AND m.is_active
      ORDER BY o.date DESC
      LIMIT ${MAX_SESSIONS}
    ) w ORDER BY date
  `
  if (points.length === 0) return { points: [], benchmark: [], technical: null }

  // The overlay is fetched over the instrument's OWN first date, not a fixed lookback: rebasing
  // needs both series to start on the same session or the index is a lie about the comparison.
  const benchmark =
    symbol === BENCHMARK
      ? []
      : await sql<{ date: string; close_tr: string | null }[]>`
          SELECT o.date::text, o.close_tr::text
          FROM atlas_global.ohlcv_daily o
          JOIN atlas_global.instrument_master m ON m.instrument_id = o.instrument_id
          WHERE m.symbol = ${BENCHMARK} AND m.is_active AND o.date >= ${points[0].date}::date
          ORDER BY o.date
        `

  const [technical] = await sql<TechnicalRead[]>`
    SELECT t.date::text, t.price_basis,
           t.ema_21::text, t.ema_50::text, t.ema_200::text,
           t.above_ema_21, t.above_ema_50, t.above_ema_200,
           t.rsi_14::text, t.atr_14_pct::text, t.bb_width::text, t.pos_52w::text,
           t.vol_ratio_30d::text,
           t.ret_1w::text, t.ret_1m::text, t.ret_3m::text, t.ret_6m::text,
           t.ret_12m::text, t.ret_24m::text, t.ret_ytd::text,
           t.rs_1w_spy::text, t.rs_1m_spy::text, t.rs_3m_spy::text, t.rs_6m_spy::text,
           t.rs_12m_spy::text, t.rs_24m_spy::text,
           t.vol_63d_ann::text, t.vol_252d_ann::text, t.downside_dev_63d::text,
           t.mdd_12m::text, t.mdd_36m::text, t.beta_spy_252::text, t.corr_spy_252::text,
           t.sharpe_12m::text, t.sortino_12m::text, t.calmar_36m::text,
           t.adv_usd_60d_median::text
    FROM atlas_global.technical_daily t
    JOIN atlas_global.instrument_master m ON m.instrument_id = t.instrument_id
    WHERE m.symbol = ${symbol} AND m.is_active
    ORDER BY t.date DESC
    LIMIT 1
  `
  return { points, benchmark, technical: technical ?? null }
}, 'instrument-series')

/** One instrument's sessions, SPY over the same dates, and its latest technical row. */
export async function getInstrumentSeries(symbol: string): Promise<InstrumentSeries> {
  if (!dbAvailable) return { points: [], benchmark: [], technical: null }
  return inner(symbol)
}
