// frontend/src/components/v6/PositionSizingWidget.tsx
//
// Renders the position-sizing recommendation on the stock detail hero.
// Consumes B.1 HoldingState (passed server-side) and B.5 computeSizing (pure fn).
//
// NO DB calls inside this component — data is passed in as props.
//
// Decimal boundary: HoldingState.aggregate_weight is a stringified NUMERIC.
// toNumber() converts it at the component boundary before passing to computeSizing.

'use client'

import { useId } from 'react'
import type { HoldingState } from '@/lib/queries/v6/portfolio_holdings'
import { computeSizing, type SizingInput } from '@/lib/v6/sizing'
import { InfoTooltip } from '@/components/ui/InfoTooltip'
import { toNumberOr } from '@/lib/v6/decimal'

// ---------------------------------------------------------------------------
// Public interface
// ---------------------------------------------------------------------------

export interface PositionSizingWidgetProps {
  holdingState: HoldingState | null
  /** Regime-derived sizing scalar (0.0..1.5) */
  deploymentMultiplier: number
  /** Signed pp vs Nifty 500 benchmark for this stock's sector */
  sectorGapPp: number
  /** Number of Atlas cell rules firing in support (0..5) */
  cellConvictionDepth: number
  /** Per-stock policy cap (default 5) */
  maxPerStockPct?: number
  className?: string
}

// ---------------------------------------------------------------------------
// Constraint tooltip explanations
// ---------------------------------------------------------------------------

const CONSTRAINT_TOOLTIPS: Record<string, { content: string; translation: string }> = {
  max_per_stock: {
    content: 'Per-stock concentration cap.',
    translation: 'Position is at or near the maximum allowed weight for a single stock.',
  },
  deployment_cap: {
    content: 'Regime-adjusted deployment cap.',
    translation:
      'The current market regime reduces effective position size below the per-stock cap.',
  },
  sector_cap: {
    content: 'Sector overweight cap.',
    translation:
      'Your book is already overweight this sector vs the Nifty 500 benchmark. No further adds until the gap narrows.',
  },
  conviction_floor: {
    content: 'Conviction floor — zero Atlas cell support.',
    translation:
      'No cell rules currently support entry into this stock. Position sizing is blocked until conviction registers.',
  },
}

// ---------------------------------------------------------------------------
// Helper: derive current_weight_pct from HoldingState
// ---------------------------------------------------------------------------

function deriveCurrentWeight(state: HoldingState | null): number {
  if (state === null) return 0
  // aggregate_weight is a stringified NUMERIC (decimal fraction, e.g. "0.035" = 3.5%)
  // multiply by 100 to get whole-number percentage for computeSizing
  const fraction = toNumberOr(state.aggregate_weight, 0)
  return fraction * 100
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function PositionSizingWidget({
  holdingState,
  deploymentMultiplier,
  sectorGapPp,
  cellConvictionDepth,
  maxPerStockPct = 5,
  className = '',
}: PositionSizingWidgetProps): React.ReactElement {
  const widgetId = useId()
  const isHeld = holdingState !== null
  const currentWeightPct = deriveCurrentWeight(holdingState)

  const input: SizingInput = {
    current_weight_pct: currentWeightPct,
    max_per_stock_pct: maxPerStockPct,
    deployment_multiplier: deploymentMultiplier,
    sector_gap_pp: sectorGapPp,
    cell_conviction_depth: cellConvictionDepth,
  }

  const rec = computeSizing(input)
  const { suggested_add_pct, binding_constraint, rationale } = rec

  // Determine headline copy
  const isAtCap = suggested_add_pct === 0
  let headline: string

  if (!isHeld) {
    if (isAtCap) {
      headline = 'No first position suggested (see constraint below)'
    } else {
      headline = `+${suggested_add_pct.toFixed(1)}% suggested first position (current 0%)`
    }
  } else {
    if (isAtCap) {
      // Tailor at-cap message to constraint
      if (binding_constraint === 'max_per_stock') {
        headline = `At cap (${maxPerStockPct}% max per stock; current ${currentWeightPct.toFixed(1)}%)`
      } else if (binding_constraint === 'conviction_floor') {
        headline = 'Conviction too thin — no add suggested'
      } else if (binding_constraint === 'sector_cap') {
        headline = `Book overweight in sector — no add suggested (current ${currentWeightPct.toFixed(1)}%)`
      } else {
        headline = `Regime cap: no room at ${deploymentMultiplier}x (current ${currentWeightPct.toFixed(1)}%)`
      }
    } else {
      headline = `Suggested next add: +${suggested_add_pct.toFixed(1)}% (current ${currentWeightPct.toFixed(1)}%)`
    }
  }

  // Constraint chip label
  const constraintLabel = binding_constraint.replace(/_/g, ' ')
  const tooltipMeta = CONSTRAINT_TOOLTIPS[binding_constraint]

  // ARIA label encodes key numbers
  const ariaLabel =
    `Suggested position add: +${suggested_add_pct.toFixed(1)}%; ` +
    `binding constraint ${constraintLabel}; ` +
    `current weight ${currentWeightPct.toFixed(1)}%`

  return (
    <div
      id={widgetId}
      aria-label={ariaLabel}
      className={['flex flex-col gap-1.5 bg-paper-deep rounded-[3px] px-3 py-2.5', className].join(
        ' ',
      )}
    >
      {/* Headline */}
      <p className="text-sm font-sans font-medium text-ink-primary leading-snug">
        {headline}
      </p>

      {/* Binding constraint chip */}
      <div className="flex items-center gap-1.5 flex-wrap">
        <span className="text-[11px] font-sans text-ink-tertiary uppercase tracking-wide">
          Binding:
        </span>
        <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-[2px] bg-paper border border-paper-rule text-[11px] font-sans text-ink-secondary font-medium">
          {constraintLabel}
        </span>
        <InfoTooltip content={tooltipMeta.content} translation={tooltipMeta.translation} />

        {/* Constraint-specific value */}
        {binding_constraint === 'max_per_stock' && (
          <span className="text-[11px] font-sans text-ink-tertiary">
            {maxPerStockPct}% cap
          </span>
        )}
        {binding_constraint === 'deployment_cap' && deploymentMultiplier < 1.0 && (
          <span className="text-[11px] font-sans text-ink-tertiary">
            Regime cap: positions sized {Math.round(deploymentMultiplier * 100)}% of normal
          </span>
        )}
      </div>

      {/* Rationale secondary line */}
      <p className="text-[11px] font-sans text-ink-tertiary leading-relaxed">
        {rationale}
      </p>
    </div>
  )
}
