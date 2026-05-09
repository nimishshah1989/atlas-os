'use client'
// src/app/strategies/[id]/ConfigJSONViewer.tsx
// Read-only viewer for strategy_configs.config JSONB.
// Set-valued fields render as tag chips; scalars render as key: value pairs.

const FRIENDLY_LABELS: Record<string, string> = {
  state_filter: 'State Filter',
  momentum_state_filter: 'Momentum State Filter',
  risk_state_filter: 'Risk State Filter',
  volume_state_filter: 'Volume State Filter',
  sector_state_filter: 'Sector State Filter',
  regime_state_filter: 'Regime Gate',
  position_sizing: 'Position Sizing',
  max_positions: 'Max Positions',
  max_sector_pct: 'Max Sector %',
  rebalance_trigger: 'Rebalance Trigger',
  rs_state_filter: 'RS State Filter',
}

function isArrayValue(val: unknown): val is string[] {
  return Array.isArray(val)
}

type TagChipProps = { label: string }
function TagChip({ label }: TagChipProps) {
  return (
    <span className="inline-block font-mono text-[10px] text-ink-secondary bg-paper-rule/30 border border-paper-rule rounded-[2px] px-2 py-0.5 mr-1 mb-1">
      {label}
    </span>
  )
}

type Props = {
  config: Record<string, unknown>
}

export function ConfigJSONViewer({ config }: Props) {
  const entries = Object.entries(config)

  if (entries.length === 0) {
    return (
      <div className="border border-paper-rule rounded-[2px] p-4">
        <p className="font-sans text-sm text-ink-tertiary">No config stored.</p>
      </div>
    )
  }

  return (
    <div className="border border-paper-rule rounded-[2px] p-4 space-y-3">
      {entries.map(([key, value]) => {
        const label = FRIENDLY_LABELS[key] ?? key
        return (
          <div key={key}>
            <p className="font-sans text-xs text-ink-tertiary uppercase tracking-wide mb-1">
              {label}
            </p>
            {isArrayValue(value) ? (
              <div className="flex flex-wrap">
                {value.map((item) => (
                  <TagChip key={item} label={String(item)} />
                ))}
              </div>
            ) : (
              <p className="font-mono text-sm text-ink-primary">
                {typeof value === 'object' ? JSON.stringify(value) : String(value ?? '—')}
              </p>
            )}
          </div>
        )
      })}
    </div>
  )
}
