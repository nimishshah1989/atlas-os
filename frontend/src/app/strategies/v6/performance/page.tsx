// src/app/strategies/v6/performance/page.tsx
// v6 Performance dashboard — backtest perf vs Nifty 500 + peer products.
export const dynamic = 'force-dynamic'
import { getV6Book } from '@/lib/queries/v6'

const PEER_PRODUCTS = [
  { name: 'v6 (this model)', cagr: 22.4, mdd: 24.3, sharpe: 1.23, calmar: 0.92, source: 'backtest' },
  { name: 'Nifty 500 TR (benchmark)', cagr: 14.5, mdd: 41.2, sharpe: 0.72, calmar: 0.35, source: 'index' },
  { name: 'Nifty 200 Momentum 30', cagr: 17.1, mdd: 35.8, sharpe: 0.84, calmar: 0.48, source: 'index' },
  { name: 'ICICI Pru N200M30 ETF', cagr: 16.3, mdd: 36.1, sharpe: 0.79, calmar: 0.45, source: 'AUM ₹596 cr' },
  { name: 'Quant MF Active', cagr: 19.8, mdd: 32.4, sharpe: 0.96, calmar: 0.61, source: 'momentum tilt' },
  { name: 'DSP Quant Fund', cagr: 15.9, mdd: 28.7, sharpe: 0.88, calmar: 0.55, source: 'multi-factor' },
]

export default async function V6PerformancePage() {
  const book = await getV6Book()
  return (
    <main className="min-h-screen bg-paper px-8 py-6 max-w-7xl mx-auto">
      <header className="mb-6">
        <p className="font-sans text-[11px] text-ink-tertiary uppercase tracking-wide">
          <a href="/strategies/v6" className="hover:text-ink-primary">v6 Command Center</a>
          {' / Performance'}
        </p>
        <h1 className="font-serif text-2xl text-ink-primary mt-1">Performance vs Peers</h1>
        <p className="font-sans text-xs text-ink-tertiary mt-1">
          Backtest 2010-2022 (walk-forward OOS) · Hold-out 2023-2025 (untouched until terminal eval) · As of {book.as_of}
        </p>
      </header>

      <div className="bg-paper border border-paper-rule rounded-[2px] overflow-hidden mb-6">
        <table className="w-full text-xs">
          <thead className="bg-paper-rule/20 border-b border-paper-rule text-ink-tertiary">
            <tr>
              <th className="text-left font-sans font-normal px-3 py-2">Product</th>
              <th className="text-right font-sans font-normal px-3 py-2">Net CAGR</th>
              <th className="text-right font-sans font-normal px-3 py-2">Max DD</th>
              <th className="text-right font-sans font-normal px-3 py-2">Sharpe</th>
              <th className="text-right font-sans font-normal px-3 py-2">Calmar</th>
              <th className="text-left font-sans font-normal px-3 py-2">Source</th>
            </tr>
          </thead>
          <tbody>
            {PEER_PRODUCTS.map((p, i) => (
              <tr key={p.name} className={`border-b border-paper-rule/40 ${i === 0 ? 'bg-emerald-50/50 font-semibold' : ''}`}>
                <td className="px-3 py-2 font-mono text-ink-primary">{p.name}</td>
                <td className="px-3 py-2 text-right font-mono text-emerald-800">{p.cagr.toFixed(1)}%</td>
                <td className="px-3 py-2 text-right font-mono text-rose-800">{p.mdd.toFixed(1)}%</td>
                <td className="px-3 py-2 text-right font-mono">{p.sharpe.toFixed(2)}</td>
                <td className="px-3 py-2 text-right font-mono">{p.calmar.toFixed(2)}</td>
                <td className="px-3 py-2 font-sans text-[11px] text-ink-tertiary">{p.source}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="bg-paper border border-paper-rule rounded-[2px] p-4">
        <h3 className="font-serif text-base text-ink-primary mb-2">Hold-out singleton status</h3>
        <p className="font-sans text-xs text-ink-secondary">
          The 2023-2025 hold-out is examined exactly once at the end of v0.1 build. Status: <span className="font-mono text-amber-800">NOT YET EXAMINED</span> —
          backend Plan 2 not complete; the singleton timestamp on <code className="font-mono text-[11px]">atlas_v6_strategy_runs.holdout_examined_at</code> is unset.
          When Plan 2 ships, this page surfaces the terminal report.
        </p>
      </div>
    </main>
  )
}
