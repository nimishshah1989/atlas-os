// src/lib/queries/portfolios.ts
// Read-only SELECT helpers for FM custom portfolios.
// Unions Static (strategy_fm_custom_portfolios) + Rule-Based (strategy_configs WHERE is_fm_authored=TRUE).
// NUMERIC columns kept as string — parse at display time.
import 'server-only'
import sql from '@/lib/db'

export type PortfolioListRow = {
  id: string
  name: string
  type: 'static' | 'rule-based'
  // For static: count of instruments in JSONB array. For rule-based: null (placeholder).
  instrument_count: number | null
  latest_sharpe: string | null
  paper_trading_active: boolean
  created_at: Date
}

export type StaticPortfolioDetail = {
  id: string
  name: string
  instruments: Array<{
    instrument_id: string
    instrument_type: 'stock' | 'etf' | 'fund'
    weight_pct: number
  }>
  backtest_id: string | null
  paper_trading_active: boolean
  created_at: Date
  updated_at: Date
  // Latest backtest KPIs
  latest_sharpe: string | null
  latest_max_drawdown: string | null
  latest_alpha_vs_nifty500: string | null
}

export type RuleBasedPortfolioDetail = {
  id: string
  name: string
  config: Record<string, unknown>
  is_active: boolean
  created_by: string | null
  created_at: Date
  updated_at: Date
  // Latest backtest KPIs
  latest_sharpe: string | null
  latest_max_drawdown: string | null
  latest_alpha_vs_nifty500: string | null
  latest_backtest_id: string | null
}

export type BacktestListRow = {
  id: string
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

/** Unioned list of static + rule-based FM portfolios with latest backtest Sharpe. */
export async function getAllPortfolios(): Promise<PortfolioListRow[]> {
  return sql<PortfolioListRow[]>`
    SELECT
      p.id,
      p.name,
      'static'::text                        AS type,
      jsonb_array_length(p.instruments)     AS instrument_count,
      bt.sharpe_ratio::text                 AS latest_sharpe,
      p.paper_trading_active,
      p.created_at
    FROM atlas.strategy_fm_custom_portfolios p
    LEFT JOIN LATERAL (
      SELECT sharpe_ratio
      FROM atlas.strategy_backtest_results
      WHERE custom_portfolio_id = p.id
      ORDER BY created_at DESC
      LIMIT 1
    ) bt ON TRUE

    UNION ALL

    SELECT
      sc.id,
      sc.name,
      'rule-based'::text                    AS type,
      NULL::int                             AS instrument_count,
      bt.sharpe_ratio::text                 AS latest_sharpe,
      FALSE                                 AS paper_trading_active,
      sc.created_at
    FROM atlas.strategy_configs sc
    LEFT JOIN LATERAL (
      SELECT sharpe_ratio
      FROM atlas.strategy_backtest_results
      WHERE strategy_id = sc.id
      ORDER BY created_at DESC
      LIMIT 1
    ) bt ON TRUE
    WHERE sc.is_fm_authored = TRUE

    ORDER BY created_at DESC
  `
}

/** Single static portfolio detail + latest backtest KPIs. Returns null if not found. */
export async function getStaticPortfolioById(
  id: string,
): Promise<StaticPortfolioDetail | null> {
  const rows = await sql<StaticPortfolioDetail[]>`
    SELECT
      p.id,
      p.name,
      p.instruments,
      p.backtest_id,
      p.paper_trading_active,
      p.created_at,
      p.updated_at,
      bt.sharpe_ratio::text           AS latest_sharpe,
      bt.max_drawdown::text           AS latest_max_drawdown,
      bt.alpha_vs_nifty500::text      AS latest_alpha_vs_nifty500
    FROM atlas.strategy_fm_custom_portfolios p
    LEFT JOIN LATERAL (
      SELECT sharpe_ratio, max_drawdown, alpha_vs_nifty500
      FROM atlas.strategy_backtest_results
      WHERE custom_portfolio_id = p.id
      ORDER BY created_at DESC
      LIMIT 1
    ) bt ON TRUE
    WHERE p.id = ${id}
  `
  return rows[0] ?? null
}

/** Single rule-based portfolio detail (from strategy_configs) + latest backtest KPIs. */
export async function getRuleBasedPortfolioById(
  id: string,
): Promise<RuleBasedPortfolioDetail | null> {
  const rows = await sql<RuleBasedPortfolioDetail[]>`
    SELECT
      sc.id,
      sc.name,
      sc.config,
      sc.is_active,
      sc.created_by,
      sc.created_at,
      sc.updated_at,
      bt.sharpe_ratio::text           AS latest_sharpe,
      bt.max_drawdown::text           AS latest_max_drawdown,
      bt.alpha_vs_nifty500::text      AS latest_alpha_vs_nifty500,
      bt.id::text                     AS latest_backtest_id
    FROM atlas.strategy_configs sc
    LEFT JOIN LATERAL (
      SELECT id, sharpe_ratio, max_drawdown, alpha_vs_nifty500
      FROM atlas.strategy_backtest_results
      WHERE strategy_id = sc.id
      ORDER BY created_at DESC
      LIMIT 1
    ) bt ON TRUE
    WHERE sc.id = ${id}
      AND sc.is_fm_authored = TRUE
  `
  return rows[0] ?? null
}

/**
 * All backtests for a portfolio. Routes by type:
 * - 'static' uses custom_portfolio_id
 * - 'rule-based' uses strategy_id
 */
export async function getBacktestsForPortfolio(
  id: string,
  type: 'static' | 'rule-based',
  limit: number = 50,
): Promise<BacktestListRow[]> {
  if (type === 'static') {
    return sql<BacktestListRow[]>`
      SELECT
        id,
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
      WHERE custom_portfolio_id = ${id}
      ORDER BY created_at DESC
      LIMIT ${limit}
    `
  }
  return sql<BacktestListRow[]>`
    SELECT
      id,
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
    WHERE strategy_id = ${id}
    ORDER BY created_at DESC
    LIMIT ${limit}
  `
}
