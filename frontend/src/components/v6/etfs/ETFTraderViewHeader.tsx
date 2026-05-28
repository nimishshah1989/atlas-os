// ETFTraderViewHeader — canonical trader-view header for /etfs/[ticker].
// Reuses the 5 shared trader-view components but derives verdict + chips
// from existing ETFRow fields (no new MV view needed).
//
// Spec: docs/superpowers/specs/2026-05-28-trader-view-redesign.html §8
// Mockup: docs/v6/mockup-trader-view.html

import type { ETFRow } from '@/lib/queries/etfs'
import {
  VerdictPill,
  WhyStrip,
  type Chip,
  type Verdict,
} from '@/components/v6/trader-view'

function deriveEtfVerdict(etf: ETFRow): { verdict: Verdict; reason: string | null } {
  // Gate veto first — if any of the 5 statutory gates fails, WAIT
  if (etf.strength_gate === false) return { verdict: 'WAIT', reason: 'Strength gate fail' }
  if (etf.direction_gate === false) return { verdict: 'WAIT', reason: 'Direction gate fail' }
  if (etf.risk_gate === false) return { verdict: 'WAIT', reason: 'Risk gate fail' }
  if (etf.sector_gate === false) return { verdict: 'WAIT', reason: 'Sector gate fail' }
  if (etf.market_gate === false) return { verdict: 'WAIT', reason: 'Market gate fail' }

  // is_investable = pct_stage_4 < 50% → POSITIVE; otherwise NEGATIVE
  if (etf.is_investable === true) return { verdict: 'BUY', reason: null }
  if (etf.is_investable === false) return { verdict: 'AVOID', reason: null }
  return { verdict: 'WATCH', reason: 'No Atlas math yet' }
}

function fmtPct(v: string | number | null | undefined): string {
  if (v == null) return '—'
  const n = typeof v === 'number' ? v : Number(v)
  if (!Number.isFinite(n)) return '—'
  const sign = n >= 0 ? '+' : ''
  return `${sign}${(n * 100).toFixed(1)}%`
}

export function ETFTraderViewHeader({ etf }: { etf: ETFRow }) {
  const { verdict, reason } = deriveEtfVerdict(etf)

  const passedGates = [
    etf.strength_gate, etf.direction_gate, etf.risk_gate,
    etf.sector_gate, etf.market_gate,
  ].filter((g) => g === true).length

  const chips: Chip[] = [
    {
      label: 'Gates',
      value: `${passedGates}/5 passing`,
      state: passedGates === 5 ? 'pass' : passedGates >= 3 ? 'warn' : 'fail',
    },
    {
      label: 'Engine state',
      value: etf.engine_state ?? '—',
      state: etf.engine_state === 'stage_2a' || etf.engine_state === 'stage_2b' ? 'pass'
           : etf.engine_state === 'stage_2c' ? 'warn'
           : etf.engine_state === 'stage_3' || etf.engine_state === 'stage_4' ? 'fail'
           : 'neutral',
    },
    {
      label: 'Weinstein',
      value: etf.weinstein_gate_pass === true ? 'above 30W MA · gate pass'
           : etf.weinstein_gate_pass === false ? 'below 30W MA · context only'
           : '—',
      state: 'neutral',
    },
    {
      label: 'Theme',
      value: etf.theme,
      state: 'neutral',
    },
  ]
  if (reason) chips.push({ label: 'Reason', value: reason, state: 'warn' })

  return (
    <div className="border-b border-ink-rule px-6 py-5 bg-paper">
      <div className="flex flex-col gap-3">
        <VerdictPill verdict={verdict} />

        <div className="font-mono text-[15px] text-ink-secondary flex items-center gap-3 flex-wrap">
          {etf.ret_3m != null && (
            <span>
              3M return{' '}
              <span className={`font-semibold ${Number(etf.ret_3m) >= 0 ? 'text-signal-pos' : 'text-signal-neg'}`}>
                {fmtPct(etf.ret_3m)}
              </span>
            </span>
          )}
          {etf.rs_pctile_3m != null && (
            <span className="text-ink-tertiary">
              · RS 3M pctile{' '}
              <span className="font-semibold text-ink-secondary">
                {(Number(etf.rs_pctile_3m) * 100).toFixed(0)}
              </span>
            </span>
          )}
          {etf.position_size_pct != null && Number(etf.position_size_pct) > 0 && (
            <span className="text-[10px] font-bold tracking-wider px-2 py-0.5 bg-accent/10 text-accent rounded-sm">
              POS {(Number(etf.position_size_pct) * 100).toFixed(1)}%
            </span>
          )}
        </div>

        <div className="text-[12px] text-ink-tertiary">
          {etf.ticker} · {etf.etf_name ?? '—'}
          {etf.asset_class && <> · <span className="font-mono">{etf.asset_class}</span></>}
        </div>
      </div>

      <WhyStrip chips={chips} />
    </div>
  )
}
