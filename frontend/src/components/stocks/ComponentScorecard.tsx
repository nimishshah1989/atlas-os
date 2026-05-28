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

// Plain-English context line for each scorecard row.
// Goal: every row answers "what does this number mean for the trader?"

function rsContextLine(rank: number | null): string {
  if (rank == null) return 'No relative-strength data'
  const pct = Math.round(rank * 100)
  if (rank >= 0.8)  return `Stronger than ${pct}% of Nifty-500 peers · top quintile`
  if (rank >= 0.6)  return `Stronger than ${pct}% of peers · above average`
  if (rank >= 0.4)  return `Around the middle of the pack (${pct}th percentile)`
  if (rank >= 0.2)  return `Weaker than ${100-pct}% of peers · below average`
  return `Weaker than ${100-pct}% of peers · bottom quintile`
}

function urgencyContextLine(urgency: string): string {
  if (urgency === 'urgent')  return 'Fresh — early in the state, signal still actionable'
  if (urgency === 'normal')  return 'In the typical part of the state cycle'
  if (urgency === 'late')    return 'Late — past the typical exit; signal aging'
  return 'No urgency reading'
}

function obvContextLine(slope: number | null | undefined): string {
  if (slope == null) return 'No OBV reading'
  const dir = slope >= 0 ? 'rising' : 'falling'
  const verb = slope >= 0 ? 'buyers accumulating' : 'sellers distributing'
  return `Volume trend is ${dir} (~${Math.abs(Math.round(slope)).toLocaleString('en-IN')} shares/day) — ${verb}`
}

function atrContextLine(ratio: number | null | undefined): string {
  if (ratio == null) return 'No volatility reading'
  if (ratio < 0.6)  return `Volatility very contracted (${ratio.toFixed(2)}× normal) — coiled spring, breakout candidate`
  if (ratio < 0.8)  return `Volatility contracted (${ratio.toFixed(2)}× normal) — energy building`
  if (ratio < 1.2)  return `Volatility around normal (${ratio.toFixed(2)}×)`
  if (ratio < 1.5)  return `Volatility expanded (${ratio.toFixed(2)}× normal) — recent move underway`
  return `Volatility extreme (${ratio.toFixed(2)}× normal) — late-stage moves often happen here`
}

function volTierContextLine(tier: string | null | undefined): string {
  if (!tier || tier === 'n/a')  return 'No vol-tier reading'
  if (tier.toLowerCase().includes('low'))   return 'Lower realised volatility than the universe median — calmer mover'
  if (tier.toLowerCase().includes('high'))  return 'Higher realised volatility than the universe median — wider swings'
  return `${tier} realised volatility tier`
}

export function ComponentScorecard({ state, validations, obvSlope, atrRatio, realizedVolTier }: ComponentScorecardProps) {
  const rsTier      = deriveRsTier(state.rs_rank_12m)
  const rsValidation = findValidation(validations, 'rs', rsTier)

  const stateLabel     = STATE_ROW_LABEL[state.state]
  const stateValidation = findValidation(validations, 'state', stateLabel)

  const dwellLabel = `Day ${state.dwell_days} · ${state.urgency_score}`
  const dwellValidation = findValidation(validations, 'dwell', state.state)

  const volTierBadge = realizedVolTier ?? 'n/a'

  return (
    <section
      className="px-6 py-4 border-t border-paper-rule"
      data-testid="component-scorecard"
      aria-label="Signal scorecard"
    >
      <h2 className="font-sans text-[10px] font-semibold text-ink-tertiary uppercase tracking-wider mb-1">
        Signal scorecard
      </h2>
      <p className="font-sans text-[11px] text-ink-tertiary mb-3 max-w-prose">
        Every row reads &ldquo;what is this and what does it mean for the trader.&rdquo;
        Validated rows are IC-backed; decorative rows are context.
      </p>

      <div>
        <ComponentValidationRow
          componentLabel="Relative strength"
          badge={rsTier}
          validation={rsValidation}
          contextLine={rsContextLine(state.rs_rank_12m)}
        />

        <ComponentValidationRow
          componentLabel="Master state"
          badge={stateLabel}
          validation={stateValidation}
        />

        <ComponentValidationRow
          componentLabel="Dwell timing"
          badge={dwellLabel}
          validation={dwellValidation}
          contextLine={urgencyContextLine(state.urgency_score)}
        />

        <ComponentValidationRow
          componentLabel="Volume flow (OBV)"
          badge="Continuous"
          validation={findValidation(validations, 'obv_slope_50d', 'Continuous')}
          contextLine={obvContextLine(obvSlope)}
        />

        <ComponentValidationRow
          componentLabel="Volatility (ATR)"
          badge="Continuous"
          validation={findValidation(validations, 'atr_contraction_ratio', 'Continuous')}
          contextLine={atrContextLine(atrRatio)}
        />

        <ComponentValidationRow
          componentLabel="Realised vol tier"
          badge={volTierBadge}
          validation={findValidation(validations, 'realized_vol_63', volTierBadge)}
          contextLine={volTierContextLine(realizedVolTier)}
        />
      </div>
    </section>
  )
}
