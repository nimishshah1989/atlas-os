'use client'
// src/components/portfolio/PolicyPanel.tsx
// Read-only display of the effective portfolio policy.
// Shows all 17 fields grouped into 7 sections.
// Each field: label, formatted value, InfoTooltip, inherited/overridden marker.
// Editing is OUT OF SCOPE for this task.
//
// Tooltip system: InfoTooltip (Radix UI, inline string) — NOT MetricTooltip.
// Rationale: policy fields are config parameters, not financial metrics.
// Extending metric-registry with policy fields would muddy its purpose.

import { InfoTooltip } from '@/components/ui/InfoTooltip'
import { formatPct, formatRank } from '@/lib/format-number'
import { stageLabel, instrumentUniverseLabel } from '@/lib/stage-labels'

// ---------------------------------------------------------------------------
// Types — exported so policy.ts can import them
// ---------------------------------------------------------------------------

export type PolicyFieldValue = {
  value: string | string[] | boolean | null
  source: 'inherited' | 'overridden'
}

export type EffectivePolicy = {
  // Deployment
  cash_floor_pct: PolicyFieldValue
  respect_regime_cap: PolicyFieldValue
  // Concentration
  max_per_stock_pct: PolicyFieldValue
  max_per_sector_pct: PolicyFieldValue
  max_small_cap_pct: PolicyFieldValue
  min_holdings: PolicyFieldValue
  max_positions: PolicyFieldValue
  // Entry
  buy_states: PolicyFieldValue
  min_within_state_rank: PolicyFieldValue
  min_rs_rank: PolicyFieldValue
  // Exit
  hard_stop_pct: PolicyFieldValue
  state_exit_trim: PolicyFieldValue
  state_exit_full: PolicyFieldValue
  trailing_stop_pct: PolicyFieldValue
  // Instrument
  instrument_universe: PolicyFieldValue
  // Benchmark
  benchmark: PolicyFieldValue
  // Cadence
  rebalance_cadence: PolicyFieldValue
}

// ---------------------------------------------------------------------------
// Tooltip definitions — one per field
// ---------------------------------------------------------------------------

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
  min_rs_rank: 'Minimum 12-month relative-strength rank (0–1 quantile) required for entry. 0.70 means the stock\'s RS must be in the top 30% of the universe.',
  hard_stop_pct: 'Hard exit trigger: exit the full position if it falls this many percent below the entry price. A mechanical loss-limit — e.g. 8% means exit if the stock is down 8% from purchase.',
  state_exit_trim: 'RS state that triggers a partial position trim (reduce to half or a defined target). When a held stock enters this state, the system recommends trimming the position.',
  state_exit_full: 'RS state that triggers a full exit. When a held stock enters this state, the system recommends exiting 100% of the position.',
  trailing_stop_pct: 'Optional trailing stop: exit if the position falls this many percent below its highest post-entry close. Off = no trailing stop active.',
  instrument_universe: 'The class of instruments eligible for this portfolio — direct_equity, etf, mutual_fund, or mixed.',
  benchmark: 'The index used for alpha calculation, regime overlay, and relative performance attribution.',
  rebalance_cadence: 'How frequently the engine generates rebalance recommendations: daily, weekly, or monthly.',
}

// ---------------------------------------------------------------------------
// Formatting helpers
// ---------------------------------------------------------------------------

type FieldKind = 'pct' | 'rank' | 'bool' | 'states' | 'text' | 'int' | 'trailing'

function fieldKind(key: keyof EffectivePolicy): FieldKind {
  if (key === 'buy_states') return 'states'
  if (key === 'respect_regime_cap') return 'bool'
  if (key === 'trailing_stop_pct') return 'trailing'
  if (key === 'min_within_state_rank' || key === 'min_rs_rank') return 'rank'
  if (key === 'min_holdings' || key === 'max_positions') return 'int'
  if (
    key === 'state_exit_trim' ||
    key === 'state_exit_full' ||
    key === 'instrument_universe' ||
    key === 'benchmark' ||
    key === 'rebalance_cadence'
  ) return 'text'
  // cash_floor_pct, max_per_stock_pct, max_per_sector_pct, max_small_cap_pct, hard_stop_pct
  return 'pct'
}

function formatValue(key: keyof EffectivePolicy, raw: PolicyFieldValue['value']): React.ReactNode {
  const kind = fieldKind(key)

  if (kind === 'states') {
    const states = Array.isArray(raw) ? raw : []
    if (states.length === 0) return <span className="text-ink-tertiary">—</span>
    return (
      <span className="flex flex-wrap gap-1">
        {states.map((s) => (
          <span
            key={s}
            className="font-mono text-xs px-1.5 py-0.5 rounded-[2px] border border-paper-rule bg-paper text-ink-secondary"
          >
            {stageLabel(s)}
          </span>
        ))}
      </span>
    )
  }

  if (kind === 'bool') {
    return <span>{raw === true || raw === 'true' ? 'Yes' : 'No'}</span>
  }

  if (kind === 'trailing') {
    if (raw === null || raw === undefined || raw === '') return <span className="text-ink-tertiary">Off</span>
    return <span>{formatPct(typeof raw === 'string' ? raw : null)}</span>
  }

  if (kind === 'pct') {
    if (raw === null || raw === undefined) return <span className="text-ink-tertiary">—</span>
    return <span>{formatPct(typeof raw === 'string' || typeof raw === 'number' ? raw : null)}</span>
  }

  if (kind === 'rank') {
    if (raw === null || raw === undefined) return <span className="text-ink-tertiary">—</span>
    return <span>{formatRank(typeof raw === 'string' || typeof raw === 'number' ? raw : null)}</span>
  }

  // 'text' kind — translate known enum values
  if (raw === null || raw === undefined) return <span className="text-ink-tertiary">—</span>
  if (key === 'state_exit_trim' || key === 'state_exit_full') {
    return <span>{stageLabel(typeof raw === 'string' ? raw : null)}</span>
  }
  if (key === 'instrument_universe') {
    return <span>{instrumentUniverseLabel(typeof raw === 'string' ? raw : null)}</span>
  }
  return <span>{String(raw)}</span>
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function SourceBadge({ source }: { source: 'inherited' | 'overridden' }) {
  if (source === 'overridden') {
    return (
      <span
        data-source="overridden"
        className="font-sans text-[10px] px-1.5 py-0.5 rounded-[2px] border border-accent/30 text-accent bg-accent/5"
      >
        overridden
      </span>
    )
  }
  return (
    <span
      data-source="inherited"
      className="font-sans text-[10px] px-1.5 py-0.5 rounded-[2px] border border-paper-rule text-ink-tertiary bg-paper"
    >
      inherited
    </span>
  )
}

const FIELD_LABELS: Record<keyof EffectivePolicy, string> = {
  cash_floor_pct: 'Cash Floor',
  respect_regime_cap: 'Respect Regime Cap',
  max_per_stock_pct: 'Max per Stock',
  max_per_sector_pct: 'Max per Sector',
  max_small_cap_pct: 'Max Small Cap',
  min_holdings: 'Min Holdings',
  max_positions: 'Max Positions',
  buy_states: 'Buy States',
  min_within_state_rank: 'Min Within-State Rank',
  min_rs_rank: 'Min RS Rank',
  hard_stop_pct: 'Hard Stop',
  state_exit_trim: 'State Exit (Trim)',
  state_exit_full: 'State Exit (Full)',
  trailing_stop_pct: 'Trailing Stop',
  instrument_universe: 'Instrument Universe',
  benchmark: 'Benchmark',
  rebalance_cadence: 'Rebalance Cadence',
}

function PolicyField({
  fieldKey,
  field,
}: {
  fieldKey: keyof EffectivePolicy
  field: PolicyFieldValue
}) {
  return (
    <div className="flex items-start justify-between gap-4 py-2 border-b border-paper-rule/50 last:border-0">
      <div className="flex items-center gap-1 min-w-[180px]">
        <span className="font-sans text-xs text-ink-secondary">{FIELD_LABELS[fieldKey]}</span>
        <InfoTooltip content={TOOLTIPS[fieldKey]} />
      </div>
      <div className="flex items-center gap-2 flex-wrap justify-end">
        <span className="font-mono text-xs text-ink-primary">
          {formatValue(fieldKey, field.value)}
        </span>
        <SourceBadge source={field.source} />
      </div>
    </div>
  )
}

function PolicyGroup({
  title,
  fields,
  policy,
}: {
  title: string
  fields: (keyof EffectivePolicy)[]
  policy: EffectivePolicy
}) {
  return (
    <div className="mb-6">
      <h3 className="font-sans text-[11px] font-semibold uppercase tracking-wider text-ink-tertiary mb-2">
        {title}
      </h3>
      <div className="rounded-[3px] border border-paper-rule bg-paper px-4 py-0.5">
        {fields.map((key) => (
          <PolicyField key={key} fieldKey={key} field={policy[key]} />
        ))}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Group definitions
// ---------------------------------------------------------------------------

const GROUPS: Array<{ title: string; fields: (keyof EffectivePolicy)[] }> = [
  {
    title: 'Deployment',
    fields: ['cash_floor_pct', 'respect_regime_cap'],
  },
  {
    title: 'Concentration',
    fields: [
      'max_per_stock_pct',
      'max_per_sector_pct',
      'max_small_cap_pct',
      'min_holdings',
      'max_positions',
    ],
  },
  {
    title: 'Entry',
    fields: ['buy_states', 'min_within_state_rank', 'min_rs_rank'],
  },
  {
    title: 'Exit',
    fields: ['hard_stop_pct', 'state_exit_trim', 'state_exit_full', 'trailing_stop_pct'],
  },
  {
    title: 'Instrument',
    fields: ['instrument_universe'],
  },
  {
    title: 'Benchmark',
    fields: ['benchmark'],
  },
  {
    title: 'Cadence',
    fields: ['rebalance_cadence'],
  },
]

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

type Props = {
  policy: EffectivePolicy | null
}

export function PolicyPanel({ policy }: Props) {
  if (policy === null) {
    return (
      <div className="rounded-[3px] border border-paper-rule bg-paper px-4 py-5 text-center">
        <p className="font-sans text-sm text-ink-tertiary">
          Policy not configured — run{' '}
          <code className="font-mono text-xs">scripts/seed_house_policy.py</code> to seed the
          house default.
        </p>
      </div>
    )
  }

  return (
    <div>
      {GROUPS.map((group) => (
        <PolicyGroup
          key={group.title}
          title={group.title}
          fields={group.fields}
          policy={policy}
        />
      ))}
    </div>
  )
}
