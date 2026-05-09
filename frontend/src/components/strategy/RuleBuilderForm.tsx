'use client'
// allow-large: composes 7 rule cards + sizing + rebalance + submit polling + all form state management
// src/components/strategy/RuleBuilderForm.tsx

import { useState, useCallback } from 'react'
import { useRouter } from 'next/navigation'
import {
  RS_STATES,
  MOMENTUM_STATES,
  RISK_STATES,
  VOLUME_STATES,
  SECTOR_STATES,
  REGIME_STATES,
  BREADTH_GATES,
  POSITION_SIZING,
  REBALANCE,
} from '@/lib/rule-catalogs'
import { RuleCard } from './RuleCard'
import { StateMultiSelect } from './StateMultiSelect'
import { BreadthGateSlider } from './BreadthGateSlider'
import { createRuleBasedPortfolio, getPortfolioStatusAction } from '@/app/portfolios/new/actions'

type StateFilterField = {
  enabled: boolean
  selected: Set<string>
}

type FormState = {
  name: string
  description: string
  // Universe
  universeStocks: boolean
  universeEtfs: boolean
  universeFunds: boolean
  // Entry rules
  rsStateFilter: StateFilterField
  momentumStateFilter: StateFilterField
  riskStateFilter: StateFilterField
  volumeStateFilter: StateFilterField
  sectorStateFilter: StateFilterField
  regimeStateFilter: StateFilterField
  breadthGates: { enabled: boolean; values: Record<string, number | null> }
  // Exit rules
  drawdownPerPosition: number | null
  drawdownEnabled: boolean
  holdingPeriodMax: number | null
  holdingPeriodEnabled: boolean
  // Sizing
  positionSizing: 'equal_weight' | 'vol_target' | 'market_cap'
  maxPositions: number
  maxSectorPct: number
  // Rebalance
  rebalanceTrigger: 'signal_change' | 'weekly' | 'monthly'
}

type SubmitState =
  | { phase: 'idle' }
  | { phase: 'creating' }
  | { phase: 'polling'; portfolioId: string; elapsed: number }
  | { phase: 'error'; message: string }
  | { phase: 'conflict' }

function buildInitialState(): FormState {
  const gateValues: Record<string, number | null> = {}
  for (const g of BREADTH_GATES) {
    gateValues[g.key] = null
  }
  return {
    name: '',
    description: '',
    universeStocks: true,
    universeEtfs: false,
    universeFunds: false,
    rsStateFilter: { enabled: false, selected: new Set() },
    momentumStateFilter: { enabled: false, selected: new Set() },
    riskStateFilter: { enabled: false, selected: new Set() },
    volumeStateFilter: { enabled: false, selected: new Set() },
    sectorStateFilter: { enabled: false, selected: new Set() },
    regimeStateFilter: { enabled: false, selected: new Set() },
    breadthGates: { enabled: false, values: gateValues },
    drawdownPerPosition: null,
    drawdownEnabled: false,
    holdingPeriodMax: null,
    holdingPeriodEnabled: false,
    positionSizing: 'equal_weight',
    maxPositions: 20,
    maxSectorPct: 25,
    rebalanceTrigger: 'signal_change',
  }
}

/** True if any enabled filter has zero selections */
function hasEmptyEnabledFilter(state: FormState): boolean {
  const filters: StateFilterField[] = [
    state.rsStateFilter,
    state.momentumStateFilter,
    state.riskStateFilter,
    state.volumeStateFilter,
    state.sectorStateFilter,
    state.regimeStateFilter,
  ]
  return filters.some((f) => f.enabled && f.selected.size === 0)
}

/** Build the config payload, dropping disabled rules */
export function buildConfigPayload(state: FormState): Record<string, unknown> {
  const config: Record<string, unknown> = {}

  if (state.rsStateFilter.enabled && state.rsStateFilter.selected.size > 0) {
    config.rs_state_filter = [...state.rsStateFilter.selected]
  }
  if (state.momentumStateFilter.enabled && state.momentumStateFilter.selected.size > 0) {
    config.momentum_state_filter = [...state.momentumStateFilter.selected]
  }
  if (state.riskStateFilter.enabled && state.riskStateFilter.selected.size > 0) {
    config.risk_state_filter = [...state.riskStateFilter.selected]
  }
  if (state.volumeStateFilter.enabled && state.volumeStateFilter.selected.size > 0) {
    config.volume_state_filter = [...state.volumeStateFilter.selected]
  }
  if (state.sectorStateFilter.enabled && state.sectorStateFilter.selected.size > 0) {
    config.sector_state_filter = [...state.sectorStateFilter.selected]
  }
  if (state.regimeStateFilter.enabled && state.regimeStateFilter.selected.size > 0) {
    config.regime_state_filter = [...state.regimeStateFilter.selected]
  }

  if (state.breadthGates.enabled) {
    const activeGates: Record<string, number> = {}
    for (const [key, val] of Object.entries(state.breadthGates.values)) {
      if (val !== null) activeGates[key] = val
    }
    if (Object.keys(activeGates).length > 0) {
      config.breadth_gates = activeGates
    }
  }

  if (state.drawdownEnabled && state.drawdownPerPosition !== null) {
    config.exit_rules = {
      ...(typeof config.exit_rules === 'object' && config.exit_rules !== null
        ? config.exit_rules
        : {}),
      drawdown_per_position_pct: state.drawdownPerPosition,
    }
  }
  if (state.holdingPeriodEnabled && state.holdingPeriodMax !== null) {
    config.exit_rules = {
      ...(typeof config.exit_rules === 'object' && config.exit_rules !== null
        ? config.exit_rules
        : {}),
      holding_period_max_days: state.holdingPeriodMax,
    }
  }

  config.position_sizing = state.positionSizing
  config.max_positions = state.maxPositions
  config.max_sector_pct = state.maxSectorPct
  config.rebalance_trigger = state.rebalanceTrigger

  return config
}

export function RuleBuilderForm() {
  const router = useRouter()
  const [form, setForm] = useState<FormState>(buildInitialState)
  const [submitState, setSubmitState] = useState<SubmitState>({ phase: 'idle' })

  const isSubmitting =
    submitState.phase === 'creating' || submitState.phase === 'polling'

  // Generic state filter updater
  const updateStateFilter = useCallback(
    (
      field: keyof Pick<
        FormState,
        | 'rsStateFilter'
        | 'momentumStateFilter'
        | 'riskStateFilter'
        | 'volumeStateFilter'
        | 'sectorStateFilter'
        | 'regimeStateFilter'
      >,
      patch: Partial<StateFilterField>,
    ) => {
      setForm((prev) => ({
        ...prev,
        [field]: { ...prev[field], ...patch },
      }))
    },
    [],
  )

  const updateGateValue = useCallback((key: string, value: number | null) => {
    setForm((prev) => ({
      ...prev,
      breadthGates: {
        ...prev.breadthGates,
        values: { ...prev.breadthGates.values, [key]: value },
      },
    }))
  }, [])

  async function handleSubmit() {
    if (!form.name.trim()) {
      setSubmitState({ phase: 'error', message: 'Portfolio name is required' })
      window.scrollTo({ top: 0, behavior: 'smooth' })
      return
    }

    setSubmitState({ phase: 'creating' })

    const config = buildConfigPayload(form)

    const universeFilter = {
      stocks: form.universeStocks,
      etfs: form.universeEtfs,
      funds: form.universeFunds,
    }

    const result = await createRuleBasedPortfolio({
      name: form.name.trim(),
      description: form.description.trim() || null,
      config,
      universe_filter: universeFilter,
    })

    if (!result.ok) {
      if (result.error.includes('409') || result.error.toLowerCase().includes('already running')) {
        setSubmitState({ phase: 'conflict' })
      } else {
        setSubmitState({ phase: 'error', message: result.error })
        window.scrollTo({ top: 0, behavior: 'smooth' })
      }
      return
    }

    const portfolioId = result.portfolio_id
    const startTime = Date.now()
    setSubmitState({ phase: 'polling', portfolioId, elapsed: 0 })

    const poll = async () => {
      const elapsed = Math.floor((Date.now() - startTime) / 1000)
      setSubmitState({ phase: 'polling', portfolioId, elapsed })

      const status = await getPortfolioStatusAction(portfolioId)
      if (!status.ok) {
        setTimeout(poll, 3000)
        return
      }
      if (status.status === 'completed') {
        router.push(`/portfolios/${portfolioId}`)
        return
      }
      setTimeout(poll, 3000)
    }
    setTimeout(poll, 3000)
  }

  const warnEmptyFilter = hasEmptyEnabledFilter(form)

  return (
    <div className="space-y-8">
      {/* Top-level error */}
      {submitState.phase === 'error' && (
        <div className="border border-signal-neg/30 bg-signal-neg/5 rounded-[2px] px-4 py-3">
          <p className="font-sans text-sm text-signal-neg">{submitState.message}</p>
        </div>
      )}
      {submitState.phase === 'conflict' && (
        <div className="border border-signal-warn/30 bg-signal-warn/5 rounded-[2px] px-4 py-3">
          <p className="font-sans text-sm text-signal-warn">
            A backtest is already running for this strategy. Wait for it to complete.
          </p>
        </div>
      )}
      {warnEmptyFilter && (
        <div className="border border-signal-warn/30 bg-signal-warn/5 rounded-[2px] px-4 py-3">
          <p className="font-sans text-sm text-signal-warn">
            No instruments will match — pick at least one state in any active filter, or disable the empty filter.
          </p>
        </div>
      )}

      {/* Step 1: Name + Description */}
      <section>
        <h2 className="font-sans text-sm font-semibold text-ink-primary mb-3">
          Step 1: Name your strategy
        </h2>
        <div className="space-y-3">
          <input
            type="text"
            value={form.name}
            onChange={(e) => setForm((p) => ({ ...p, name: e.target.value }))}
            placeholder="e.g. Momentum Leaders — Large Cap"
            disabled={isSubmitting}
            className="w-full md:w-96 font-sans text-sm px-3 py-2 border border-paper-rule rounded-[2px] bg-paper text-ink-primary placeholder:text-ink-tertiary focus:outline-none focus:border-accent"
          />
          <textarea
            value={form.description}
            onChange={(e) => setForm((p) => ({ ...p, description: e.target.value }))}
            placeholder="Optional description…"
            disabled={isSubmitting}
            rows={2}
            className="w-full md:w-96 font-sans text-sm px-3 py-2 border border-paper-rule rounded-[2px] bg-paper text-ink-primary placeholder:text-ink-tertiary focus:outline-none focus:border-accent resize-none"
          />
        </div>
      </section>

      {/* Step 2: Universe */}
      <section>
        <h2 className="font-sans text-sm font-semibold text-ink-primary mb-3">
          Step 2: Universe
        </h2>
        <div className="flex gap-6">
          {([
            { key: 'universeStocks', label: 'Stocks' },
            { key: 'universeEtfs', label: 'ETFs' },
            { key: 'universeFunds', label: 'Mutual Funds' },
          ] as const).map(({ key, label }) => (
            <label key={key} className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={form[key]}
                onChange={(e) => setForm((p) => ({ ...p, [key]: e.target.checked }))}
                disabled={isSubmitting}
                className="accent-accent"
              />
              <span className="font-sans text-sm text-ink-primary">{label}</span>
            </label>
          ))}
        </div>
      </section>

      {/* Step 3: Entry rules */}
      <section>
        <h2 className="font-sans text-sm font-semibold text-ink-primary mb-3">
          Step 3: Entry rules
        </h2>
        <div className="space-y-3">
          <RuleCard
            title="RS State Filter"
            description="Relative strength state of the instrument"
            enabled={form.rsStateFilter.enabled}
            onToggleEnabled={() =>
              updateStateFilter('rsStateFilter', { enabled: !form.rsStateFilter.enabled })
            }
          >
            <StateMultiSelect
              title="Allowed states"
              options={RS_STATES}
              selected={form.rsStateFilter.selected}
              onChange={(next) => updateStateFilter('rsStateFilter', { selected: next })}
            />
          </RuleCard>

          <RuleCard
            title="Momentum State Filter"
            description="Price momentum trend of the instrument"
            enabled={form.momentumStateFilter.enabled}
            onToggleEnabled={() =>
              updateStateFilter('momentumStateFilter', {
                enabled: !form.momentumStateFilter.enabled,
              })
            }
          >
            <StateMultiSelect
              title="Allowed states"
              options={MOMENTUM_STATES}
              selected={form.momentumStateFilter.selected}
              onChange={(next) => updateStateFilter('momentumStateFilter', { selected: next })}
            />
          </RuleCard>

          <RuleCard
            title="Risk State Filter"
            description="Volatility / risk regime of the instrument"
            enabled={form.riskStateFilter.enabled}
            onToggleEnabled={() =>
              updateStateFilter('riskStateFilter', { enabled: !form.riskStateFilter.enabled })
            }
          >
            <StateMultiSelect
              title="Allowed states"
              options={RISK_STATES}
              selected={form.riskStateFilter.selected}
              onChange={(next) => updateStateFilter('riskStateFilter', { selected: next })}
            />
          </RuleCard>

          <RuleCard
            title="Volume State Filter"
            description="Volume / accumulation-distribution state"
            enabled={form.volumeStateFilter.enabled}
            onToggleEnabled={() =>
              updateStateFilter('volumeStateFilter', { enabled: !form.volumeStateFilter.enabled })
            }
          >
            <StateMultiSelect
              title="Allowed states"
              options={VOLUME_STATES}
              selected={form.volumeStateFilter.selected}
              onChange={(next) => updateStateFilter('volumeStateFilter', { selected: next })}
            />
          </RuleCard>

          <RuleCard
            title="Sector State Filter"
            description="Sector allocation stance (Overweight / Neutral / Underweight / Avoid)"
            enabled={form.sectorStateFilter.enabled}
            onToggleEnabled={() =>
              updateStateFilter('sectorStateFilter', { enabled: !form.sectorStateFilter.enabled })
            }
          >
            <StateMultiSelect
              title="Allowed states"
              options={SECTOR_STATES}
              selected={form.sectorStateFilter.selected}
              onChange={(next) => updateStateFilter('sectorStateFilter', { selected: next })}
            />
          </RuleCard>

          <RuleCard
            title="Market Regime Filter"
            description="Overall market regime gate"
            enabled={form.regimeStateFilter.enabled}
            onToggleEnabled={() =>
              updateStateFilter('regimeStateFilter', { enabled: !form.regimeStateFilter.enabled })
            }
          >
            <StateMultiSelect
              title="Allowed states"
              options={REGIME_STATES}
              selected={form.regimeStateFilter.selected}
              onChange={(next) => updateStateFilter('regimeStateFilter', { selected: next })}
            />
          </RuleCard>

          <RuleCard
            title="Market Breadth Gates"
            description="Block all entries when market-breadth metrics fall below thresholds"
            enabled={form.breadthGates.enabled}
            onToggleEnabled={() =>
              setForm((p) => ({
                ...p,
                breadthGates: { ...p.breadthGates, enabled: !p.breadthGates.enabled },
              }))
            }
          >
            <div className="space-y-0">
              {BREADTH_GATES.map((gate) => (
                <BreadthGateSlider
                  key={gate.key}
                  gate={gate}
                  value={form.breadthGates.values[gate.key] ?? null}
                  onChange={(v) => updateGateValue(gate.key, v)}
                />
              ))}
            </div>
          </RuleCard>
        </div>
      </section>

      {/* Step 4: Exit rules */}
      <section>
        <h2 className="font-sans text-sm font-semibold text-ink-primary mb-3">
          Step 4: Exit rules
        </h2>
        <div className="bg-paper border border-paper-rule rounded-[2px] p-4 space-y-4">
          {/* Stop loss */}
          <div className="flex items-center gap-4 flex-wrap">
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={form.drawdownEnabled}
                onChange={(e) =>
                  setForm((p) => ({ ...p, drawdownEnabled: e.target.checked }))
                }
                disabled={isSubmitting}
                className="accent-accent"
              />
              <span className="font-sans text-sm text-ink-primary">Stop loss per position (%)</span>
            </label>
            {form.drawdownEnabled && (
              <input
                type="number"
                min={1}
                max={50}
                step={1}
                value={form.drawdownPerPosition ?? 10}
                onChange={(e) =>
                  setForm((p) => ({
                    ...p,
                    drawdownPerPosition: parseFloat(e.target.value),
                  }))
                }
                disabled={isSubmitting}
                className="w-20 font-mono text-sm px-2 py-1 border border-paper-rule rounded-[2px] bg-paper text-ink-primary focus:outline-none focus:border-accent"
              />
            )}
          </div>

          {/* Max holding period */}
          <div className="flex items-center gap-4 flex-wrap">
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={form.holdingPeriodEnabled}
                onChange={(e) =>
                  setForm((p) => ({ ...p, holdingPeriodEnabled: e.target.checked }))
                }
                disabled={isSubmitting}
                className="accent-accent"
              />
              <span className="font-sans text-sm text-ink-primary">Max holding period (days)</span>
            </label>
            {form.holdingPeriodEnabled && (
              <input
                type="number"
                min={1}
                max={365}
                step={1}
                value={form.holdingPeriodMax ?? 90}
                onChange={(e) =>
                  setForm((p) => ({
                    ...p,
                    holdingPeriodMax: parseInt(e.target.value, 10),
                  }))
                }
                disabled={isSubmitting}
                className="w-20 font-mono text-sm px-2 py-1 border border-paper-rule rounded-[2px] bg-paper text-ink-primary focus:outline-none focus:border-accent"
              />
            )}
          </div>
        </div>
      </section>

      {/* Step 5: Position sizing */}
      <section>
        <h2 className="font-sans text-sm font-semibold text-ink-primary mb-3">
          Step 5: Position sizing
        </h2>
        <div className="bg-paper border border-paper-rule rounded-[2px] p-4 space-y-4">
          <div className="flex gap-6 flex-wrap">
            {POSITION_SIZING.map((opt) => (
              <label key={opt} className="flex items-center gap-2 cursor-pointer">
                <input
                  type="radio"
                  name="positionSizing"
                  value={opt}
                  checked={form.positionSizing === opt}
                  onChange={() => setForm((p) => ({ ...p, positionSizing: opt }))}
                  disabled={isSubmitting}
                  className="accent-accent"
                />
                <span className="font-mono text-sm text-ink-primary">{opt}</span>
              </label>
            ))}
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="font-sans text-xs text-ink-secondary block mb-1">
                Max positions: {form.maxPositions}
              </label>
              <input
                type="range"
                min={5}
                max={50}
                step={1}
                value={form.maxPositions}
                onChange={(e) =>
                  setForm((p) => ({ ...p, maxPositions: parseInt(e.target.value, 10) }))
                }
                disabled={isSubmitting}
                className="w-full accent-accent"
              />
              <div className="flex justify-between font-sans text-xs text-ink-tertiary">
                <span>5</span>
                <span>50</span>
              </div>
            </div>

            <div>
              <label className="font-sans text-xs text-ink-secondary block mb-1">
                Max sector %: {form.maxSectorPct}%
              </label>
              <input
                type="range"
                min={10}
                max={50}
                step={5}
                value={form.maxSectorPct}
                onChange={(e) =>
                  setForm((p) => ({ ...p, maxSectorPct: parseInt(e.target.value, 10) }))
                }
                disabled={isSubmitting}
                className="w-full accent-accent"
              />
              <div className="flex justify-between font-sans text-xs text-ink-tertiary">
                <span>10%</span>
                <span>50%</span>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Step 6: Rebalance */}
      <section>
        <h2 className="font-sans text-sm font-semibold text-ink-primary mb-3">
          Step 6: Rebalance trigger
        </h2>
        <div className="bg-paper border border-paper-rule rounded-[2px] p-4">
          <div className="flex gap-6 flex-wrap">
            {REBALANCE.map((opt) => (
              <label key={opt} className="flex items-center gap-2 cursor-pointer">
                <input
                  type="radio"
                  name="rebalanceTrigger"
                  value={opt}
                  checked={form.rebalanceTrigger === opt}
                  onChange={() => setForm((p) => ({ ...p, rebalanceTrigger: opt }))}
                  disabled={isSubmitting}
                  className="accent-accent"
                />
                <span className="font-mono text-sm text-ink-primary">{opt}</span>
              </label>
            ))}
          </div>
        </div>
      </section>

      {/* Step 7: Submit */}
      <section>
        <h2 className="font-sans text-sm font-semibold text-ink-primary mb-3">
          Step 7: Submit
        </h2>
        {submitState.phase === 'polling' && (
          <p className="font-sans text-sm text-ink-secondary mb-3">
            Backtest running… ({submitState.elapsed}s elapsed)
          </p>
        )}
        <button
          type="button"
          onClick={handleSubmit}
          disabled={isSubmitting}
          className={`font-sans text-sm px-6 py-2.5 rounded-[2px] border transition-colors ${
            isSubmitting
              ? 'bg-paper-rule/30 border-paper-rule text-ink-tertiary cursor-wait'
              : 'bg-accent text-white border-accent hover:bg-accent/90'
          }`}
        >
          {submitState.phase === 'creating'
            ? 'Creating…'
            : submitState.phase === 'polling'
            ? 'Backtest running…'
            : 'Create + Backtest'}
        </button>
      </section>
    </div>
  )
}
