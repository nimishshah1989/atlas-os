// frontend/src/components/stocks/ComponentScorecard.tsx
// Bottom-of-page panel: one-glance signal scorecard for a stock.
// Phase 1: RS tier + state row + dwell row.
// Phase 6: OBV slope row, ATR contraction row, realized-vol-tier row wired via footer props.
// Pure server component.
import type { StockState } from '@/lib/queries/states'
import type { ComponentValidation } from '@/lib/queries/component_validation'
import { ComponentValidationRow } from './ComponentValidationRow'

interface ComponentScorecardProps {
  state: StockState
  validations: ComponentValidation[]
  obvSlope?: number | null
  atrRatio?: number | null
  realizedVolTier?: string | null
}

// ---------------------------------------------------------------------------
// RS tier derivation from rs_rank_12m [0..1]
// ---------------------------------------------------------------------------

function deriveRsTier(rank: number | null): string {
  if (rank == null) return 'Average'
  if (rank >= 0.8) return 'Leader'
  if (rank >= 0.6) return 'Strong'
  if (rank >= 0.4) return 'Average'
  if (rank >= 0.2) return 'Weak'
  return 'Laggard'
}

// ---------------------------------------------------------------------------
// State -> human label for the scorecard row
// ---------------------------------------------------------------------------

const STATE_ROW_LABEL: Record<StockState['state'], string> = {
  stage_1:      'Stage 1 Base',
  stage_2a:     'Stage 2A Fresh Breakout',
  stage_2b:     'Stage 2B Confirmed',
  stage_2c:     'Stage 2C Mature',
  stage_3:      'Stage 3 Top',
  stage_4:      'Stage 4 Decline',
  uninvestable: 'Uninvestable',
}

// ---------------------------------------------------------------------------
// Lookup helpers
// ---------------------------------------------------------------------------

function findValidation(
  validations: ComponentValidation[],
  component: string,
  badge: string,
): ComponentValidation | undefined {
  return validations.find(v => v.component_name === component && v.badge === badge)
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function ComponentScorecard({ state, validations, obvSlope, atrRatio, realizedVolTier }: ComponentScorecardProps) {
  const rsTier      = deriveRsTier(state.rs_rank_12m)
  const rsRankStr   = state.rs_rank_12m != null
    ? `12-month RS rank: ${state.rs_rank_12m.toFixed(2)}`
    : undefined
  const rsValidation = findValidation(validations, 'rs', rsTier)

  const stateLabel     = STATE_ROW_LABEL[state.state]
  const stateValidation = findValidation(validations, 'state', stateLabel)

  const dwellLabel = `Day ${state.dwell_days}`
  const dwellValidation = findValidation(validations, 'dwell', state.state)

  const volTierBadge = realizedVolTier ?? 'n/a'

  return (
    <section
      className="px-6 py-4 border-t border-paper-rule"
      data-testid="component-scorecard"
      aria-label="Signal scorecard"
    >
      <h2 className="font-sans text-[10px] font-semibold text-ink-tertiary uppercase tracking-wider mb-3">
        Signal scorecard
      </h2>

      <div>
        {/* RS tier row */}
        <ComponentValidationRow
          componentLabel="Relative strength"
          badge={rsTier}
          validation={rsValidation}
          contextLine={rsRankStr}
        />

        {/* Master state row */}
        <ComponentValidationRow
          componentLabel="Master state"
          badge={stateLabel}
          validation={stateValidation}
        />

        {/* Dwell / timing row */}
        <ComponentValidationRow
          componentLabel="Dwell timing"
          badge={dwellLabel}
          validation={dwellValidation}
          contextLine={`urgency: ${state.urgency_score}`}
        />

        {/* OBV slope row */}
        <ComponentValidationRow
          componentLabel="OBV slope"
          badge="Continuous"
          validation={findValidation(validations, 'obv_slope_50d', 'Continuous')}
          contextLine={obvSlope == null ? 'computed continuously' : `slope ${obvSlope >= 0 ? '+' : ''}${Math.round(obvSlope).toLocaleString('en-IN')}/day`}
        />

        {/* ATR contraction row */}
        <ComponentValidationRow
          componentLabel="ATR contraction"
          badge="Continuous"
          validation={findValidation(validations, 'atr_contraction_ratio', 'Continuous')}
          contextLine={atrRatio == null ? 'computed continuously' : `ratio ${atrRatio.toFixed(2)}`}
        />

        {/* Realized vol tier row */}
        <ComponentValidationRow
          componentLabel="Realized vol tier"
          badge={volTierBadge}
          validation={findValidation(validations, 'realized_vol_63', volTierBadge)}
          contextLine={undefined}
        />
      </div>
    </section>
  )
}
