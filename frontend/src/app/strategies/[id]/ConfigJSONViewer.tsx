'use client'
// src/app/strategies/[id]/ConfigJSONViewer.tsx
// allow-large: single-responsibility component with value translation tables

const FRIENDLY_LABELS: Record<string, string> = {
  state_filter: 'Signal Quality',
  regime_stance: 'Risk-Off Behaviour',
  position_sizing: 'Sizing Method',
  max_positions: 'Max Positions',
  max_sector_pct: 'Sector Cap',
  rebalance_trigger: 'Rebalance On',
  stock_allocation_pct: 'Stock Allocation',
  etf_allocation_pct: 'ETF Allocation',
  fund_tier_filter: 'Fund Tiers',
}

const REGIME_STANCE_LABELS: Record<string, string> = {
  pause_risk_off: 'Pauses — exits fully when market turns risk-off',
  scale_risk_off: 'Scales down — reduces exposure in risk-off, stays partially invested',
  hold_risk_off: 'Holds — stays fully invested regardless of market regime',
}

const STATE_FILTER_LABELS: Record<string, string> = {
  leader: 'Leader only (top decile RS)',
  strong: 'Strong (top-2 RS tiers)',
  emerging: 'Emerging (top-3 RS tiers, inc. early momentum)',
  investable: 'Investable (fund NAV Leader state)',
}

const POSITION_SIZING_LABELS: Record<string, string> = {
  equal_weight: 'Equal weight',
}

// Keys that are not useful in the config panel
const SKIP_KEYS = new Set(['description', 'threshold_overrides', 'momentum_state_filter',
  'risk_state_filter', 'volume_state_filter', 'sector_state_filter', 'regime_state_filter',
  'rs_state_filter'])

function isArrayValue(val: unknown): val is string[] {
  return Array.isArray(val)
}

function formatValue(key: string, value: unknown): string {
  if (key === 'regime_stance') return REGIME_STANCE_LABELS[String(value)] ?? String(value)
  if (key === 'position_sizing') return POSITION_SIZING_LABELS[String(value)] ?? String(value)
  if (key === 'rebalance_trigger') return String(value).replace(/_/g, ' ')
  if (key === 'max_sector_pct' || key === 'stock_allocation_pct' || key === 'etf_allocation_pct') {
    return `${value}%`
  }
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value ?? '—')
}

function formatArrayItem(key: string, item: string): string {
  if (key === 'state_filter') return STATE_FILTER_LABELS[item] ?? item
  return item
}

type TagChipProps = { label: string }
function TagChip({ label }: TagChipProps) {
  return (
    <span className="inline-block font-sans text-[10px] text-ink-secondary bg-paper-rule/30 border border-paper-rule rounded-[2px] px-2 py-0.5 mr-1 mb-1">
      {label}
    </span>
  )
}

type Props = {
  config: Record<string, unknown>
}

export function ConfigJSONViewer({ config }: Props) {
  const entries = Object.entries(config).filter(([key]) => !SKIP_KEYS.has(key))

  if (entries.length === 0) {
    return (
      <div className="border border-paper-rule rounded-[2px] p-4">
        <p className="font-sans text-sm text-ink-tertiary">No parameters stored.</p>
      </div>
    )
  }

  return (
    <div className="border border-paper-rule rounded-[2px] p-4 space-y-4">
      {entries.map(([key, value]) => {
        const label = FRIENDLY_LABELS[key] ?? key.replace(/_/g, ' ')
        return (
          <div key={key}>
            <p className="font-sans text-[10px] font-semibold text-ink-tertiary uppercase tracking-wide mb-1">
              {label}
            </p>
            {isArrayValue(value) ? (
              <div className="flex flex-wrap">
                {value.map((item) => (
                  <TagChip key={item} label={formatArrayItem(key, String(item))} />
                ))}
              </div>
            ) : (
              <p className="font-sans text-sm text-ink-primary">
                {formatValue(key, value)}
              </p>
            )}
          </div>
        )
      })}
    </div>
  )
}
