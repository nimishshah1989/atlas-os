// frontend/src/components/v6/RuleCard.tsx
//
// Three-zone card for a single CellRule:
//   1. name + archetype tag
//   2. ELI5 + predicates list
//   3. IC mean / IR / q / fric-adj + PerWindowChart

import type { CellRule } from '@/lib/api/v1'
import { ELI5Tooltip } from './ELI5Tooltip'
import { PerWindowChart } from './PerWindowChart'
import { formatIC, formatICSigned, formatQ, formatFricAdj, formatGatePass } from '@/lib/format-cell'

type Props = {
  rule: CellRule
  cellId?: string
}

export function RuleCard({ rule, cellId }: Props) {
  const windows = rule.per_window_stability.map((v, i) => ({
    label: `W${i + 1}`,
    value: v,
    passed: i < rule.gate_pass_count,
  }))

  return (
    <div className="border border-paper-rule rounded-[2px] bg-paper p-4">
      {/* Zone 1: name + archetype */}
      <div className="flex items-baseline justify-between gap-3 mb-2.5">
        <span className="font-mono text-sm font-semibold text-ink-primary tabular-nums break-all">
          {rule.name}
        </span>
        <ELI5Tooltip term={rule.archetype}>
          <span className="font-sans text-[10px] uppercase tracking-wider text-ink-tertiary shrink-0">
            {rule.archetype}
          </span>
        </ELI5Tooltip>
      </div>

      {/* Zone 2: ELI5 + predicates */}
      <p className="font-sans text-xs text-ink-secondary leading-relaxed mb-3">
        {rule.eli5}
      </p>
      {rule.predicates_natural.length > 0 && (
        <div className="mb-3">
          <div className="font-sans text-[10px] uppercase tracking-wider text-ink-tertiary mb-1">
            Predicates
          </div>
          <ul className="space-y-0.5">
            {rule.predicates_natural.map((p, i) => (
              <li key={i} className="font-mono text-[11px] text-ink-secondary tabular-nums">
                <span className="text-ink-tertiary mr-1.5">•</span>
                {p}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Zone 3: metrics + per-window chart */}
      <div className="flex items-start justify-between gap-4 pt-2.5 border-t border-paper-rule/60">
        <dl className="grid grid-cols-2 gap-x-4 gap-y-1.5 text-[11px]">
          <dt className="font-sans text-ink-tertiary">
            <ELI5Tooltip term="ic_mean">IC mean</ELI5Tooltip>
          </dt>
          <dd className="font-mono tabular-nums text-ink-primary">{formatICSigned(rule.ic_mean)}</dd>

          <dt className="font-sans text-ink-tertiary">
            <ELI5Tooltip term="ic_ir">IC IR</ELI5Tooltip>
          </dt>
          <dd className="font-mono tabular-nums text-ink-primary">{formatIC(rule.ic_ir)}</dd>

          <dt className="font-sans text-ink-tertiary">
            <ELI5Tooltip term="q_value">q-value</ELI5Tooltip>
          </dt>
          <dd className="font-mono tabular-nums text-ink-primary">{formatQ(rule.q_value)}</dd>

          <dt className="font-sans text-ink-tertiary">
            <ELI5Tooltip term="fric_adj_excess">Fric-adj (ann)</ELI5Tooltip>
          </dt>
          <dd className={`font-mono tabular-nums ${rule.fric_adj_excess_mean_ann != null && rule.fric_adj_excess_mean_ann >= 0 ? 'text-signal-pos' : 'text-signal-neg'}`}>
            {formatFricAdj(rule.fric_adj_excess_mean_ann)}
          </dd>

          <dt className="font-sans text-ink-tertiary">
            <ELI5Tooltip term="gate_pass">Gate pass</ELI5Tooltip>
          </dt>
          <dd className="font-mono tabular-nums text-ink-primary">{formatGatePass(rule.gate_pass_count, rule.gate_total)}</dd>

          <dt className="font-sans text-ink-tertiary">Population today</dt>
          <dd className="font-mono tabular-nums text-ink-primary">
            {rule.population_today} {cellId ? 'stocks' : ''}
          </dd>
        </dl>
        <div className="shrink-0">
          <div className="font-sans text-[10px] uppercase tracking-wider text-ink-tertiary mb-1 text-right">
            <ELI5Tooltip term="per_window_stability">Per-window</ELI5Tooltip>
          </div>
          <PerWindowChart windows={windows} />
        </div>
      </div>
    </div>
  )
}
