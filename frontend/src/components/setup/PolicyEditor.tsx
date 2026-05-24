'use client'
// src/components/setup/PolicyEditor.tsx
// Editable twin of PolicyPanel. Presentational — no API calls.
// Modes: 'house-default' (all fields editable) | 'portfolio' (inherited/overridden flow).

import { useState, useMemo, useCallback } from 'react'
import { InfoTooltip } from '@/components/ui/InfoTooltip'
import { stageLabel, STAGE_LABEL, INSTRUMENT_UNIVERSE_LABEL } from '@/lib/stage-labels'
import type { EffectivePolicy, PolicyFieldValue } from '@/components/portfolio/PolicyPanel'

// ---------------------------------------------------------------------------
// Public types
// ---------------------------------------------------------------------------

export type PolicyEditorChanges = Partial<{
  [K in keyof EffectivePolicy]: PolicyFieldValue['value'] | null
}>

type Props = {
  policy: EffectivePolicy
  mode: 'house-default' | 'portfolio'
  onSave: (changed: PolicyEditorChanges) => void
}

// ---------------------------------------------------------------------------
// Constants (mirrors PolicyPanel)
// ---------------------------------------------------------------------------

const FIELD_LABELS: Record<keyof EffectivePolicy, string> = {
  cash_floor_pct: 'Cash Floor', respect_regime_cap: 'Respect Regime Cap',
  max_per_stock_pct: 'Max per Stock', max_per_sector_pct: 'Max per Sector',
  max_small_cap_pct: 'Max Small Cap', min_holdings: 'Min Holdings', max_positions: 'Max Positions',
  buy_states: 'Buy States', min_within_state_rank: 'Min Within-State Rank', min_rs_rank: 'Min RS Rank',
  hard_stop_pct: 'Hard Stop', state_exit_trim: 'State Exit (Trim)', state_exit_full: 'State Exit (Full)',
  trailing_stop_pct: 'Trailing Stop', instrument_universe: 'Instrument Universe',
  benchmark: 'Benchmark', rebalance_cadence: 'Rebalance Cadence',
}

const TOOLTIPS: Record<keyof EffectivePolicy, string> = {
  cash_floor_pct: 'Minimum cash reserve as a percentage of total portfolio value. Recommendations will not deploy below this floor — e.g. 5% means at most 95% is ever invested.',
  respect_regime_cap: 'When enabled, the engine caps total equity deployment according to the current market regime (e.g. Risk-Off regimes trigger reduced exposure). Disabling means the mandate always targets full deployment regardless of regime.',
  max_per_stock_pct: 'Maximum weight any single stock can hold in the portfolio. Limits idiosyncratic concentration risk — e.g. 5% means no stock can exceed 5% of AUM.',
  max_per_sector_pct: 'Maximum combined weight for all positions in any single sector. Must be ≥ max_per_stock_pct. Prevents sector concentration — e.g. 15% means total IT exposure cannot exceed 15%.',
  max_small_cap_pct: 'Maximum combined weight in small-cap stocks (outside Nifty 500). Caps illiquidity risk — e.g. 30% means at most 30% of the portfolio can be in small-caps.',
  min_holdings: 'Minimum number of distinct positions the portfolio must hold. Prevents over-concentration in a handful of names. Must be ≤ max_positions.',
  max_positions: 'Maximum number of distinct positions allowed at any time. Caps portfolio complexity and forces quality filtering.',
  buy_states: 'The set of RS (relative-strength) state stages in which new entries are permitted. Only stocks currently in one of these states are eligible for purchase recommendations.',
  min_within_state_rank: 'Minimum within-state rank (0–1 quantile) a stock must achieve before an entry is recommended. 0.60 means the stock must rank in the top 40% of peers in its state.',
  min_rs_rank: "Minimum 12-month relative-strength rank (0–1 quantile) required for entry. 0.70 means the stock's RS must be in the top 30% of the universe.",
  hard_stop_pct: 'Hard exit trigger: exit the full position if it falls this many percent below the entry price. A mechanical loss-limit — e.g. 8% means exit if the stock is down 8% from purchase.',
  state_exit_trim: 'RS state that triggers a partial position trim (reduce to half or a defined target). When a held stock enters this state, the system recommends trimming the position.',
  state_exit_full: 'RS state that triggers a full exit. When a held stock enters this state, the system recommends exiting 100% of the position.',
  trailing_stop_pct: 'Optional trailing stop: exit if the position falls this many percent below its highest post-entry close. Off = no trailing stop active.',
  instrument_universe: 'The class of instruments eligible for this portfolio — direct_equity, etf, mutual_fund, or mixed.',
  benchmark: 'The index used for alpha calculation, regime overlay, and relative performance attribution.',
  rebalance_cadence: 'How frequently the engine generates rebalance recommendations: daily, weekly, or monthly.',
}

const GROUPS: Array<{ title: string; fields: (keyof EffectivePolicy)[] }> = [
  { title: 'Deployment', fields: ['cash_floor_pct', 'respect_regime_cap'] },
  { title: 'Concentration', fields: ['max_per_stock_pct', 'max_per_sector_pct', 'max_small_cap_pct', 'min_holdings', 'max_positions'] },
  { title: 'Entry', fields: ['buy_states', 'min_within_state_rank', 'min_rs_rank'] },
  { title: 'Exit', fields: ['hard_stop_pct', 'state_exit_trim', 'state_exit_full', 'trailing_stop_pct'] },
  { title: 'Instrument', fields: ['instrument_universe'] },
  { title: 'Benchmark', fields: ['benchmark'] },
  { title: 'Cadence', fields: ['rebalance_cadence'] },
]

const ALL_STAGES = Object.keys(STAGE_LABEL) as string[]
const CADENCE_OPTIONS = ['daily', 'weekly', 'monthly']

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

type DraftValue = PolicyFieldValue['value']
type DraftState = Partial<Record<keyof EffectivePolicy, DraftValue>>

function policyToFlat(p: EffectivePolicy): DraftState {
  const d: DraftState = {}
  for (const k of Object.keys(p) as (keyof EffectivePolicy)[]) d[k] = p[k].value
  return d
}

function valuesEqual(a: DraftValue, b: DraftValue): boolean {
  if (Array.isArray(a) && Array.isArray(b)) return a.length === b.length && a.every((v, i) => v === b[i])
  if (a === null && b === null) return true
  return a === b
}

type FieldKind = 'pct' | 'rank' | 'int' | 'bool' | 'states' | 'text' | 'trailing' | 'universe' | 'cadence' | 'stage-select'

function fieldKind(key: keyof EffectivePolicy): FieldKind {
  if (key === 'buy_states') return 'states'
  if (key === 'respect_regime_cap') return 'bool'
  if (key === 'trailing_stop_pct') return 'trailing'
  if (key === 'min_within_state_rank' || key === 'min_rs_rank') return 'rank'
  if (key === 'min_holdings' || key === 'max_positions') return 'int'
  if (key === 'state_exit_trim' || key === 'state_exit_full') return 'stage-select'
  if (key === 'instrument_universe') return 'universe'
  if (key === 'rebalance_cadence') return 'cadence'
  if (key === 'benchmark') return 'text'
  return 'pct'
}

const inputCls = 'font-mono text-xs w-20 border border-paper-rule rounded-[2px] px-2 py-1 bg-paper text-ink-primary disabled:opacity-50 disabled:cursor-not-allowed'
const selectCls = 'font-mono text-xs border border-paper-rule rounded-[2px] px-2 py-1 bg-paper text-ink-primary disabled:opacity-50 disabled:cursor-not-allowed'

// ---------------------------------------------------------------------------
// Field controls
// ---------------------------------------------------------------------------

type CP = { fieldKey: keyof EffectivePolicy; value: DraftValue; disabled: boolean; onChange: (v: DraftValue) => void }

function FieldControl({ fieldKey, value, disabled, onChange }: CP) {
  const kind = fieldKind(fieldKey)
  const tid = `field-${fieldKey}`
  const strVal = value === null || value === undefined ? '' : String(value)

  if (kind === 'bool') {
    const boolVal = value === true || value === 'true'
    return (
      <div data-testid={tid} className="inline-flex items-center">
        <button data-testid={`toggle-${fieldKey}`} type="button" disabled={disabled}
          onClick={() => onChange(!boolVal)}
          className={`font-sans text-xs px-3 py-1 rounded-[2px] border transition-colors disabled:opacity-50 disabled:cursor-not-allowed ${boolVal ? 'bg-accent/10 border-accent/40 text-accent' : 'bg-paper border-paper-rule text-ink-secondary'}`}
        >{boolVal ? 'Yes' : 'No'}</button>
      </div>
    )
  }

  if (kind === 'states') {
    const selected = Array.isArray(value) ? value : []
    return (
      <div data-testid={tid} className="flex flex-wrap gap-2">
        {ALL_STAGES.map((s) => (
          <label key={s} className={`flex items-center gap-1 font-sans text-xs cursor-pointer ${disabled ? 'opacity-50 cursor-not-allowed' : ''}`}>
            <input type="checkbox" value={s} checked={selected.includes(s)} disabled={disabled}
              onChange={() => {
                if (disabled) return
                const next = selected.includes(s) ? selected.filter((x) => x !== s) : [...selected, s]
                onChange(next)
              }} className="w-3 h-3" />
            <span>{stageLabel(s)}</span>
          </label>
        ))}
      </div>
    )
  }

  if (kind === 'trailing') {
    const isOff = value === null || value === undefined || value === ''
    return (
      <div data-testid={tid} className="flex items-center gap-2">
        {isOff ? (
          <>
            <span data-testid="trailing-off-indicator" className="font-mono text-xs text-ink-tertiary">Off</span>
            {!disabled && <button type="button" onClick={() => onChange('0')} className="font-sans text-[11px] text-accent hover:underline">Enable</button>}
          </>
        ) : (
          <>
            <input data-testid={`input-${fieldKey}`} type="number" step="0.1" value={strVal} disabled={disabled} onChange={(e) => onChange(e.target.value)} className={inputCls} />
            {!disabled && <button data-testid="trailing-clear-btn" type="button" onClick={() => onChange(null)} className="font-sans text-[11px] text-ink-tertiary hover:text-ink-primary">Clear</button>}
          </>
        )}
      </div>
    )
  }

  if (kind === 'stage-select') {
    return (
      <div data-testid={tid}>
        <select value={strVal} disabled={disabled} onChange={(e) => onChange(e.target.value)} className={selectCls}>
          <option value="">—</option>
          {ALL_STAGES.map((s) => <option key={s} value={s}>{stageLabel(s)}</option>)}
        </select>
      </div>
    )
  }

  if (kind === 'universe') {
    return (
      <div data-testid={tid}>
        <select value={strVal} disabled={disabled} onChange={(e) => onChange(e.target.value)} className={selectCls}>
          {Object.entries(INSTRUMENT_UNIVERSE_LABEL).map(([k, lbl]) => <option key={k} value={k}>{lbl}</option>)}
        </select>
      </div>
    )
  }

  if (kind === 'cadence') {
    return (
      <div data-testid={tid}>
        <select value={strVal} disabled={disabled} onChange={(e) => onChange(e.target.value)} className={selectCls}>
          {CADENCE_OPTIONS.map((c) => <option key={c} value={c}>{c.charAt(0).toUpperCase() + c.slice(1)}</option>)}
        </select>
      </div>
    )
  }

  if (kind === 'text') {
    return (
      <div data-testid={tid}>
        <input data-testid={`input-${fieldKey}`} type="text" value={strVal} disabled={disabled} onChange={(e) => onChange(e.target.value)} className="font-mono text-xs w-32 border border-paper-rule rounded-[2px] px-2 py-1 bg-paper text-ink-primary disabled:opacity-50 disabled:cursor-not-allowed" />
      </div>
    )
  }

  // pct / rank / int
  const step = kind === 'rank' ? '0.01' : kind === 'int' ? '1' : '0.1'
  return (
    <div data-testid={tid}>
      <input data-testid={`input-${fieldKey}`} type="number" step={step} value={strVal} disabled={disabled} onChange={(e) => onChange(e.target.value)} className={inputCls} />
    </div>
  )
}

// ---------------------------------------------------------------------------
// Source badge
// ---------------------------------------------------------------------------

function SourceBadge({ fieldKey, source }: { fieldKey: keyof EffectivePolicy; source: 'inherited' | 'overridden' }) {
  const base = 'font-sans text-[10px] px-1.5 py-0.5 rounded-[2px] border'
  return source === 'overridden'
    ? <span data-testid={`source-badge-${fieldKey}`} data-source="overridden" className={`${base} border-accent/30 text-accent bg-accent/5`}>overridden</span>
    : <span data-testid={`source-badge-${fieldKey}`} data-source="inherited" className={`${base} border-paper-rule text-ink-tertiary bg-paper`}>inherited</span>
}

// ---------------------------------------------------------------------------
// Field row
// ---------------------------------------------------------------------------

type RowProps = {
  fieldKey: keyof EffectivePolicy; field: PolicyFieldValue; mode: Props['mode']
  draftValue: DraftValue; isActiveOverride: boolean; isReverted: boolean
  onValueChange: (v: DraftValue) => void; onOverride: () => void; onRevert: () => void
}

function FieldRow({ fieldKey, field, mode, draftValue, isActiveOverride, isReverted, onValueChange, onOverride, onRevert }: RowProps) {
  const isPortfolio = mode === 'portfolio'
  const disabled = isPortfolio && field.source === 'inherited' && !isActiveOverride
  const showOverrideBtn = isPortfolio && field.source === 'inherited' && !isActiveOverride
  const showRevertBtn = isPortfolio && field.source === 'overridden' && !isReverted
  const effectiveSource = isReverted ? 'inherited' : isActiveOverride ? 'overridden' : field.source

  return (
    <div className="flex items-start justify-between gap-4 py-2 border-b border-paper-rule/50 last:border-0">
      <div className="flex items-center gap-1 min-w-[180px]">
        <span className="font-sans text-xs text-ink-secondary">{FIELD_LABELS[fieldKey]}</span>
        <InfoTooltip content={TOOLTIPS[fieldKey]} />
      </div>
      <div className="flex items-center gap-2 flex-wrap justify-end">
        <FieldControl fieldKey={fieldKey} value={isReverted ? field.value : draftValue} disabled={disabled || isReverted} onChange={onValueChange} />
        {isPortfolio && <SourceBadge fieldKey={fieldKey} source={effectiveSource} />}
        {showOverrideBtn && <button data-testid={`override-btn-${fieldKey}`} type="button" onClick={onOverride} className="font-sans text-[11px] text-accent hover:underline">Override</button>}
        {showRevertBtn && <button data-testid={`revert-btn-${fieldKey}`} type="button" onClick={onRevert} className="font-sans text-[11px] text-ink-tertiary hover:text-signal-neg">Revert</button>}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export function PolicyEditor({ policy, mode, onSave }: Props) {
  const [savedBaseline, setSavedBaseline] = useState<DraftState>(() => policyToFlat(policy))
  const [draft, setDraft] = useState<DraftState>(() => policyToFlat(policy))
  const [activeOverrides, setActiveOverrides] = useState<Set<keyof EffectivePolicy>>(new Set())
  const [reverted, setReverted] = useState<Set<keyof EffectivePolicy>>(new Set())

  const handleValueChange = useCallback((key: keyof EffectivePolicy, val: DraftValue) => {
    setDraft((prev) => ({ ...prev, [key]: val }))
  }, [])

  const handleOverride = useCallback((key: keyof EffectivePolicy) => {
    setActiveOverrides((prev) => { const n = new Set(prev); n.add(key); return n })
  }, [])

  const handleRevert = useCallback((key: keyof EffectivePolicy) => {
    setReverted((prev) => { const n = new Set(prev); n.add(key); return n })
  }, [])

  const changedFields = useMemo<PolicyEditorChanges>(() => {
    const changes: PolicyEditorChanges = {}
    for (const key of Object.keys(policy) as (keyof EffectivePolicy)[]) {
      if (mode === 'portfolio') {
        if (reverted.has(key)) {
          changes[key] = null
        } else if (activeOverrides.has(key)) {
          changes[key] = draft[key] ?? null
        } else if (policy[key].source === 'overridden' && !valuesEqual(draft[key] ?? null, savedBaseline[key] ?? null)) {
          changes[key] = draft[key] ?? null
        }
      } else {
        if (!valuesEqual(draft[key] ?? null, savedBaseline[key] ?? null)) changes[key] = draft[key] ?? null
      }
    }
    return changes
  }, [draft, savedBaseline, policy, mode, activeOverrides, reverted])

  const isDirty = Object.keys(changedFields).length > 0

  const handleSave = useCallback(() => {
    const snapshot = { ...changedFields }
    onSave(snapshot)
    setSavedBaseline((prev) => {
      const next = { ...prev }
      for (const k of Object.keys(snapshot) as (keyof EffectivePolicy)[]) {
        next[k] = snapshot[k] === null ? policy[k].value : snapshot[k] as DraftValue
      }
      return next
    })
    setDraft((prev) => {
      const next = { ...prev }
      for (const k of Object.keys(snapshot) as (keyof EffectivePolicy)[]) {
        if (snapshot[k] === null) next[k] = policy[k].value
      }
      return next
    })
    setActiveOverrides(new Set())
    setReverted(new Set())
  }, [changedFields, onSave, policy])

  return (
    <div>
      {isDirty && (
        <div data-testid="unsaved-indicator" className="mb-4 px-3 py-2 rounded-[2px] border border-signal-warn/40 bg-signal-warn/5 font-sans text-xs text-signal-warn">
          Unsaved changes
        </div>
      )}
      {GROUPS.map((group) => (
        <div key={group.title} className="mb-6">
          <h3 className="font-sans text-[11px] font-semibold uppercase tracking-wider text-ink-tertiary mb-2">{group.title}</h3>
          <div className="rounded-[3px] border border-paper-rule bg-paper px-4 py-0.5">
            {group.fields.map((key) => (
              <FieldRow key={key} fieldKey={key} field={policy[key]} mode={mode}
                draftValue={draft[key] ?? policy[key].value}
                isActiveOverride={activeOverrides.has(key)}
                isReverted={reverted.has(key)}
                onValueChange={(v) => handleValueChange(key, v)}
                onOverride={() => handleOverride(key)}
                onRevert={() => handleRevert(key)}
              />
            ))}
          </div>
        </div>
      ))}
      <div className="flex items-center justify-end gap-3 pt-2 border-t border-paper-rule">
        <button type="button" disabled={!isDirty} onClick={handleSave}
          className="font-sans text-sm px-4 py-2 rounded-[2px] bg-accent text-white disabled:opacity-40 disabled:cursor-not-allowed hover:bg-accent/90 transition-colors">
          Save
        </button>
      </div>
    </div>
  )
}
