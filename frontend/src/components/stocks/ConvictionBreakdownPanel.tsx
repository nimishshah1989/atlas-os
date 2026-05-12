// SP04 Stage 3 — breakdown panel showing per-signal contributions to the
// composite conviction score on the stock deep-dive page.
import type { ConvictionBreakdown } from '@/lib/queries/conviction'

type Props = {
  conviction: {
    conviction_score: string
    tier: string
    confidence_label: string
    backing_ic: string | null
  } | null
  breakdown: Record<string, ConvictionBreakdown> | null
}

const SIGNAL_LABELS: Record<string, string> = {
  ma_30w_slope_4w: '30-week MA slope (trend)',
  ret_6m: '6-month return',
  ret_12m_1m: '12-1m momentum factor',
  extension_pct: 'Distance from MA',
  vol_ratio_63: '63-day vol ratio',
  effort_ratio_63: 'Effort ratio (vol/range)',
  realized_vol_63: '63-day realized volatility',
  max_drawdown_252: '1-year max drawdown',
  rs_pctile_3m: '3-month RS percentile',
  ema_10_ratio: '10-day EMA ratio',
  atr_21: '21-day ATR (penalty)',
}

const TIER_DISPLAY: Record<string, string> = {
  tier_1_megacap: 'Tier 1 (mega-cap)',
  tier_2_largecap: 'Tier 2 (large-cap)',
  tier_3_uppermid: 'Tier 3 (upper mid-cap)',
  tier_4_lowermid: 'Tier 4 (lower mid-cap)',
  tier_5_smallcap: 'Tier 5 (small-cap)',
}

export function ConvictionBreakdownPanel({ conviction, breakdown }: Props) {
  if (!conviction || !breakdown) {
    return (
      <section className="border-t border-paper-rule pt-6 mt-6">
        <h3 className="font-sans text-[11px] text-ink-tertiary uppercase tracking-wider mb-3">
          Conviction Breakdown
        </h3>
        <p className="font-sans text-sm text-ink-tertiary">
          No conviction score available for this stock today. The composite
          requires the stock to be in the top 1000 by 20-day ADV and to have
          metrics computed for the most recent date.
        </p>
      </section>
    )
  }

  const score = Math.round(Number(conviction.conviction_score) * 100)
  const ic = conviction.backing_ic ? Number(conviction.backing_ic) : null
  const tierLabel = TIER_DISPLAY[conviction.tier] ?? conviction.tier
  const isIndustryGrade = conviction.confidence_label === 'industry_grade'

  const entries = Object.entries(breakdown).sort(
    (a, b) => Math.abs(b[1].contribution) - Math.abs(a[1].contribution),
  )
  const maxAbsContrib = Math.max(
    ...entries.map(([, b]) => Math.abs(b.contribution)),
    0.001,
  )

  return (
    <section className="border-t border-paper-rule pt-6 mt-6">
      <div className="flex items-baseline justify-between mb-3 flex-wrap gap-2">
        <h3 className="font-sans text-[11px] text-ink-tertiary uppercase tracking-wider">
          Conviction Breakdown
        </h3>
        <div className="font-sans text-[11px] text-ink-tertiary flex items-center gap-2">
          <span>
            Score{' '}
            <span className="font-mono text-ink-primary tabular-nums">
              {score}
            </span>
          </span>
          <span>·</span>
          <span
            className={`inline-flex items-center px-1.5 py-0.5 rounded border text-[10px] font-semibold ${
              isIndustryGrade
                ? 'bg-teal/10 text-teal border-teal/30'
                : 'bg-ink-tertiary/10 text-ink-secondary border-ink-tertiary/30'
            }`}
          >
            {isIndustryGrade ? '★ Industry-Grade' : 'Baseline'}
          </span>
          <span>{tierLabel}</span>
          {ic !== null && (
            <>
              <span>·</span>
              <span>
                Backing IC{' '}
                <span className="font-mono text-ink-primary tabular-nums">
                  {ic.toFixed(4)}
                </span>
              </span>
            </>
          )}
        </div>
      </div>

      <div className="space-y-1.5">
        {entries.map(([signal, info]) => {
          const widthPct = (Math.abs(info.contribution) / maxAbsContrib) * 100
          const label = SIGNAL_LABELS[signal] ?? signal
          return (
            <div
              key={signal}
              className="grid grid-cols-[200px_1fr_80px] gap-3 items-center text-xs"
            >
              <span
                className="font-sans text-ink-primary truncate"
                title={signal}
              >
                {label}
                {info.flipped && (
                  <span className="ml-1 text-[10px] text-ink-tertiary">
                    (flipped)
                  </span>
                )}
                {info.was_neutral_fill && (
                  <span
                    className="ml-1 text-[10px] text-signal-neg"
                    title="signal was NaN; neutral-filled to 0.5"
                  >
                    ⚠
                  </span>
                )}
              </span>
              <div className="relative h-1.5 bg-paper-rule rounded-full overflow-hidden">
                <div
                  className="h-full bg-teal/70 rounded-full"
                  style={{ width: `${widthPct}%` }}
                />
              </div>
              <span className="font-mono text-ink-secondary text-right tabular-nums">
                {(info.contribution * 100).toFixed(2)}
              </span>
            </div>
          )
        })}
      </div>
      <p className="font-sans text-[10px] text-ink-tertiary mt-4">
        Bar length = contribution to composite score (signal weight × percentile
        rank within tier, post-flip). Composite is IC-weighted from {tierLabel}{' '}
        training period 2019-2022, holdout 2023-2025.
      </p>
    </section>
  )
}
