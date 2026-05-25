// frontend/src/components/v6/PortfolioBadge.tsx
//
// Chip: "Held · 4 portfolios" (compact) or multi-line (expanded).
// Silent absence when state === null — FM-critic §1.3 critical gap #1.
// TODO(v6.1): expand tooltip to per-portfolio breakdown.

'use client'

import * as Tooltip from '@radix-ui/react-tooltip'
import { useId } from 'react'
import type { HoldingState } from '@/lib/queries/v6/portfolio_holdings'
import { formatPct } from '@/lib/v6/decimal'

export type PortfolioBadgeVariant = 'compact' | 'expanded'

export interface PortfolioBadgeProps {
  state: HoldingState | null
  variant?: PortfolioBadgeVariant
  className?: string
}

function portfolioLabel(count: number): string {
  return count === 1 ? 'portfolio' : 'portfolios'
}

function formatDate(iso: string | null): string {
  if (!iso) return 'unknown'
  const d = new Date(iso + 'T00:00:00')
  return d.toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' })
}

function CompactBadge({ count, label }: { count: number; label: string }): React.ReactElement {
  return (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-[2px] bg-paper-deep text-ink-primary text-[11px] font-sans font-medium leading-tight whitespace-nowrap">
      <span className="text-ink-secondary">Held</span>
      <span className="text-ink-tertiary">·</span>
      <span>{count}&nbsp;{label}</span>
    </span>
  )
}

function ExpandedBadge({
  count, label, weightStr, lastAddDate,
}: { count: number; label: string; weightStr: string; lastAddDate: string | null }): React.ReactElement {
  return (
    <span className="inline-flex flex-col gap-0.5">
      <span className="text-xs font-sans font-medium text-ink-primary">
        Held in {count}&nbsp;{label}
      </span>
      <span className="text-[11px] font-sans text-ink-secondary">
        {weightStr} aggregate book weight
      </span>
      {lastAddDate != null && (
        <span className="text-[11px] font-sans text-ink-tertiary">
          Last added {formatDate(lastAddDate)}
        </span>
      )}
    </span>
  )
}

export function PortfolioBadge({
  state,
  variant = 'compact',
  className = '',
}: PortfolioBadgeProps): React.ReactElement | null {
  const tooltipId = useId()

  // Silent absence — FM-critic spec: no holding means no badge
  if (state === null) return null

  const { portfolio_count, aggregate_weight, last_add_date } = state
  const label = portfolioLabel(portfolio_count)
  const weightStr = formatPct(aggregate_weight, { signed: false })
  const ariaLabel = `Held in ${portfolio_count} ${label}, aggregate ${weightStr}`
  const tooltipContent = [
    `Total ${portfolio_count} ${label}.`,
    `Aggregate weight ${weightStr}.`,
    `Last add: ${formatDate(last_add_date)}.`,
  ].join(' ')

  return (
    <Tooltip.Provider delayDuration={200}>
      <Tooltip.Root>
        <Tooltip.Trigger asChild>
          <span
            role="status"
            aria-label={ariaLabel}
            aria-describedby={tooltipId}
            className={['inline-flex flex-col gap-0.5 cursor-default', className].join(' ')}
          >
            {variant === 'compact' ? (
              <CompactBadge count={portfolio_count} label={label} />
            ) : (
              <ExpandedBadge
                count={portfolio_count}
                label={label}
                weightStr={weightStr}
                lastAddDate={last_add_date}
              />
            )}
          </span>
        </Tooltip.Trigger>
        <Tooltip.Portal>
          <Tooltip.Content
            id={tooltipId}
            sideOffset={4}
            className="z-50 max-w-xs bg-paper border border-paper-rule rounded-[2px] px-3 py-2 text-xs font-sans text-ink-secondary shadow-sm leading-relaxed"
          >
            {tooltipContent}
            {/* TODO(v6.1): per-portfolio breakdown (name + weight + entry date) */}
            <Tooltip.Arrow className="fill-paper-rule" />
          </Tooltip.Content>
        </Tooltip.Portal>
      </Tooltip.Root>
    </Tooltip.Provider>
  )
}
