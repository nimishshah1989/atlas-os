// frontend/src/components/stocks/ComponentScorecard.tsx
// Bottom-of-page panel: one-glance signal scorecard for a stock.
// Phase 1: RS tier + state row + dwell row.
// TODO (step 6): OBV slope row, ATR contraction row, realized-vol-tier row —
//   pending OBVContinuousChart + ATRContractionGauge + WithinStatePeers (Phase 5b).
// Pure server component.
import type { StockState } from '@/lib/queries/states'
import type { ComponentValidation } from '@/lib/queries/component_validation'
import { ComponentValidationRow } from './ComponentValidationRow'

interface ComponentScorecardProps {
  state: StockState
  validations: ComponentValidation[]
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
// State → human label for the scorecard row
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

export function ComponentScorecard({ state, validations }: ComponentScorecardProps) {
  const rsTier      = deriveRsTier(state.rs_rank_12m)
  const rsRankStr   = state.rs_rank_12m != null
    ? `rs_rank_12m ${state.rs_rank_12m.toFixed(2)}`
    : undefined
  const rsValidation = findValidation(validations, 'rs', rsTier)

  const stateLabel     = STATE_ROW_LABEL[state.state]
  const stateValidation = findValidation(validations, 'state', stateLabel)

  const dwellLabel = `Day ${state.dwell_days}`
  const dwellValidation = findValidation(validations, 'dwell', state.state)

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

        {/* ----------------------------------------------------------------
            Phase 5b rows — deferred pending OBVContinuousChart +
            ATRContractionGauge + realized-vol cross-sectional context.
            Add in step 6 of the stock detail page redesign.
            ---------------------------------------------------------------- */}
        <ComponentValidationRow
          componentLabel="OBV slope"
          badge="Continuous"
          validation={undefined}
          contextLine="Phase 5b — chart below"
        />

        <ComponentValidationRow
          componentLabel="ATR contraction"
          badge="Continuous"
          validation={undefined}
          contextLine="Phase 5b — gauge below"
        />

        <ComponentValidationRow
          componentLabel="Realized vol tier"
          badge="n/a"
          validation={undefined}
          contextLine="Phase 5b — cross-sectional context required"
        />
      </div>
    </section>
  )
}
