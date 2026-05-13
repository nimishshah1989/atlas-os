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

const TIER_INFO: Record<string, { label: string; range: string }> = {
  tier_1_megacap: { label: 'Mega-cap', range: 'ADV rank 1–50 (top 50 NSE stocks by daily traded value)' },
  tier_2_largecap: { label: 'Large-cap', range: 'ADV rank 51–150' },
  tier_3_uppermid: { label: 'Upper Mid-cap', range: 'ADV rank 151–300' },
  tier_4_lowermid: { label: 'Lower Mid-cap', range: 'ADV rank 301–500' },
  tier_5_smallcap: { label: 'Small-cap', range: 'ADV rank 501–1000' },
}

function buildConvictionTooltip(row: ConvictionMapRow): string {
  const score = Math.round(Number(row.conviction_score) * 100)
  const info = TIER_INFO[row.tier] ?? { label: row.tier, range: '' }
  const standing = score >= 70 ? 'top 30% of peers' : score >= 50 ? 'above median' : score >= 30 ? 'below median' : 'bottom 30% of peers'
  return [
    `${score}/100 — ${standing} in the ${info.label} tier`,
    `Tier: ${info.range}`,
    '',
    '50 = median. 70+ = top 30%. 30 or below = bottom 30%.',
    'Ranks momentum, trend, volume, and risk against size-similar stocks only.',
    'Do not compare across tiers (Mega vs Small scores are not comparable).',
  ].join('\n')
}


export function ConvictionCell({ row }: Props) {
  if (!row) {
    return <span className="font-mono text-xs text-ink-tertiary">—</span>
  }
  const score = Math.round(Number(row.conviction_score) * 100)
  const tierLabel = TIER_NAMES[row.tier] ?? row.tier
  const barCls = score >= 70 ? 'bg-teal' : score >= 50 ? 'bg-amber-500' : 'bg-paper-rule'
  const scoreColor = score >= 70 ? 'text-teal' : score >= 50 ? 'text-amber-500' : 'text-ink-secondary'

  return (
    <div
      className="flex flex-col gap-0.5 min-w-[110px]"
      title={buildConvictionTooltip(row)}
    >
      <div className="flex items-center gap-2">
        <div className="relative flex-1 h-1.5 bg-paper-rule rounded-full overflow-hidden">
          <div
            className={`h-full ${barCls} rounded-full`}
            style={{ width: `${Math.max(score, 6)}%` }}
          />
        </div>
        <span className={`font-mono text-xs font-semibold tabular-nums w-8 text-right ${scoreColor}`}>
          {score}
        </span>
      </div>
      <span className="font-sans text-[10px] text-ink-tertiary">{tierLabel} peers</span>
    </div>
  )
}
