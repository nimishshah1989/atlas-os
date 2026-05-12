// SP04 Stage 4c — server-only queries against the live-perf + revert
// audit tables. Used by /admin/weight-performance and by the revert
// banner on /admin/composite-proposals.
import 'server-only'
import sql from '@/lib/db'

export type LivePerfRow = {
  weight_set_version: string
  as_of_date: Date
  realized_ic: string
  ic_ratio: string | null
  n_observations: number
}

export type ActiveSetSummary = {
  tier: string
  regime: string
  version: string
  predicted_ic: string | null
  trail: LivePerfRow[]
  days_below_threshold: number
  n_trail_rows: number
  in_revert_territory: boolean
}

export type RevertLogRow = {
  id: string
  tier: string
  regime: string
  reverted_from_version: string
  restored_to_version: string | null
  days_below_threshold: number
  realized_ic_avg: string | null
  predicted_holdout_ic: string | null
  triggered_by: string
  notes: string | null
  applied_at: Date
}

export type HitRateRow = {
  instrument_id: string
  date: Date
  lookback_window: number
  n_high_conviction_days: number
  n_positive_outcomes: number
  hit_rate: string | null
  tier_at_as_of: string | null
}

export async function getActiveWeightSetsWithTrail(): Promise<ActiveSetSummary[]> {
  // Pull active sets + their trails in one round trip via two queries.
  type ActiveRow = {
    tier: string
    regime: string
    version: string
    predicted_ic: string | null
  }
  const actives = await sql<ActiveRow[]>`
    SELECT tier, regime,
           tier || '@' || MAX(approved_at)::text AS version,
           MAX(holdout_ic)::text                  AS predicted_ic
    FROM atlas.atlas_signal_weights
    WHERE effective_to IS NULL
    GROUP BY tier, regime
    ORDER BY tier
  `
  const out: ActiveSetSummary[] = []
  for (const a of actives) {
    const trail = await sql<LivePerfRow[]>`
      SELECT
        weight_set_version,
        as_of_date,
        realized_ic::text AS realized_ic,
        ic_ratio::text    AS ic_ratio,
        n_observations
      FROM atlas.atlas_signal_weights_live_perf
      WHERE weight_set_version = ${a.version}
        AND as_of_date >= CURRENT_DATE - INTERVAL '30 days'
      ORDER BY as_of_date ASC
    `
    const daysBelow = trail.filter(
      (t) => t.ic_ratio !== null && parseFloat(t.ic_ratio) < 0.5,
    ).length
    out.push({
      tier: a.tier,
      regime: a.regime,
      version: a.version,
      predicted_ic: a.predicted_ic,
      trail,
      days_below_threshold: daysBelow,
      n_trail_rows: trail.length,
      in_revert_territory: trail.length >= 60 && daysBelow === trail.length,
    })
  }
  return out
}

export async function getRecentReverts(): Promise<RevertLogRow[]> {
  return await sql<RevertLogRow[]>`
    SELECT
      id::text                  AS id,
      tier,
      regime,
      reverted_from_version,
      restored_to_version,
      days_below_threshold,
      realized_ic_avg::text     AS realized_ic_avg,
      predicted_holdout_ic::text AS predicted_holdout_ic,
      triggered_by,
      notes,
      applied_at
    FROM atlas.atlas_weight_revert_log
    WHERE applied_at >= NOW() - INTERVAL '30 days'
    ORDER BY applied_at DESC
  `
}

export async function getHitRateForStock(
  instrumentId: string,
  lookback: number = 20,
): Promise<HitRateRow | null> {
  const rows = await sql<HitRateRow[]>`
    SELECT
      instrument_id::text       AS instrument_id,
      date,
      lookback_window,
      n_high_conviction_days,
      n_positive_outcomes,
      hit_rate::text            AS hit_rate,
      tier_at_as_of
    FROM atlas.atlas_stock_hit_rate_daily
    WHERE instrument_id = ${instrumentId}::uuid
      AND lookback_window = ${lookback}
    ORDER BY date DESC
    LIMIT 1
  `
  return rows[0] ?? null
}
