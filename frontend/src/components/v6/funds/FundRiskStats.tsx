// FundRiskStats — the return + risk box a fund manager reads first, derived from the fund's NAV
// history: trailing/compound returns, annualised volatility, Sharpe, Sortino, max drawdown.
// Restrained colour (returns + drawdown only) — these are read at a glance, not a heatmap.
import type { FundRiskStats as Stats } from '@/lib/v6/fundStats'
import { TermInfo } from '@/components/v6/shared/TermInfo'

const pct = (v: number | null, signed = false) =>
  v == null ? '—' : `${signed && v > 0 ? '+' : ''}${(v * 100).toFixed(1)}%`
const ratio = (v: number | null) => (v == null ? '—' : v.toFixed(2))
const retTone = (v: number | null) => (v == null ? 'text-txt-1' : v >= 0 ? 'text-sig-pos' : 'text-sig-neg')

function Metric({ label, value, tone, sub, term }: { label: string; value: string; tone?: string; sub?: string; term?: string }) {
  return (
    <div className="rounded-tile border border-edge-hair bg-surface-panel px-3 py-2.5">
      <div className="font-num text-[9px] uppercase tracking-wider text-txt-3">{label}{term && <TermInfo term={term} />}</div>
      <div className={`mt-1 font-num text-[18px] font-semibold tabular-nums ${tone ?? 'text-txt-1'}`}>{value}</div>
      {sub && <div className="mt-0.5 font-sans text-[10px] text-txt-3">{sub}</div>}
    </div>
  )
}

export function FundRiskStats({ stats }: { stats: Stats }) {
  if (stats.months < 2) return null // not enough NAV history to say anything
  const yrs = (stats.months / 12).toFixed(1)
  const metrics = [
    { label: '1Y return', value: pct(stats.ret1y, true), tone: retTone(stats.ret1y) },
    { label: '3Y CAGR', value: pct(stats.cagr3y, true), tone: retTone(stats.cagr3y) },
    { label: '5Y CAGR', value: pct(stats.cagr5y, true), tone: retTone(stats.cagr5y) },
    { label: `CAGR · ${yrs}y`, value: pct(stats.cagrIncept, true), tone: retTone(stats.cagrIncept), sub: 'since earliest NAV' },
    { label: 'Volatility', value: pct(stats.volAnn), sub: 'annualised', term: 'fund_volatility' },
    { label: 'Sharpe', value: ratio(stats.sharpe), sub: 'rf 6.5%', term: 'sharpe' },
    { label: 'Sortino', value: ratio(stats.sortino), sub: 'rf 6.5%', term: 'sortino' },
    { label: 'Max drawdown', value: pct(stats.maxDrawdown), tone: stats.maxDrawdown != null && stats.maxDrawdown < 0 ? 'text-sig-neg' : 'text-txt-1', term: 'max_drawdown' },
  ]
  return (
    <div>
      <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-4">
        {metrics.map((m) => <Metric key={m.label} {...m} />)}
      </div>
      <div className="mt-2 font-sans text-[11px] text-txt-3">
        From NAV history {stats.navFrom} → {stats.navTo} · {stats.months} monthly observations. Risk-free 6.5% for Sharpe/Sortino.
      </div>
    </div>
  )
}
