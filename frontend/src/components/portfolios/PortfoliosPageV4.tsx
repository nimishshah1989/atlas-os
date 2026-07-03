// PortfoliosPageV4 — the /portfolios board: every model portfolio (rule-based
// strategy simulations + FM baskets), its live paper-track NAV and its backtest.
// All rows are REAL engine output (portfolio_run.py) — nothing is computed here.
import Link from 'next/link'
import { getPortfolios, type PortfolioSummary } from '@/lib/queries/portfolios'
import { Panel } from '@/components/ui/Panel'

const inr = (v: number | null) =>
  v == null ? '—' : `₹${v.toLocaleString('en-IN', { maximumFractionDigits: 0 })}`
const pct = (v: number | null, signed = true) =>
  v == null ? '—' : `${signed && v > 0 ? '+' : ''}${v.toFixed(1)}%`
const retTone = (v: number | null) =>
  v == null ? 'text-txt-3' : v >= 0 ? 'text-sig-pos' : 'text-sig-neg'

function Row({ p }: { p: PortfolioSummary }) {
  return (
    <tr className="border-b border-edge-hair transition-colors hover:bg-surface-raised/50">
      <td className="px-3 py-2.5">
        <Link href={`/portfolios/${p.id}`} className="font-sans text-[13px] font-semibold text-txt-1 no-underline hover:text-brand hover:underline">
          {p.name}
        </Link>
        <div className="font-sans text-[11px] text-txt-3">
          {p.kind === 'strategy' ? p.strategyLabel : 'FM basket'} · {p.assetClasses.join(' + ')}
        </div>
      </td>
      <td className="px-3 py-2.5 text-right font-num text-[12px] tabular-nums text-txt-2">{p.inceptionDate}</td>
      <td className="px-3 py-2.5 text-right font-num text-[13px] font-semibold tabular-nums text-txt-1">{inr(p.nav)}</td>
      <td className={`px-3 py-2.5 text-right font-num text-[13px] font-semibold tabular-nums ${retTone(p.sinceInceptionPct)}`}>
        {pct(p.sinceInceptionPct)}
      </td>
      <td className="px-3 py-2.5 text-right font-num text-[12px] tabular-nums text-txt-2">{p.nPositions ?? '—'}</td>
      <td className="px-3 py-2.5 text-right font-num text-[12px] tabular-nums text-txt-2">
        {p.nav && p.cash != null ? `${((p.cash / p.nav) * 100).toFixed(1)}%` : '—'}
      </td>
      <td className={`px-3 py-2.5 text-right font-num text-[13px] tabular-nums ${retTone(p.btTotalPct)}`}>
        {pct(p.btTotalPct)}
        {p.btYears != null && <span className="ml-1 font-sans text-[10px] text-txt-3">{p.btYears.toFixed(1)}y</span>}
      </td>
    </tr>
  )
}

export async function PortfoliosPageV4() {
  const portfolios = await getPortfolios()
  return (
    <div className="mx-auto max-w-[1400px] space-y-6 px-6 py-7">
      <div>
        <p className="font-num text-[9px] uppercase tracking-[0.14em] text-txt-3">Paper-traded · marked at every EOD</p>
        <h1 className="font-display text-[28px] font-medium tracking-tight text-txt-1">Portfolios</h1>
        <p className="mt-2 max-w-[860px] font-sans text-[13.5px] text-txt-2">
          Model portfolios run by the Atlas engine: rule-based strategies (EMA crossovers over the
          scored universe, entries ranked by composite when signals exceed slots) and FM baskets —
          both paper-traded from inception at real EOD closes, with a full-history backtest of the
          same rules. Glass-box: every trade, price and NAV row is inspectable below.
        </p>
      </div>

      <Panel bodyClassName="overflow-x-auto">
        {portfolios.length === 0 ? (
          <p className="px-5 py-6 font-sans text-[13px] italic text-txt-3">No portfolios yet.</p>
        ) : (
          <table className="w-full min-w-[880px]">
            <thead>
              <tr className="border-b border-edge-rule">
                {['Portfolio', 'Inception', 'NAV', 'Since inception', 'Positions', 'Cash', 'Backtest'].map((h, i) => (
                  <th key={h} className={`px-3 py-2 font-num text-[10px] uppercase tracking-wider text-txt-3 ${i === 0 ? 'text-left' : 'text-right'}`}>
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {portfolios.map((p) => <Row key={p.id} p={p} />)}
            </tbody>
          </table>
        )}
      </Panel>
    </div>
  )
}
