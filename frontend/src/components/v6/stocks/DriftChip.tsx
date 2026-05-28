'use client'

// DriftChip — inline signal drift status badge for stock/ETF detail pages.
//
// Renders a colored pill showing the current drift state for an open signal call.
// Wired by Stream D into the stock detail page header (next to verdict block).
//
// Props:
//   status — drift classification from mv_stock_landscape_drift.drift_status
//   z      — latest Z-score from mv_stock_landscape_drift.drift_z (signed float)
//
// Status → visual mapping:
//   'within_band'       → teal  (|Z| ≤ 1.5)  "Within band"
//   'mild_drift'        → amber (1.5 < |Z| ≤ 2.0) "Mild drift ±Nσ"
//   'significant_drift' → red   (|Z| > 2.0)   "Drift — call is failing ±Nσ"
//   'no_data' / null    → renders nothing
//
// Design: inline-flex pill with 6px leading dot, 11px text, rounded-sm.
// Matches the Atlas v6 signal badge aesthetic (teal accents, wealth-mgmt palette).

export type DriftStatus =
  | 'within_band'
  | 'mild_drift'
  | 'significant_drift'
  | 'no_data'
  | null

export interface DriftChipProps {
  status: DriftStatus
  z: number | null
}

export function DriftChip({ status, z }: DriftChipProps) {
  if (status == null || status === 'no_data') return null

  if (status === 'within_band') {
    return (
      <span className="inline-flex items-center gap-1.5 px-2 py-0.5 text-[11px] bg-signal-pos/10 text-signal-pos rounded-sm font-medium">
        <span className="w-1.5 h-1.5 rounded-full bg-signal-pos" />
        Within band
      </span>
    )
  }

  const sign = z != null && z > 0 ? '+' : ''
  const sigmaLabel = z != null ? ` ${sign}${z.toFixed(1)}σ` : ''

  if (status === 'mild_drift') {
    return (
      <span className="inline-flex items-center gap-1.5 px-2 py-0.5 text-[11px] bg-signal-warn/10 text-signal-warn rounded-sm font-medium">
        <span className="w-1.5 h-1.5 rounded-full bg-signal-warn" />
        {'Mild drift'}
        {sigmaLabel}
      </span>
    )
  }

  // significant_drift
  return (
    <span className="inline-flex items-center gap-1.5 px-2 py-0.5 text-[11px] bg-signal-neg/10 text-signal-neg rounded-sm font-medium">
      <span className="w-1.5 h-1.5 rounded-full bg-signal-neg" />
      {'Drift — call is failing'}
      {sigmaLabel}
    </span>
  )
}
