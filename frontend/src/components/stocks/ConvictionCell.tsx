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
  const ic = row.backing_ic ? Number(row.backing_ic) : null
  const icStr = ic !== null ? ic.toFixed(4) : null

  let gradeNote: string
  if (row.confidence_label === 'industry_grade') {
    gradeNote = `★ Industry-Grade (IC ${icStr}): composite was directionally predictive in 2023–25 holdout backtest. IC ≥ 0.05 means the ranking was right ~52–53% of the time — that's a meaningful edge. High scores here carry weight.`
  } else if (row.confidence_label === 'baseline') {
    gradeNote = `Baseline (IC ${icStr ?? '—'}): same composite formula, but IC < 0.05 — didn't clear the validation bar in backtest. Still useful for relative comparison within this peer group, but don't treat a high score as a strong directional signal.`
  } else {
    gradeNote = 'Descriptive only: no holdout IC measured yet. Score computed but not validated.'
  }

  return [
    `Score ${score}/100 — percentile rank vs peers in the same liquidity tier`,
    `Tier: ${info.label} · ${info.range}`,
    `50 = average for this tier. Higher = stronger momentum, trend, volume, and risk profile vs peers.`,
    `Percentile ranks are within-tier only — a 70 here means beat 70% of stocks in the same liquidity bucket.`,
    '',
    gradeNote,
  ].join('\n')
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
      title={buildConvictionTooltip(row)}
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
