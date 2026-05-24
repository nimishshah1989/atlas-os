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

export type StaticInstrument = {
  instrument_id: string
  instrument_type: 'stock' | 'etf' | 'fund'
  weight_pct: number
  // Task 3.5: target weight per holding. null = no target set (render "—", never fake 0).
  target_weight_pct: number | null
  // Task 3.5: enriched from atlas_universe_stocks for display + compliance checks.
  // null when the instrument_id is not found in the universe (ETF/fund without a universe row).
  symbol: string | null
  // 'Unknown' when the instrument_id is not found in the universe (e.g. ETF/fund).
  sector: string
  // True if not in Nifty 100 and not in Nifty 500 (small-cap definition matching compliance.py).
  is_small_cap: boolean
  // Task 3.6: current Weinstein engine state from atlas_stock_signal_unified.
  // null for ETFs/funds/unclassified stocks. Used for deterioration surfacing.
  engine_state: string | null
}

export type StaticPortfolioDetail = {
  id: string
  name: string
  instruments: Array<StaticInstrument>
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

/** Single static portfolio detail + latest backtest KPIs. Returns null if not found.
 *
 * Task 3.5: instruments array is enriched with target_weight_pct, sector, is_small_cap
 * by joining each JSONB element against atlas_universe_stocks (most-recent snapshot per
 * instrument_id). Non-universe instruments (ETFs, funds, missing IDs) fall back to
 * sector='Unknown' and is_small_cap=false — safe for compliance checks.
 *
 * Task 3.6: instruments array further enriched with engine_state from
 * atlas_stock_signal_unified (latest row per instrument_id). Null for ETFs/funds
 * not in the signal table. Used for deterioration surfacing.
 */
export async function getStaticPortfolioById(
  id: string,
): Promise<StaticPortfolioDetail | null> {
  const rows = await sql<StaticPortfolioDetail[]>`
    SELECT
      p.id,
      p.name,
      (
        SELECT jsonb_agg(
          elem || jsonb_build_object(
            'symbol',       u.symbol,
            'sector',       COALESCE(u.sector, 'Unknown'),
            'is_small_cap', (u.in_nifty_100 IS NOT TRUE AND u.in_nifty_500 IS NOT TRUE),
            'engine_state', ss.engine_state
          )
        )
        FROM jsonb_array_elements(p.instruments) AS elem
        LEFT JOIN LATERAL (
          -- Portfolio holdings mix stock instruments (uuid ids) and fund
          -- instruments (string ids like "F00001G6N8"). Compare as text so a
          -- fund id never gets cast to ::uuid (which would raise a SQL error).
          SELECT symbol, sector, in_nifty_100, in_nifty_500
          FROM atlas.atlas_universe_stocks
          WHERE instrument_id::text = elem->>'instrument_id'
          ORDER BY effective_from DESC
          LIMIT 1
        ) u ON TRUE
        LEFT JOIN LATERAL (
          SELECT engine_state
          FROM atlas.atlas_stock_signal_unified
          WHERE instrument_id::text = elem->>'instrument_id'
          ORDER BY date DESC
          LIMIT 1
        ) ss ON TRUE
      )                               AS instruments,
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
