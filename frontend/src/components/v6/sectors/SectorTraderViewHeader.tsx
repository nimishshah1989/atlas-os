// SectorTraderViewHeader — canonical trader-view header for /sectors/[name].
// Maps sector_state ("Overweight"/"Neutral"/"Underweight"/"Avoid") to the
// canonical BUY/WATCH/AVOID vocabulary.
//
// Spec: docs/superpowers/specs/2026-05-28-trader-view-redesign.html §8

import type { SectorDeepdiveRow } from '@/lib/queries/v6/sectors'
import {
  VerdictPill,
  WhyStrip,
  type Chip,
  type Verdict,
} from '@/components/v6/trader-view'

function mapSectorVerdict(state: string | null | undefined): Verdict {
  if (!state) return 'WATCH'
  const s = state.toLowerCase()
  if (s === 'overweight')  return 'BUY'
  if (s === 'neutral')     return 'WATCH'
  if (s === 'underweight') return 'AVOID'
  if (s === 'avoid')       return 'AVOID'
  return 'WATCH'
}

function fmtPct(v: string | number | null | undefined, decimals = 1): string {
  if (v == null) return '—'
  const n = typeof v === 'number' ? v : Number(v)
  if (!Number.isFinite(n)) return '—'
  const sign = n >= 0 ? '+' : ''
  return `${sign}${(n * 100).toFixed(decimals)}%`
}

export function SectorTraderViewHeader({ sector }: { sector: SectorDeepdiveRow }) {
  const verdict = mapSectorVerdict(sector.verdict)
  const rs3m = sector.rs_windows?.rs_3m ?? null
  const ret3m = sector.returns?.ret_3m ?? null

  const chips: Chip[] = [
    {
      label: 'Constituents',
      value: `${sector.constituent_count ?? '—'} stocks`,
      state: 'neutral',
    },
    {
      label: 'RS 3M',
      value: rs3m != null
        ? `${rs3m >= 0 ? '+' : ''}${(rs3m * 100).toFixed(1)}% vs Nifty 500`
        : '—',
      state: rs3m == null ? 'neutral'
           : rs3m > 0.02 ? 'pass'
           : rs3m < -0.02 ? 'fail'
           : 'neutral',
    },
    {
      label: 'Abs 3M',
      value: fmtPct(ret3m),
      state: 'neutral',
    },
    {
      label: 'Verdict',
      value: sector.verdict ?? '—',
      state: verdict === 'BUY' ? 'pass' : verdict === 'AVOID' ? 'fail' : 'neutral',
    },
  ]

  return (
    <div className="border-b border-ink-rule px-6 py-5 bg-paper">
      <div className="flex flex-col gap-3">
        <VerdictPill verdict={verdict} />

        <div className="font-mono text-[15px] text-ink-secondary">
          Sector verdict for{' '}
          <strong className="text-ink-primary font-semibold">{sector.sector_name}</strong>
          {' · '}
          <span className="text-ink-tertiary">{sector.constituent_count ?? '—'} constituents</span>
        </div>

        <div className="text-[12px] text-ink-tertiary max-w-prose">
          {verdict === 'BUY' && 'Sector showing strength on relative-strength + bottom-up breadth. Look for leaders in the constituents table below.'}
          {verdict === 'AVOID' && 'Sector under structural pressure. Most constituents in stage 3/4. Avoid new positions; rotate out of holdings.'}
          {verdict === 'WATCH' && 'Sector neither outperforming nor underperforming materially. Monitor — wait for clear directional move before adding.'}
        </div>
      </div>

      <WhyStrip chips={chips} />
    </div>
  )
}
