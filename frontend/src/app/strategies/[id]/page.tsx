// src/app/strategies/[id]/page.tsx
// RSC — single strategy long-scroll detail page.
// Shell ≤250 LOC; each section is a self-contained component or inline block.
export const dynamic = 'force-dynamic'
import { notFound } from 'next/navigation'
import { getStrategyById } from '@/lib/queries/strategies'
import { getBacktestsForStrategy, getLatestBacktestForStrategy } from '@/lib/queries/backtests'
import { getPaperPerformance, getRecentPaperTrades } from '@/lib/queries/paper_perf'
import { KPICard } from '@/components/strategy/KPICard'
import { ReRunBacktestButton } from '@/components/strategy/ReRunBacktestButton'
import { EquityCurveChart } from './EquityCurveChart'
import { DrawdownChart } from './DrawdownChart'
import { RegimeBreakdownChart } from './RegimeBreakdownChart'
import { ConfigJSONViewer } from './ConfigJSONViewer'

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

export default async function StrategyDetailPage({ params }: Props) {
  const { id } = await params

  const [strategy, latestBt, allBts, perfRows, trades] = await Promise.all([
    getStrategyById(id),
    getLatestBacktestForStrategy(id),
    getBacktestsForStrategy(id, 50),
    getPaperPerformance(id),
    getRecentPaperTrades(id, 20),
  ])

  if (!strategy) notFound()

  const tierColor: Record<string, string> = {
    Aggressive: 'text-signal-neg bg-signal-neg/10 border-signal-neg/20',
    Moderate: 'text-signal-warn bg-signal-warn/10 border-signal-warn/20',
    Passive: 'text-signal-pos bg-signal-pos/10 border-signal-pos/20',
  }

  return (
    <main className="min-h-screen bg-paper px-8 py-6 max-w-5xl mx-auto">
      {/* In-page anchor nav */}
      <nav className="flex gap-4 text-xs font-sans text-ink-tertiary mb-6 border-b border-paper-rule pb-3">
        {['kpis', 'equity', 'drawdown', 'regime', 'backtests', 'paper', 'config'].map((anchor) => (
          <a key={anchor} href={`#${anchor}`} className="hover:text-ink-primary transition-colors capitalize">
            {anchor === 'kpis' ? 'KPIs' : anchor === 'config' ? 'Config' : anchor.charAt(0).toUpperCase() + anchor.slice(1)}
          </a>
        ))}
      </nav>

      {/* 1. Header */}
      <header className="mb-6">
        <div className="flex items-center gap-3 flex-wrap mb-1">
          <h1 className="font-serif text-2xl text-ink-primary">{strategy.name}</h1>
          <span
            className={`font-sans text-xs px-2 py-0.5 rounded-[2px] border ${tierColor[strategy.tier] ?? 'text-ink-secondary border-paper-rule'}`}
          >
            {strategy.tier}
          </span>
          <span className="font-sans text-xs text-ink-tertiary">{strategy.archetype.replace(/_/g, ' ')}</span>
          {strategy.paper_active && (
            <span className="inline-flex items-center gap-1.5 font-sans text-xs text-signal-pos">
              <span className="inline-block w-2 h-2 rounded-full bg-signal-pos" />
              Paper Active
            </span>
          )}
        </div>
        <p className="font-sans text-xs text-ink-tertiary">
          Variant: <span className="font-mono">{strategy.variant}</span>
        </p>
        {strategy.description && (
          <p className="font-sans text-sm text-ink-secondary mt-3 max-w-2xl leading-relaxed">
            {strategy.description}
          </p>
        )}
      </header>

      {/* 2. KPI cards */}
      <section id="kpis" className="mb-8">
        <h2 className="font-sans text-xs font-semibold uppercase tracking-wide text-ink-secondary mb-3">Performance Metrics</h2>
        <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
          <KPICard label="Sharpe Ratio" value={fmtSharpe(latestBt?.sharpe_ratio ?? null)} />
          <KPICard label="Max Drawdown" value={fmtPct(latestBt?.max_drawdown ?? null)} />
          <KPICard label="Total Return" value={fmtPct(latestBt?.total_return ?? null)} />
          <KPICard
            label="Alpha vs Nifty500"
            value={fmtPct(latestBt?.alpha_vs_nifty500 ?? null)}
            delta={latestBt?.alpha_vs_nifty500 != null ? 'vs Nifty500' : undefined}
            deltaPositive={latestBt?.alpha_vs_nifty500 != null && parseFloat(latestBt.alpha_vs_nifty500) >= 0}
          />
          <KPICard label="Alpha vs Naive Atlas" value={fmtPct(latestBt?.alpha_vs_naive_atlas ?? null)} />
          <KPICard label="Walk-forward OOS Sharpe" value={fmtSharpe(latestBt?.walk_forward_oos_sharpe ?? null)} />
        </div>
      </section>

      {/* 3. Action bar — Re-run Backtest */}
      <section className="mb-8 flex items-center gap-3">
        <ReRunBacktestButton strategyId={strategy.id} strategyName={strategy.name} />
        {latestBt && (
          <span className="font-sans text-xs text-ink-tertiary">
            Last backtest: {fmtDate(latestBt.created_at)}&nbsp;·&nbsp;
            {fmtDate(latestBt.start_date)} — {fmtDate(latestBt.end_date)}
          </span>
        )}
      </section>

      {/* 4. Equity curve */}
      <section id="equity" className="mb-8">
        <h2 className="font-sans text-xs font-semibold uppercase tracking-wide text-ink-secondary mb-3">Equity Curve</h2>
        <EquityCurveChart data={perfRows} />
      </section>

      {/* 5. Drawdown */}
      <section id="drawdown" className="mb-8">
        <h2 className="font-sans text-xs font-semibold uppercase tracking-wide text-ink-secondary mb-3">Drawdown</h2>
        <DrawdownChart data={perfRows} />
      </section>

      {/* 6. Regime breakdown */}
      <section id="regime" className="mb-8">
        <h2 className="font-sans text-xs font-semibold uppercase tracking-wide text-ink-secondary mb-3">Regime Breakdown</h2>
        <RegimeBreakdownChart breakdown={latestBt?.regime_breakdown ?? null} />
      </section>

      {/* 7. Backtest history */}
      <section id="backtests" className="mb-8">
        <h2 className="font-sans text-xs font-semibold uppercase tracking-wide text-ink-secondary mb-3">Backtest History</h2>
        {allBts.length === 0 ? (
          <p className="font-sans text-sm text-ink-tertiary">No backtests run yet.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="border-b border-paper-rule">
                  {['Date', 'Range', 'Sharpe', 'Max DD', 'Total Return', 'Alpha N500'].map((col) => (
                    <th key={col} className="font-sans text-xs text-ink-tertiary uppercase tracking-wide pb-2 pr-4 font-medium">
                      {col}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {allBts.map((bt) => (
                  <tr key={bt.id} className="border-b border-paper-rule/50">
                    <td className="py-2 pr-4 font-sans text-xs text-ink-secondary">{fmtDate(bt.created_at)}</td>
                    <td className="py-2 pr-4 font-mono text-xs text-ink-tertiary">
                      {fmtDate(bt.start_date)} — {fmtDate(bt.end_date)}
                    </td>
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

      {/* 8. Recent paper trades (only if paper active) */}
      {strategy.paper_active && (
        <section id="paper" className="mb-8">
          <h2 className="font-sans text-xs font-semibold uppercase tracking-wide text-ink-secondary mb-3">Recent Paper Trades</h2>
          {trades.length === 0 ? (
            <p className="font-sans text-sm text-ink-tertiary">No paper trades recorded yet.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left border-collapse">
                <thead>
                  <tr className="border-b border-paper-rule">
                    {['Date', 'Instrument', 'Action', 'Signal', 'Price', 'Weight', 'Regime'].map((col) => (
                      <th key={col} className="font-sans text-xs text-ink-tertiary uppercase tracking-wide pb-2 pr-4 font-medium">
                        {col}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {trades.map((t) => (
                    <tr key={t.id} className="border-b border-paper-rule/50">
                      <td className="py-2 pr-4 font-sans text-xs text-ink-secondary">{fmtDate(t.trade_date)}</td>
                      <td className="py-2 pr-4 font-mono text-xs text-ink-primary">{t.instrument_id}</td>
                      <td className={`py-2 pr-4 font-sans text-xs font-medium ${t.action === 'BUY' ? 'text-signal-pos' : 'text-signal-neg'}`}>
                        {t.action}
                      </td>
                      <td className="py-2 pr-4 font-sans text-xs text-ink-tertiary">{t.signal_type}</td>
                      <td className="py-2 pr-4 font-mono text-xs text-right">
                        ₹{parseFloat(t.price).toLocaleString('en-IN', { maximumFractionDigits: 2 })}
                      </td>
                      <td className="py-2 pr-4 font-mono text-xs text-right">{(parseFloat(t.weight_pct) * 100).toFixed(2)}%</td>
                      <td className="py-2 font-sans text-xs text-ink-tertiary">{t.regime_at_trade}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      )}

      {/* 9. Config viewer */}
      <section id="config" className="mb-8">
        <h2 className="font-sans text-xs font-semibold uppercase tracking-wide text-ink-secondary mb-3">Strategy Parameters</h2>
        <ConfigJSONViewer config={strategy.config} />
      </section>
    </main>
  )
}
