// src/lib/queries/paper_perf.ts
// Read-only SELECT helpers for paper performance + paper trades.
// NUMERIC columns kept as string — parse at display time.
import 'server-only'
import sql from '@/lib/db'

export type PaperPerfRow = {
  id: string
  strategy_id: string
  date: Date
  total_value: string
  daily_return: string
  benchmark_nifty500_return: string | null
  benchmark_naive_atlas_return: string | null
  regime: string
  positions_count: number
}

export type PaperTradeRow = {
  id: string
  strategy_id: string
  instrument_id: string
  instrument_type: string
  action: string
  signal_type: string
  price: string
  weight_pct: string
  notional_value: string
  trade_date: Date
  regime_at_trade: string
  created_at: Date
}

/**
 * Daily paper performance series for equity curve + drawdown.
 * If since is provided, returns only rows on or after that date.
 */
export async function getPaperPerformance(
  strategyId: string,
  since?: Date,
): Promise<PaperPerfRow[]> {
  const sinceDate = since ?? null
  return sql<PaperPerfRow[]>`
    SELECT
      id,
      strategy_id,
      date,
      total_value::text                       AS total_value,
      daily_return::text                      AS daily_return,
      benchmark_nifty500_return::text         AS benchmark_nifty500_return,
      benchmark_naive_atlas_return::text      AS benchmark_naive_atlas_return,
      regime,
      positions_count
    FROM atlas.strategy_paper_performance
    WHERE strategy_id = ${strategyId}
      AND (${sinceDate}::date IS NULL OR date >= ${sinceDate}::date)
    ORDER BY date ASC
  `
}

/** Most recent paper trades for a strategy. */
export async function getRecentPaperTrades(
  strategyId: string,
  limit: number = 20,
): Promise<PaperTradeRow[]> {
  return sql<PaperTradeRow[]>`
    SELECT
      id,
      strategy_id,
      instrument_id,
      instrument_type,
      action,
      signal_type,
      price::text           AS price,
      weight_pct::text      AS weight_pct,
      notional_value::text  AS notional_value,
      trade_date,
      regime_at_trade,
      created_at
    FROM atlas.strategy_paper_trades
    WHERE strategy_id = ${strategyId}
    ORDER BY trade_date DESC, created_at DESC
    LIMIT ${limit}
  `
}
