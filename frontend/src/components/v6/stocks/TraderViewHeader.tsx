// TraderViewHeader — the canonical trader-view header for /stocks/[symbol].
//
// Composes the 5 shared trader-view components (VerdictPill, ReturnLine,
// SinceCallLine, WhyStrip, TrackingGrid) with data from
// atlas.mv_stock_landscape_trader (see query at
// frontend/src/lib/queries/v6/stock-trader-header.ts).
//
// Spec: docs/superpowers/specs/2026-05-28-trader-view-redesign.html §8
// Mockup: docs/v6/mockup-trader-view.html

import {
  VerdictPill,
  ReturnLine,
  SinceCallLine,
  WhyStrip,
  type Chip,
} from '@/components/v6/trader-view'
import type { StockTraderHeader as StockTraderHeaderData } from '@/lib/queries/v6/stock-trader-header'

export function TraderViewHeader({ data }: { data: StockTraderHeaderData | null }) {
  if (!data) {
    return (
      <div className="border-b border-paper-rule px-6 py-4 bg-paper-soft">
        <div className="text-[12px] text-ink-tertiary">
          No Atlas math yet for this stock — composite_score and signal_call both NULL.
        </div>
      </div>
    )
  }

  // Source-aware chip strings
  const sourceChip: Chip = (() => {
    if (data.verdict_source === 'signal_call') {
      return {
        label: 'Source',
        value: `Cell math · ${data.cell_tenure ?? '—'} ${data.cell_action ?? ''}${data.cell_ic != null ? ` · IC ${data.cell_ic.toFixed(3)}` : ''}`,
        state: 'pass',
      }
    }
    if (data.verdict_source === 'composite_score') {
      return {
        label: 'Source',
        value: `Composite ${data.composite_score != null ? data.composite_score.toFixed(2) : '—'} (statistical, low-confidence)`,
        state: 'neutral',
      }
    }
    return {
      label: 'Source',
      value: 'No Atlas math yet — composite + signal both NULL',
      state: 'neutral',
    }
  })()

  const convictionChip: Chip = {
    label: 'Conviction',
    value: data.conviction_tier
      ? `${data.conviction_tier}${data.conviction_score != null ? ` · ${data.conviction_score.toFixed(2)}` : ''}`
      : '—',
    state: data.conviction_tier === 'T1' ? 'pass'
         : data.conviction_tier === 'T2' ? 'pass'
         : data.conviction_tier === 'T3' ? 'neutral'
         : data.conviction_tier === 'T4' ? 'warn'
         : data.conviction_tier === 'T5' ? 'warn'
         : 'neutral',
  }

  const capTierChip: Chip = {
    label: 'Tier',
    value: data.cap_tier ?? '—',
    state: 'neutral',
  }

  const chips: Chip[] = [sourceChip, convictionChip, capTierChip]
  if (data.verdict_reason) {
    chips.push({ label: 'Reason', value: data.verdict_reason, state: 'warn' })
  }

  return (
    <div className="border-b border-ink-rule px-6 py-5 bg-paper">
      <div className="flex flex-col gap-3">
        {/* Verdict pill — large, color-coded, opacity-modulated by conviction tier */}
        <VerdictPill
          verdict={data.combined_verdict ?? null}
          convictionTier={data.conviction_tier}
        />

        {/* Expected return + tier badge */}
        <ReturnLine
          predictedExcess={data.cell_predicted_excess}
          tenure={data.cell_tenure}
          convictionTier={data.conviction_tier}
          convictionScore={data.conviction_score}
          verdictSource={data.verdict_source}
        />

        {/* First-called + days held + since-call return */}
        <SinceCallLine
          firstCalledAt={data.first_called_at}
          verdict={data.combined_verdict ?? '—'}
          sinceCallReturn={data.since_call_return}
        />
      </div>

      {/* Why-strip — explains the verdict source + confidence */}
      <WhyStrip chips={chips} />
    </div>
  )
}
