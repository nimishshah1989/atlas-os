'use client'

// frontend/src/components/v6/DriftWarnChip.tsx
//
// Reusable drift-status chip for v6 hero panels.
//
// Renders:
//   healthy    → null (silent, no element)
//   drift_warn → amber chip "⚠ Drift flagged · maintainer reviewing" (bg-signal-warn)
//   deprecated → red chip "Deprecated · do not act on new signals" (bg-signal-neg)
//
// Wraps with InfoTooltip on hover per A.6 pattern.
// ARIA labels are distinct per variant.
//
// LOC budget: ≤100

import type { DriftStatus } from '@/lib/queries/v6/cells'
import { InfoTooltip } from '@/components/ui/InfoTooltip'

export interface DriftWarnChipProps {
  driftStatus: DriftStatus | null
  className?: string
}

const DRIFT_WARN_TOOLTIP =
  "This cell's realized excess is diverging from its locked prediction. Methodology team is reviewing. Position remains open; no automatic action."

const DEPRECATED_TOOLTIP =
  "This cell has been deprecated. Historical signal calls are preserved for audit, but no new signals are generated. Do not act on this cell."

export function DriftWarnChip({ driftStatus, className = '' }: DriftWarnChipProps) {
  if (driftStatus === null || driftStatus === 'healthy') {
    return null
  }

  if (driftStatus === 'drift_warn') {
    return (
      <span
        className={[
          'inline-flex items-center gap-1 px-[7px] py-[3px] rounded-[2px]',
          'bg-signal-warn/20 text-signal-warn',
          'font-sans text-[11px] font-semibold uppercase tracking-[0.08em]',
          className,
        ]
          .filter(Boolean)
          .join(' ')}
        role="status"
        aria-label="Drift warning: maintainer reviewing this cell"
      >
        <span aria-hidden="true">&#9888;</span>
        Drift flagged &middot; maintainer reviewing
        <InfoTooltip content={DRIFT_WARN_TOOLTIP} />
      </span>
    )
  }

  if (driftStatus === 'deprecated') {
    return (
      <span
        className={[
          'inline-flex items-center gap-1 px-[7px] py-[3px] rounded-[2px]',
          'bg-signal-neg/20 text-signal-neg',
          'font-sans text-[11px] font-semibold uppercase tracking-[0.08em]',
          className,
        ]
          .filter(Boolean)
          .join(' ')}
        role="status"
        aria-label="Deprecated: do not act on new signals from this cell"
      >
        Deprecated &middot; do not act on new signals
        <InfoTooltip content={DEPRECATED_TOOLTIP} />
      </span>
    )
  }

  // Unknown status — fail safe (silent)
  return null
}

export default DriftWarnChip
