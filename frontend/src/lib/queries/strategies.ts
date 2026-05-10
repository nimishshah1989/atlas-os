// src/lib/queries/strategies.ts
// Read-only SELECT helpers for atlas.strategy_configs.
// Systematic strategies only: is_fm_authored = FALSE.
// NUMERIC columns kept as string — parse at display time.
import 'server-only'
import sql from '@/lib/db'

export type StrategyRow = {
  id: string
  name: string
  tier: string
  archetype: string
  variant: string
  config: Record<string, unknown>
  is_active: boolean
  is_fm_authored: boolean
  created_by: string | null
  created_at: Date
  updated_at: Date
  // Computed: any rows in strategy_paper_portfolios → paper active
  paper_active: boolean
  // Latest backtest KPIs (may be null if no backtest yet)
  latest_sharpe: string | null
  latest_alpha_vs_nifty500: string | null
  latest_backtest_at: Date | null
}

export type StrategyDetailRow = {
  id: string
  name: string
  tier: string
  archetype: string
  variant: string
  config: Record<string, unknown>
  description: string | null
  is_active: boolean
  is_fm_authored: boolean
  created_by: string | null
  created_at: Date
  updated_at: Date
  paper_active: boolean
}

export type StrategyConfigRow = {
  id: string
  config: Record<string, unknown>
}

/** All systematic strategies with their latest backtest KPIs + paper-active flag. */
export async function getAllStrategies(filter?: {
  tier?: string
  archetype?: string
  paperActive?: boolean
}): Promise<StrategyRow[]> {
  const tier = filter?.tier ?? null
  const archetype = filter?.archetype ?? null
  const paperActive = filter?.paperActive ?? null

  return sql<StrategyRow[]>`
    SELECT
      sc.id,
      sc.name,
      sc.tier,
      sc.archetype,
      sc.variant,
      sc.config,
      sc.is_active,
      sc.is_fm_authored,
      sc.created_by,
      sc.created_at,
      sc.updated_at,
      (
        SELECT COUNT(*) > 0
        FROM atlas.strategy_paper_portfolios pp
        WHERE pp.strategy_id = sc.id
      ) AS paper_active,
      bt.sharpe_ratio::text           AS latest_sharpe,
      bt.alpha_vs_nifty500::text      AS latest_alpha_vs_nifty500,
      bt.created_at                   AS latest_backtest_at
    FROM atlas.strategy_configs sc
    LEFT JOIN LATERAL (
      SELECT sharpe_ratio, alpha_vs_nifty500, created_at
      FROM atlas.strategy_backtest_results
      WHERE strategy_id = sc.id
      ORDER BY created_at DESC
      LIMIT 1
    ) bt ON TRUE
    WHERE sc.is_fm_authored = FALSE
      AND (${tier}::text IS NULL OR sc.tier = ${tier}::text)
      AND (${archetype}::text IS NULL OR sc.archetype = ${archetype}::text)
      AND (
        ${paperActive}::boolean IS NULL
        OR (
          ${paperActive}::boolean = TRUE
          AND EXISTS (
            SELECT 1 FROM atlas.strategy_paper_portfolios pp WHERE pp.strategy_id = sc.id
          )
        )
        OR (
          ${paperActive}::boolean = FALSE
          AND NOT EXISTS (
            SELECT 1 FROM atlas.strategy_paper_portfolios pp WHERE pp.strategy_id = sc.id
          )
        )
      )
    ORDER BY sc.tier, sc.name
  `
}

/** Single strategy detail row. Returns null if not found or is FM-authored. */
export async function getStrategyById(id: string): Promise<StrategyDetailRow | null> {
  const rows = await sql<StrategyDetailRow[]>`
    SELECT
      sc.id,
      sc.name,
      sc.tier,
      sc.archetype,
      sc.variant,
      sc.config,
      sc.config->>'description'           AS description,
      sc.is_active,
      sc.is_fm_authored,
      sc.created_by,
      sc.created_at,
      sc.updated_at,
      (
        SELECT COUNT(*) > 0
        FROM atlas.strategy_paper_portfolios pp
        WHERE pp.strategy_id = sc.id
      ) AS paper_active
    FROM atlas.strategy_configs sc
    WHERE sc.id = ${id}
      AND sc.is_fm_authored = FALSE
  `
  return rows[0] ?? null
}

/** Config JSONB only — used by ConfigJSONViewer. */
export async function getStrategyConfig(id: string): Promise<StrategyConfigRow | null> {
  const rows = await sql<StrategyConfigRow[]>`
    SELECT id, config
    FROM atlas.strategy_configs
    WHERE id = ${id}
  `
  return rows[0] ?? null
}
