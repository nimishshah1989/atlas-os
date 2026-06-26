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
      FROM foundation_staging.atlas_market_regime_daily
      ORDER BY date DESC
      LIMIT 1
    `,
    sql<HistoryRow[]>`
      SELECT
        date::text                          AS date,
        pct_above_ema_50::text              AS pct_above_ema_50,
        regime_state
      FROM foundation_staging.atlas_market_regime_daily
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

// ---------------------------------------------------------------------------
// RegimeDetail — enriched type for the /regime hero (D.9)
// ---------------------------------------------------------------------------

export type RegimeJourneyPoint = {
  date: string
  regime_state: string
}

export type RegimeInputRow = {
  date: string
  smallcap_rs_z: number | null
  breadth_pct_above_200dma: number | null
  vix_percentile: number | null
  cross_sectional_dispersion: number | null
}

export type RegimeDetail = {
  /** Regime label — may be 'Cautious', 'Risk-On', etc. Pass through as-is. */
  regime_state: string
  /** Raw Decimal string e.g. "0.7000" — may be null if row absent. */
  deployment_multiplier: string | null
  /** Number of consecutive trading days in the current regime. */
  days_in_regime: number
  /**
   * 5-day flip probability — column absent on atlas_market_regime_daily.
   * Always null in v6.0; UI renders "—".
   */
  flip_probability_5d: string | null
  /** Last 12 weeks (84d) of regime history, oldest → newest. */
  journey: RegimeJourneyPoint[]
  /** Last 12 weeks (84d) of driver input sparkline data, oldest → newest. */
  inputs: RegimeInputRow[]
  /** ISO date string of the most-recent row. */
  as_of: string | null
}

type DetailRow = {
  date: string
  regime_state: string
  deployment_multiplier: string | null
  smallcap_rs_z: string | null
  breadth_pct_above_200dma: string | null
  vix_percentile: string | null
  cross_sectional_dispersion: string | null
}

/**
 * Return enriched regime detail for the /regime hero.
 *
 * days_in_regime is derived in-process from the ordered history rows —
 * count consecutive rows (newest → oldest) that share the current regime_state.
 *
 * flip_probability_5d is always null (column not present on table in v6.0).
 */
export async function getRegimeDetail(): Promise<RegimeDetail> {
  // Fetch 84 days (12 weeks) to cover journey strip + input sparklines.
  // A second fetch of the latest row isn't needed — first row of the 84d
  // window (DESC order) is the latest.
  // Real columns on atlas_market_regime_daily (verified 2026-05-26):
  // - pct_above_ema_200       — breadth proxy
  // - india_vix               — VIX absolute (percentile computed in TS layer)
  // - realized_vol_5d_nifty500 — vol proxy for dispersion
  // No native smallcap_rs_z column — returns null; UI renders "—" gracefully.
  const rows = await sql<DetailRow[]>`
    SELECT
      date::text                              AS date,
      regime_state,
      deployment_multiplier::text             AS deployment_multiplier,
      NULL::text                              AS smallcap_rs_z,
      pct_above_ema_200::text                 AS breadth_pct_above_200dma,
      india_vix::text                         AS vix_percentile,
      realized_vol_5d_nifty500::text          AS cross_sectional_dispersion
    FROM foundation_staging.atlas_market_regime_daily
    ORDER BY date DESC
    LIMIT 84
  `

  if (rows.length === 0) {
    return {
      regime_state: 'Neutral',
      deployment_multiplier: null,
      days_in_regime: 0,
      flip_probability_5d: null,
      journey: [],
      inputs: [],
      as_of: null,
    }
  }

  const latest = rows[0]
  const currentState = latest.regime_state

  // Compute contiguous streak: rows are DESC; count while regime_state matches.
  let streak = 0
  for (const row of rows) {
    if (row.regime_state === currentState) {
      streak++
    } else {
      break
    }
  }

  // Reverse to oldest → newest for journey strip + sparklines.
  const ascending = rows.slice().reverse()

  const journey: RegimeJourneyPoint[] = ascending.map(r => ({
    date: r.date,
    regime_state: r.regime_state,
  }))

  const inputs: RegimeInputRow[] = ascending.map(r => ({
    date: r.date,
    smallcap_rs_z: r.smallcap_rs_z != null ? Number(r.smallcap_rs_z) : null,
    breadth_pct_above_200dma: r.breadth_pct_above_200dma != null
      ? Number(r.breadth_pct_above_200dma)
      : null,
    vix_percentile: r.vix_percentile != null ? Number(r.vix_percentile) : null,
    cross_sectional_dispersion: r.cross_sectional_dispersion != null
      ? Number(r.cross_sectional_dispersion)
      : null,
  }))

  return {
    regime_state: currentState,
    deployment_multiplier: latest.deployment_multiplier,
    days_in_regime: streak,
    flip_probability_5d: null,
    journey,
    inputs,
    as_of: latest.date,
  }
}
