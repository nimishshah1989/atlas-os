// src/app/portfolios/[id]/page.tsx
// RSC — FM custom portfolio detail (Static or Rule-Based).
// Shell ≤250 LOC; composition + backtest logic in sub-components.
export const dynamic = 'force-dynamic'
import { notFound } from 'next/navigation'
import {
  getStaticPortfolioById,
  getRuleBasedPortfolioById,
  getBacktestsForPortfolio,
} from '@/lib/queries/portfolios'
import { getEffectivePolicy } from '@/lib/queries/policy'
import { KPICard } from '@/components/strategy/KPICard'
import { ReRunBacktestButton } from '@/components/strategy/ReRunBacktestButton'
import { EquityCurveChart } from '@/components/charts/EquityCurveChart'
import { DrawdownChart } from '@/components/charts/DrawdownChart'
import { PaperTradingToggle } from './PaperTradingToggle'
import { StaticComposition, RuleBasedComposition } from './CompositionView'
import { PolicyPanel } from '@/components/portfolio/PolicyPanel'

function fmtPct(raw: string | null): string {
  if (raw == null) return '—'
  const n = parseFloat(raw)
  return isNaN(n) ? '—' : `${n >= 0 ? '+' : ''}${(n * 100).toFixed(2)}%`
}

function fmtSharpe(raw: string | null): string {
  if (raw == null) return '—'
  const n = parseFloat(raw)
  return isNaN(n) ? '—' : n.toFixed(2)
}

function fmtDate(d: Date): string {
  const date = d instanceof Date ? d : new Date(String(d))
  return date.toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' })
}

type Props = { params: Promise<{ id: string }> }

export default async function PortfolioDetailPage({ params }: Props) {
  const { id } = await params

  const [staticPortfolio, ruleBasedPortfolio, effectivePolicy] = await Promise.all([
    getStaticPortfolioById(id),
    getRuleBasedPortfolioById(id),
    getEffectivePolicy(id),
  ])

  const isStatic = staticPortfolio != null
  if (!isStatic && ruleBasedPortfolio == null) notFound()

  const portfolio = isStatic ? staticPortfolio! : ruleBasedPortfolio!
  const type: 'static' | 'rule-based' = isStatic ? 'static' : 'rule-based'
  const paperActive = isStatic ? staticPortfolio!.paper_trading_active : false
  const backtests = await getBacktestsForPortfolio(id, type, 50)

  const typeBadgeStyle =
    type === 'static'
      ? 'text-accent bg-accent/10 border-accent/20'
      : 'text-signal-warn bg-signal-warn/10 border-signal-warn/20'

  return (
    <main className="min-h-screen bg-paper px-8 py-6 max-w-5xl mx-auto">
      <nav className="flex gap-4 text-xs font-sans text-ink-tertiary mb-6 border-b border-paper-rule pb-3">
        {['kpis', 'composition', 'equity', 'drawdown', 'backtests', 'policy'].map((anchor) => (
          <a key={anchor} href={`#${anchor}`} className="hover:text-ink-primary transition-colors capitalize">
            {anchor === 'kpis' ? 'KPIs' : anchor.charAt(0).toUpperCase() + anchor.slice(1)}
          </a>
        ))}
      </nav>

      <header className="mb-6">
        <div className="flex items-center gap-3 flex-wrap mb-1">
          <h1 className="font-serif text-2xl text-ink-primary">{portfolio.name}</h1>
          <span className={`font-sans text-xs px-2 py-0.5 rounded-[2px] border ${typeBadgeStyle}`}>
            {type === 'static' ? 'Static' : 'Rule-Based'}
          </span>
          {paperActive && (
            <span className="inline-flex items-center gap-1.5 font-sans text-xs text-signal-pos">
              <span className="inline-block w-2 h-2 rounded-full bg-signal-pos" />
              Paper Active
            </span>
          )}
        </div>
        <p className="font-sans text-xs text-ink-tertiary">Created {fmtDate(portfolio.created_at)}</p>
      </header>

      {/* Action bar — Re-run Backtest (rule-based portfolios only) */}
      {type === 'rule-based' && ruleBasedPortfolio && (
        <section className="mb-8 flex items-center gap-3">
          <ReRunBacktestButton
            strategyId={ruleBasedPortfolio.id}
            strategyName={portfolio.name}
          />
        </section>
      )}

      <section id="kpis" className="mb-8">
        <h2 className="font-sans text-xs font-semibold uppercase tracking-wide text-ink-secondary mb-3">Performance Metrics</h2>
        <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
          <KPICard label="Sharpe Ratio" value={fmtSharpe(portfolio.latest_sharpe)} />
          <KPICard label="Max Drawdown" value={fmtPct(portfolio.latest_max_drawdown)} />
          <KPICard
            label="Alpha vs Nifty500"
            value={fmtPct(portfolio.latest_alpha_vs_nifty500)}
            deltaPositive={portfolio.latest_alpha_vs_nifty500 != null && parseFloat(portfolio.latest_alpha_vs_nifty500) >= 0}
          />
        </div>
      </section>

      <section id="composition" className="mb-8">
        <h2 className="font-sans text-xs font-semibold uppercase tracking-wide text-ink-secondary mb-3">Composition</h2>
        {isStatic
          ? <StaticComposition instruments={staticPortfolio!.instruments} />
          : <RuleBasedComposition config={ruleBasedPortfolio!.config} />}
      </section>

      <section id="equity" className="mb-8">
        <h2 className="font-sans text-xs font-semibold uppercase tracking-wide text-ink-secondary mb-3">Equity Curve</h2>
        <EquityCurveChart data={[]} />
      </section>

      <section id="drawdown" className="mb-8">
        <h2 className="font-sans text-xs font-semibold uppercase tracking-wide text-ink-secondary mb-3">Drawdown</h2>
        <DrawdownChart data={[]} />
      </section>

      <section id="backtests" className="mb-8">
        <h2 className="font-sans text-xs font-semibold uppercase tracking-wide text-ink-secondary mb-3">Backtest History</h2>
        {backtests.length === 0 ? (
          <p className="font-sans text-sm text-ink-tertiary">No backtests run yet.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="border-b border-paper-rule">
                  {['Date', 'Range', 'Sharpe', 'Max DD', 'Total Return', 'Alpha N500'].map((col) => (
                    <th key={col} className="font-sans text-xs text-ink-tertiary uppercase tracking-wide pb-2 pr-4 font-medium">{col}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {backtests.map((bt) => (
                  <tr key={bt.id} className="border-b border-paper-rule/50">
                    <td className="py-2 pr-4 font-sans text-xs text-ink-secondary">{fmtDate(bt.created_at)}</td>
                    <td className="py-2 pr-4 font-mono text-xs text-ink-tertiary">{fmtDate(bt.start_date)} — {fmtDate(bt.end_date)}</td>
                    <td className="py-2 pr-4 font-mono text-sm text-right">{fmtSharpe(bt.sharpe_ratio)}</td>
                    <td className="py-2 pr-4 font-mono text-sm text-right text-signal-neg">{fmtPct(bt.max_drawdown)}</td>
                    <td className="py-2 pr-4 font-mono text-sm text-right">{fmtPct(bt.total_return)}</td>
                    <td className={`py-2 font-mono text-sm text-right ${bt.alpha_vs_nifty500 != null && parseFloat(bt.alpha_vs_nifty500) >= 0 ? 'text-signal-pos' : 'text-signal-neg'}`}>
                      {fmtPct(bt.alpha_vs_nifty500)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="mb-8">
        <h2 className="font-sans text-xs font-semibold uppercase tracking-wide text-ink-secondary mb-3">Paper Trading</h2>
        {isStatic
          ? <PaperTradingToggle portfolioId={id} currentActive={paperActive} />
          : <p className="font-sans text-sm text-ink-tertiary">Paper trading for Rule-Based portfolios connects in M16.</p>}
      </section>

      <section id="policy" className="mb-8">
        <h2 className="font-sans text-xs font-semibold uppercase tracking-wide text-ink-secondary mb-3">Trade Policy</h2>
        <PolicyPanel policy={effectivePolicy} />
      </section>
    </main>
  )
}
