// SP04 Stage 4a — server-only queries over atlas_weight_proposals and
// the rolling-IC table that backs the admin review panel.
import 'server-only'
import sql from '@/lib/db'

export type ProposalStatus =
  | 'pending'
  | 'approved'
  | 'rejected'
  | 'snoozed'
  | 'superseded'

export type WeightDict = Record<string, string> // signal → numeric string

export type ProposalRow = {
  id: string
  tier: string
  regime: string
  proposed_weights: WeightDict
  current_weights: WeightDict
  proposed_holdout_ic: string | null
  current_holdout_ic: string | null
  ic_delta: string | null
  rationale: string | null
  generator_version: string
  status: ProposalStatus
  created_at: Date
}

export async function getPendingProposals(): Promise<ProposalRow[]> {
  return await sql<ProposalRow[]>`
    SELECT
      id::text                  AS id,
      tier,
      regime,
      proposed_weights,
      current_weights,
      proposed_holdout_ic::text AS proposed_holdout_ic,
      current_holdout_ic::text  AS current_holdout_ic,
      ic_delta::text            AS ic_delta,
      rationale,
      generator_version,
      status,
      created_at
    FROM atlas.atlas_weight_proposals
    WHERE status = 'pending'
    ORDER BY created_at DESC
    LIMIT 50
  `
}

export type ICSparklineRow = {
  as_of_date: Date
  ic: string
  t_stat: string | null
}

export async function getRollingICHistory(
  tier: string,
  signalName: string,
  nDays: number = 30,
): Promise<ICSparklineRow[]> {
  return await sql<ICSparklineRow[]>`
    SELECT
      as_of_date,
      ic::text     AS ic,
      t_stat::text AS t_stat
    FROM atlas.atlas_signal_ic_rolling
    WHERE tier = ${tier} AND signal_name = ${signalName}
      AND as_of_date >= CURRENT_DATE - ${nDays}::int
    ORDER BY as_of_date ASC
  `
}

export async function getRecentProposalsAllStatuses(
  limit: number = 20,
): Promise<ProposalRow[]> {
  return await sql<ProposalRow[]>`
    SELECT
      id::text                  AS id,
      tier,
      regime,
      proposed_weights,
      current_weights,
      proposed_holdout_ic::text AS proposed_holdout_ic,
      current_holdout_ic::text  AS current_holdout_ic,
      ic_delta::text            AS ic_delta,
      rationale,
      generator_version,
      status,
      created_at
    FROM atlas.atlas_weight_proposals
    ORDER BY created_at DESC
    LIMIT ${limit}
  `
}
