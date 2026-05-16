// Read-only query helpers for Atlas Strategy Lab.
// All NUMERIC columns returned as strings — parse at display time.
// Do NOT import or modify strategies.ts (different system).
import 'server-only'
import sql from '@/lib/db'

export type LeaderboardRow = {
  rank: number
  genome_id: string
  strategy_name: string
  promoted_at: Date
  sortino_oos: string | null
  calmar_oos: string | null
  alpha_30d: string | null
  regime_breakdown: Record<string, number> | null
  generation: number
}

export type InsightRow = {
  id: string
  generated_at: Date
  insight_bullets: string[]
  parameter_importance: Record<string, number>
  top_genome_deltas: Record<string, unknown>[]
}

export type GenePoolHealth = {
  active_count: number
  killed_count: number
  promoted_count: number
  last_born_at: Date | null
}

export type PortfolioConfigRow = {
  id: string
  created_at: Date
  config_json: Record<string, unknown>
  is_active: boolean
  label: string | null
}

export type GenomePositionRow = {
  date: Date
  ticker: string
  company_name: string | null
  position_type: string
  entry_date: Date
  entry_price: string
  shares: string
  current_value: string
  unrealized_pnl: string
  holding_days: number
  tax_status: string
  entry_signals: Record<string, unknown> | null
}

export async function getLeaderboard(): Promise<LeaderboardRow[]> {
  return sql<LeaderboardRow[]>`
    SELECT
      l.rank,
      l.genome_id::text,
      l.strategy_name,
      l.promoted_at,
      l.sortino_oos::text,
      l.calmar_oos::text,
      l.alpha_30d::text,
      l.regime_breakdown,
      g.generation
    FROM atlas_strategy_leaderboard l
    JOIN atlas_strategy_genomes g ON g.id = l.genome_id
    ORDER BY l.rank
  `
}

export async function getLatestInsights(): Promise<InsightRow | null> {
  const rows = await sql<InsightRow[]>`
    SELECT id::text, generated_at, insight_bullets, parameter_importance, top_genome_deltas
    FROM atlas_strategy_insights
    ORDER BY generated_at DESC
    LIMIT 1
  `
  return rows[0] ?? null
}

export async function getGenePoolHealth(): Promise<GenePoolHealth> {
  const rows = await sql<GenePoolHealth[]>`
    SELECT
      COUNT(*) FILTER (WHERE status = 'active')   AS active_count,
      COUNT(*) FILTER (WHERE status = 'killed')   AS killed_count,
      COUNT(*) FILTER (WHERE status = 'promoted') AS promoted_count,
      MAX(born_at)                                AS last_born_at
    FROM atlas_strategy_genomes
  `
  return rows[0] ?? { active_count: 0, killed_count: 0, promoted_count: 0, last_born_at: null }
}

export async function getGenomePositions(genomeId: string): Promise<GenomePositionRow[]> {
  return sql<GenomePositionRow[]>`
    SELECT
      p.date,
      u.ticker,
      u.company_name,
      p.position_type,
      p.entry_date,
      p.entry_price::text,
      p.shares::text,
      p.current_value::text,
      p.unrealized_pnl::text,
      p.holding_days,
      p.tax_status,
      p.entry_signals
    FROM atlas_strategy_positions_daily p
    JOIN atlas.atlas_universe_stocks u ON u.id = p.instrument_id
    WHERE p.genome_id = ${genomeId}
      AND p.date = (SELECT MAX(date) FROM atlas_strategy_positions_daily WHERE genome_id = ${genomeId})
    ORDER BY p.current_value DESC
  `
}

export async function getActivePortfolioConfig(): Promise<PortfolioConfigRow | null> {
  const rows = await sql<PortfolioConfigRow[]>`
    SELECT id::text, created_at, config_json, is_active, label
    FROM atlas_portfolio_config
    WHERE is_active = TRUE
    ORDER BY created_at DESC LIMIT 1
  `
  return rows[0] ?? null
}
