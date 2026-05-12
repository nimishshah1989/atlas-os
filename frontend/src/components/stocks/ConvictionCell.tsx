// SP04 Stage 3 — table cell rendering for the conviction composite.
'use client'

import type { ConvictionMapRow } from '@/lib/queries/conviction'

type Props = {
  row: ConvictionMapRow | undefined
}

const TIER_NAMES: Record<string, string> = {
  tier_1_megacap: 'Mega',
  tier_2_largecap: 'Large',
  tier_3_uppermid: 'Mid',
  tier_4_lowermid: 'LowerMid',
  tier_5_smallcap: 'Small',
}

const CONFIDENCE_BADGES: Record<
  string,
  { label: string; cls: string; barCls: string }
> = {
  industry_grade: {
    label: '★ Industry',
    cls: 'bg-teal/10 text-teal border-teal/30',
    barCls: 'bg-teal',
  },
  baseline: {
    label: 'Baseline',
    cls: 'bg-ink-tertiary/10 text-ink-secondary border-ink-tertiary/30',
    barCls: 'bg-ink-tertiary',
  },
  descriptive_only: {
    label: '—',
    cls: 'text-ink-tertiary',
    barCls: 'bg-paper-rule',
  },
}

export function ConvictionCell({ row }: Props) {
  if (!row) {
    return <span className="font-mono text-xs text-ink-tertiary">—</span>
  }
  const score = Math.round(Number(row.conviction_score) * 100)
  const badge =
    CONFIDENCE_BADGES[row.confidence_label] ?? CONFIDENCE_BADGES.descriptive_only
  const tierLabel = TIER_NAMES[row.tier] ?? row.tier
  const ic = row.backing_ic ? Number(row.backing_ic).toFixed(3) : '—'

  return (
    <div
      className="flex flex-col gap-0.5 min-w-[140px]"
      title={`Conviction ${score} (${tierLabel}, ${row.confidence_label}, backing IC ${ic})`}
    >
      <div className="flex items-center gap-2">
        <div className="relative flex-1 h-1.5 bg-paper-rule rounded-full overflow-hidden">
          <div
            className={`h-full ${badge.barCls} rounded-full`}
            style={{ width: `${Math.max(score, 6)}%` }}
          />
        </div>
        <span className="font-mono text-xs font-semibold text-ink-primary tabular-nums w-8 text-right">
          {score}
        </span>
      </div>
      <div className="flex items-center gap-1.5">
        <span
          className={`inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-semibold border ${badge.cls}`}
        >
          {badge.label}
        </span>
        <span className="font-sans text-[10px] text-ink-tertiary">{tierLabel}</span>
      </div>
    </div>
  )
}
