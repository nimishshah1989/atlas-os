'use client'
// src/app/portfolios/[id]/CompositionView.tsx
// Composition view for portfolio detail — Static (instrument table)
// or Rule-Based (human-readable narrative from config JSONB).

type StaticInstrument = {
  instrument_id: string
  instrument_type: 'stock' | 'etf' | 'fund'
  weight_pct: number
}

export function StaticComposition({ instruments }: { instruments: StaticInstrument[] }) {
  if (instruments.length === 0) {
    return <p className="font-sans text-sm text-ink-tertiary">No instruments recorded.</p>
  }
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left border-collapse">
        <thead>
          <tr className="border-b border-paper-rule">
            {['ID / Ticker', 'Type', 'Weight %'].map((col) => (
              <th key={col} className="font-sans text-xs text-ink-tertiary uppercase tracking-wide pb-2 pr-4 font-medium">
                {col}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {instruments.map((inst) => (
            <tr key={inst.instrument_id} className="border-b border-paper-rule/50">
              <td className="py-2 pr-4 font-mono text-xs text-ink-primary">{inst.instrument_id}</td>
              <td className="py-2 pr-4 font-sans text-xs text-ink-secondary capitalize">
                {inst.instrument_type}
              </td>
              <td className="py-2 font-mono text-sm text-right">
                {inst.weight_pct.toFixed(2)}%
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

// ---- Breadth gate display helpers ----

const BREADTH_LABELS: Record<string, string> = {
  pct_above_ema_50: 'Stocks above EMA-50',
  ad_ratio: 'A/D ratio',
  new_high_low_ratio: 'New-high/new-low ratio',
  pct_in_strong_states: 'Pct in Leader/Strong',
  pct_weinstein_pass: 'Pct passing Weinstein gate',
}

function formatBreadthThreshold(key: string, value: number): string {
  if (key === 'pct_above_ema_50') return `${value.toFixed(0)}%`
  return value.toFixed(2)
}

// ---- Filter label map ----

const FILTER_LABELS: Record<string, string> = {
  rs_state_filter: 'RS state',
  momentum_state_filter: 'Momentum state',
  risk_state_filter: 'Risk state',
  volume_state_filter: 'Volume state',
  sector_state_filter: 'Sector stance',
  regime_state_filter: 'Regime',
}

function StateChip({ label }: { label: string }) {
  return (
    <span className="font-mono text-xs bg-paper-rule/50 px-1.5 py-0.5 rounded-[2px] text-ink-primary">
      {label}
    </span>
  )
}

export function RuleBasedComposition({ config }: { config: Record<string, unknown> }) {
  const stateFilterKeys = Object.keys(FILTER_LABELS)
  const activeFilters = stateFilterKeys.filter(
    (k) => Array.isArray(config[k]) && (config[k] as unknown[]).length > 0,
  )

  const breadthGates = config.breadth_gates as Record<string, number> | undefined
  const activeBreadthGates =
    breadthGates && typeof breadthGates === 'object'
      ? Object.entries(breadthGates).filter(([, v]) => typeof v === 'number')
      : []

  const sizing = config.position_sizing as string | undefined
  const maxPos = config.max_positions as number | undefined
  const rebalance = config.rebalance_trigger as string | undefined

  const hasContent =
    activeFilters.length > 0 || activeBreadthGates.length > 0 || sizing !== undefined

  return (
    <div className="space-y-3">
      <div className="border border-paper-rule rounded-[2px] p-4 bg-paper">
        {hasContent ? (
          <>
            {/* Leading sentence */}
            <p className="font-serif text-base text-ink-primary mb-3">
              Holds <strong>
                {[
                  config.universe_stocks !== false ? 'stocks' : null,
                  config.universe_etfs ? 'ETFs' : null,
                  config.universe_funds ? 'funds' : null,
                ]
                  .filter(Boolean)
                  .join(', ') || 'instruments'}
              </strong> where:
            </p>

            {/* Entry filter bullets */}
            {activeFilters.length > 0 && (
              <ul className="space-y-1.5 mb-3">
                {activeFilters.map((key) => {
                  const states = config[key] as string[]
                  return (
                    <li key={key} className="flex items-start gap-2 text-sm">
                      <span className="font-sans text-ink-secondary w-32 flex-shrink-0">
                        {FILTER_LABELS[key]}
                      </span>
                      <span className="font-sans text-ink-tertiary mr-1">∈</span>
                      <span className="flex flex-wrap gap-1">
                        {states.map((s) => (
                          <StateChip key={s} label={s} />
                        ))}
                      </span>
                    </li>
                  )
                })}
              </ul>
            )}

            {/* Breadth gates */}
            {activeBreadthGates.length > 0 && (
              <div className="border-t border-paper-rule/40 pt-2 mb-3">
                <p className="font-sans text-xs text-ink-secondary font-medium mb-1.5">
                  Market breadth gates:
                </p>
                <ul className="space-y-1">
                  {activeBreadthGates.map(([key, val]) => (
                    <li key={key} className="flex items-center gap-2 text-sm">
                      <span className="font-sans text-ink-secondary">
                        {BREADTH_LABELS[key] ?? key}
                      </span>
                      <span className="font-mono text-xs text-ink-primary">
                        ≥ {formatBreadthThreshold(key, val)}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {/* Sizing + rebalance summary */}
            {(sizing !== undefined || maxPos !== undefined || rebalance !== undefined) && (
              <div className="border-t border-paper-rule/40 pt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs font-sans text-ink-secondary">
                {sizing && (
                  <span>
                    Sized{' '}
                    <span className="font-mono text-ink-primary">{sizing}</span>
                  </span>
                )}
                {maxPos !== undefined && (
                  <span>max {maxPos} positions</span>
                )}
                {rebalance && (
                  <span>
                    rebalance{' '}
                    <span className="font-mono text-ink-primary">{rebalance}</span>
                  </span>
                )}
              </div>
            )}
          </>
        ) : (
          <p className="font-sans text-sm text-ink-tertiary">No rules configured.</p>
        )}
      </div>

      <div className="border border-paper-rule rounded-[2px] p-4 bg-paper/50">
        <p className="font-sans text-sm text-ink-tertiary">
          Live holdings will appear after the first nightly run.
        </p>
      </div>
    </div>
  )
}
