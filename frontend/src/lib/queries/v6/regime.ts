// frontend/src/lib/queries/v6/regime.ts
//
// Direct Supabase query for the market regime indicator + history strip.
//
// Source:
//   atlas_market_regime_daily ← regime_state / deployment_multiplier
//                                pct_above_ema_50 / breadth + history (last 60d)
//
// Returns MarketRegime consumed by /regime and /v6/today pages. cells_favored
// is empty pending the regime→cell-archetype mapping migration.

import 'server-only'
import sql from '@/lib/db'
import type { MarketRegime } from '@/lib/api/v1'

type LatestRow = {
  date: string
  regime_state: string
  deployment_multiplier: string | null
  pct_above_ema_50: string | null
  pct_in_strong_states: string | null
  pct_weinstein_pass: string | null
}

type HistoryRow = {
  date: string
  pct_above_ema_50: string | null
  regime_state: string
}

/**
 * Return the latest regime row plus 60d history strip.
 *
 * deployment_pct is `deployment_multiplier * 100` — the UI shows e.g. "40%"
 * when the multiplier is 0.40.
 */
export async function getCurrentRegime(): Promise<MarketRegime> {
  const [latestRows, historyRows] = await Promise.all([
    sql<LatestRow[]>`
      SELECT
        date::text                          AS date,
        regime_state,
        deployment_multiplier::text         AS deployment_multiplier,
        pct_above_ema_50::text              AS pct_above_ema_50,
        pct_in_strong_states::text          AS pct_in_strong_states,
        pct_weinstein_pass::text            AS pct_weinstein_pass
      FROM atlas.atlas_market_regime_daily
      ORDER BY date DESC
      LIMIT 1
    `,
    sql<HistoryRow[]>`
      SELECT
        date::text                          AS date,
        pct_above_ema_50::text              AS pct_above_ema_50,
        regime_state
      FROM atlas.atlas_market_regime_daily
      ORDER BY date DESC
      LIMIT 60
    `,
  ])

  const latest = latestRows[0]
  if (!latest) {
    return {
      regime_state: 'Neutral',
      deployment_pct: 50,
      pct_above_ema_50: null,
      net_stage_2_5d: null,
      participation: null,
      history: [],
      cells_favored: [],
    }
  }

  const deploymentPct = latest.deployment_multiplier != null
    ? Math.round(Number(latest.deployment_multiplier) * 100)
    : 50

  return {
    regime_state: latest.regime_state,
    deployment_pct: deploymentPct,
    pct_above_ema_50: latest.pct_above_ema_50 != null ? Number(latest.pct_above_ema_50) : null,
    net_stage_2_5d: null,
    participation: latest.pct_in_strong_states != null
      ? Number(latest.pct_in_strong_states)
      : null,
    history: historyRows
      .slice()
      .reverse() // oldest → newest for the sparkline
      .map(h => ({
        date: h.date,
        pct_above_ema_50: h.pct_above_ema_50 != null ? Number(h.pct_above_ema_50) : null,
        regime_state: h.regime_state,
      })),
    cells_favored: [],
  }
}
