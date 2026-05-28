// FundTraderViewHeader — canonical trader-view header for /funds/[mstar_id].
// Maps fund recommendation + 4 gates → canonical BUY/WATCH/AVOID/WAIT.
//
// Spec: docs/superpowers/specs/2026-05-28-trader-view-redesign.html §8

import type { FundMasterRow } from '@/lib/queries/funds'
import {
  VerdictPill,
  WhyStrip,
  type Chip,
  type Verdict,
} from '@/components/v6/trader-view'

function mapFundVerdict(rec: string | null | undefined): Verdict {
  if (!rec) return 'WATCH'
  const r = rec.toLowerCase()
  if (r.includes('buy') || r.includes('aligned') || r.includes('overweight')) return 'BUY'
  if (r.includes('avoid') || r.includes('underweight') || r.includes('exit')) return 'AVOID'
  if (r.includes('hold') || r.includes('neutral')) return 'WATCH'
  return 'WATCH'
}

export function FundTraderViewHeader({ master }: { master: FundMasterRow }) {
  // Gate veto first: if any of the 4 fund gates fails AND recommendation
  // implies BUY, downgrade to WAIT.
  const baseVerdict = mapFundVerdict(master.recommendation)
  const gateFails: string[] = []
  if (master.performance_gate === false) gateFails.push('Performance')
  if (master.sectors_gate === false)     gateFails.push('Sectors')
  if (master.stocks_gate === false)      gateFails.push('Stocks')
  if (master.market_gate === false)      gateFails.push('Market')

  let verdict: Verdict = baseVerdict
  let reason: string | null = null
  if (baseVerdict === 'BUY' && gateFails.length > 0) {
    verdict = 'WAIT'
    reason = `${gateFails[0]} gate fail`
  }

  const passedGates = [
    master.performance_gate, master.sectors_gate,
    master.stocks_gate, master.market_gate,
  ].filter((g) => g === true).length

  const chips: Chip[] = [
    {
      label: 'Gates',
      value: `${passedGates}/4 passing`,
      state: passedGates === 4 ? 'pass' : passedGates >= 2 ? 'warn' : 'fail',
    },
    {
      label: 'NAV state',
      value: master.nav_state ?? '—',
      state: master.nav_state === 'Strong' ? 'pass'
           : master.nav_state === 'Weak' ? 'fail'
           : 'neutral',
    },
    {
      label: 'Holdings state',
      value: master.holdings_state ?? '—',
      state: master.holdings_state === 'Aligned' ? 'pass'
           : master.holdings_state === 'Avoid' ? 'fail'
           : 'neutral',
    },
    {
      label: 'AMC · Category',
      value: `${master.amc} · ${master.category_name}`,
      state: 'neutral',
    },
  ]
  if (reason) chips.push({ label: 'Reason', value: reason, state: 'warn' })

  const aumCr = master.aum_cr != null ? `₹${Number(master.aum_cr).toFixed(0)} Cr` : null

  return (
    <div className="border-b border-ink-rule px-6 py-5 bg-paper">
      <div className="flex flex-col gap-3">
        <VerdictPill verdict={verdict} />

        <div className="font-mono text-[15px] text-ink-secondary flex items-center gap-3 flex-wrap">
          {master.recommendation && (
            <span>Recommendation: <strong className="text-ink-primary">{master.recommendation}</strong></span>
          )}
          {aumCr && (
            <span className="text-ink-tertiary">
              · AUM <strong className="text-ink-secondary">{aumCr}</strong>
            </span>
          )}
        </div>

        <div className="text-[12px] text-ink-tertiary max-w-prose">
          <strong className="text-ink-secondary">{master.scheme_name}</strong>
          {verdict === 'BUY' && ' — fund passes performance + holdings + market gates. Aligned with Atlas-favoured stocks.'}
          {verdict === 'AVOID' && ' — fund holdings concentrate in Avoid-state stocks or sectors. Rotate to a better-aligned fund in the same category.'}
          {verdict === 'WATCH' && ' — fund is neither clearly favoured nor flagged. Monitor; check the holdings + composition lenses below.'}
          {verdict === 'WAIT' && ' — fund is favoured but a structural gate is failing. Wait for the gate to clear.'}
        </div>
      </div>

      <WhyStrip chips={chips} />
    </div>
  )
}
