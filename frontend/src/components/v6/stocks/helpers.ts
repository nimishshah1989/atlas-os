// frontend/src/components/v6/stocks/helpers.ts
// Shared pure helpers for the stocks landscape components.
// Extracted to avoid duplication between CompositeTrajectoriesGrid and SixPicksWorthClick.

import type { LandscapeRow } from '@/lib/queries/v6/stocks-landscape'

// ---------------------------------------------------------------------------
// pickSixStocks — canonical selection of 3 BUYs + 3 AVOIDs
// opts.requireTrajectory = true  → only rows with composite_trajectory_30d >= 2 pts
// opts.requireTrajectory = false → all rows with non-null composite_score
// ---------------------------------------------------------------------------

export function pickSixStocks(
  data: LandscapeRow[],
  opts?: { requireTrajectory?: boolean },
): LandscapeRow[] {
  const requireTraj = opts?.requireTrajectory ?? true

  const eligible = requireTraj
    ? data.filter(
        r => r.composite_trajectory_30d != null && r.composite_trajectory_30d.length >= 2,
      )
    : data.filter(r => r.composite_score != null)

  const buys = eligible
    .filter(r => r.action === 'BUY')
    .sort((a, b) => parseFloat(b.composite_score ?? '0') - parseFloat(a.composite_score ?? '0'))
    .slice(0, 3)

  const avoids = eligible
    .filter(r => r.action === 'AVOID')
    .sort((a, b) => parseFloat(a.composite_score ?? '0') - parseFloat(b.composite_score ?? '0'))
    .slice(0, 3)

  return [...buys, ...avoids]
}
