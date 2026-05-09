// src/lib/queries/backtests.ts
// Read-only SELECT helpers for atlas.strategy_backtest_results.
// NUMERIC columns kept as string — parse at display time.
import 'server-only'
import sql from '@/lib/db'

export type BacktestRow = {
  id: string
  strategy_id: string | null
  custom_portfolio_id: string | null
  backtest_type: string
  start_date: Date
  end_date: Date
  sharpe_ratio: string | null
  max_drawdown: string | null
  total_return: string | null
  alpha_vs_nifty500: string | null
  alpha_vs_naive_atlas: string | null
  walk_forward_oos_sharpe: string | null
  regime_breakdown: Record<string, { alpha: number; days: number }> | null
  created_at: Date
}

/** All backtests for a strategy, newest first. */
export async function getBacktestsForStrategy(
  strategyId: string,
  limit: number = 50,
): Promise<BacktestRow[]> {
  return sql<BacktestRow[]>`
    SELECT
      id,
      strategy_id,
      custom_portfolio_id,
      backtest_type,
      start_date,
      end_date,
      sharpe_ratio::text          AS sharpe_ratio,
      max_drawdown::text          AS max_drawdown,
      total_return::text          AS total_return,
      alpha_vs_nifty500::text     AS alpha_vs_nifty500,
      alpha_vs_naive_atlas::text  AS alpha_vs_naive_atlas,
      walk_forward_oos_sharpe::text AS walk_forward_oos_sharpe,
      regime_breakdown,
      created_at
    FROM atlas.strategy_backtest_results
    WHERE strategy_id = ${strategyId}
    ORDER BY created_at DESC
    LIMIT ${limit}
  `
}

/** Latest single backtest row for a strategy. Returns null if none exist. */
export async function getLatestBacktestForStrategy(
  strategyId: string,
): Promise<BacktestRow | null> {
  const rows = await sql<BacktestRow[]>`
    SELECT
      id,
      strategy_id,
      custom_portfolio_id,
      backtest_type,
      start_date,
      end_date,
      sharpe_ratio::text          AS sharpe_ratio,
      max_drawdown::text          AS max_drawdown,
      total_return::text          AS total_return,
      alpha_vs_nifty500::text     AS alpha_vs_nifty500,
      alpha_vs_naive_atlas::text  AS alpha_vs_naive_atlas,
      walk_forward_oos_sharpe::text AS walk_forward_oos_sharpe,
      regime_breakdown,
      created_at
    FROM atlas.strategy_backtest_results
    WHERE strategy_id = ${strategyId}
    ORDER BY created_at DESC
    LIMIT 1
  `
  return rows[0] ?? null
}
