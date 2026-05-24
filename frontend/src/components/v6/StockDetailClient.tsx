// frontend/src/components/v6/StockDetailClient.tsx
//
// Interactive parts of the v6 stock detail page: the large ConvictionTape
// with click-to-expand RuleCard for the selected segment.

'use client'

import { useState } from 'react'
import { ConvictionTape } from './ConvictionTape'
import { RuleCard } from './RuleCard'
import { ELI5Tooltip } from './ELI5Tooltip'
import { StateBadge } from '@/components/ui/StateBadge'
import type { ScreenStock, CellRule, Tenure } from '@/lib/api/v1'
import { formatIC } from '@/lib/format-cell'

type Props = {
  stock: ScreenStock
  cellRules: Map<string, CellRule[]>
}

export function StockDetailClient({ stock, cellRules }: Props) {
  const [selected, setSelected] = useState<Tenure | null>('3m')

  function rulesFor(tenure: Tenure): CellRule[] {
    const v = stock.conviction_tape[tenure]
    if (v.direction === 'NEUTRAL') return []
    const cellId = `${stock.tier}-${tenure}-${v.direction}`
    return cellRules.get(cellId) ?? []
  }

  const rules = selected ? rulesFor(selected) : []
  const v = selected ? stock.conviction_tape[selected] : null

  // Composite score = sum of POS IC across 4 segments * 100, clamped 0..100.
  const compositeScore = Math.max(0, Math.min(100, Math.round(
    (['1m', '3m', '6m', '12m'] as const).reduce((sum, t) => {
      const seg = stock.conviction_tape[t]
      if (seg.direction === 'POSITIVE') return sum + (seg.ic ?? 0) * 100 * 4
      if (seg.direction === 'NEGATIVE') return sum - (seg.ic ?? 0) * 100 * 4
      return sum
    }, 50)
  )))

  return (
    <>
      <div className="px-6 py-5 border-b border-paper-rule">
        <div className="flex items-start justify-between gap-6 flex-wrap">
          <div>
            <div className="font-sans text-[10px] uppercase tracking-wider text-ink-tertiary mb-2">
              Conviction Tape
            </div>
            <ConvictionTape
              tape={stock.conviction_tape}
              selected={selected}
              onSegmentClick={t => setSelected(t)}
            />
            <div className="font-sans text-[11px] text-ink-tertiary mt-2 leading-relaxed">
              Click any segment to see the firing cell&apos;s top rule below.
            </div>
          </div>
          <div className="flex items-baseline gap-4">
            <div>
              <div className="font-sans text-[10px] uppercase tracking-wider text-ink-tertiary mb-1">Composite</div>
              <div className="font-mono text-3xl font-semibold tabular-nums text-ink-primary leading-none">
                {compositeScore} <span className="text-base text-ink-tertiary">/ 100</span>
              </div>
            </div>
            {stock.rs_state && (
              <div>
                <div className="font-sans text-[10px] uppercase tracking-wider text-ink-tertiary mb-1">RS</div>
                <StateBadge state={stock.rs_state} />
              </div>
            )}
          </div>
        </div>
      </div>

      {selected && v && (
        <div className="px-6 py-5 border-b border-paper-rule">
          <h2 className="font-sans text-xs font-medium text-ink-tertiary uppercase tracking-wider mb-3">
            {selected} {v.direction} — {v.rule_count} rule{v.rule_count === 1 ? '' : 's'} firing · IC <ELI5Tooltip term="ic">{formatIC(v.ic)}</ELI5Tooltip>
          </h2>
          {rules.length === 0 ? (
            <p className="font-sans text-sm text-ink-secondary">
              No rule detail available for this cell yet — the demo fixture only
              includes top-5 rules for green cells. The live endpoint returns
              firing rules per (tier, tenure, direction).
            </p>
          ) : (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              {rules.slice(0, 4).map(rule => (
                <RuleCard key={rule.rule_id} rule={rule} cellId={`${stock.tier}-${selected}-${v.direction}`} />
              ))}
            </div>
          )}
        </div>
      )}

      <div className="px-6 py-5">
        <h2 className="font-sans text-xs font-medium text-ink-tertiary uppercase tracking-wider mb-3">
          Returns
        </h2>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <ReturnTile label="1M" value={stock.ret_1m} />
          <ReturnTile label="3M" value={stock.ret_3m} />
          <ReturnTile label="6M" value={stock.ret_6m} />
          <ReturnTile label="12M" value={stock.ret_12m} />
        </div>
      </div>
    </>
  )
}

function ReturnTile({ label, value }: { label: string; value: number | null }) {
  if (value == null) return (
    <div className="border border-paper-rule rounded-[2px] p-3 bg-paper">
      <div className="font-sans text-[10px] uppercase tracking-wider text-ink-tertiary">{label}</div>
      <div className="font-mono text-xl font-semibold tabular-nums text-ink-tertiary mt-1">—</div>
    </div>
  )
  const pct = value * 100
  const sign = pct >= 0 ? '+' : ''
  const cls = pct >= 0 ? 'text-signal-pos' : 'text-signal-neg'
  return (
    <div className="border border-paper-rule rounded-[2px] p-3 bg-paper">
      <div className="font-sans text-[10px] uppercase tracking-wider text-ink-tertiary">{label}</div>
      <div className={`font-mono text-xl font-semibold tabular-nums ${cls} mt-1`}>{sign}{pct.toFixed(1)}%</div>
    </div>
  )
}
