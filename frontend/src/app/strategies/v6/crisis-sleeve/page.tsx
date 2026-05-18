// src/app/strategies/v6/crisis-sleeve/page.tsx
// Crisis sleeve dashboard — gold + G-Sec TSMOM allocations.
export const dynamic = 'force-dynamic'
import { getV6Book } from '@/lib/queries/v6'

export default async function V6CrisisSleevePage() {
  const book = await getV6Book()
  return (
    <main className="min-h-screen bg-paper px-8 py-6 max-w-7xl mx-auto">
      <header className="mb-6">
        <p className="font-sans text-[11px] text-ink-tertiary uppercase tracking-wide">
          <a href="/strategies/v6" className="hover:text-ink-primary">v6 Command Center</a>
          {' / Crisis Sleeve'}
        </p>
        <h1 className="font-serif text-2xl text-ink-primary mt-1">Crisis Sleeve</h1>
        <p className="font-sans text-xs text-ink-tertiary mt-1">
          Cross-asset TSMOM on gold ETF + G-Sec ETF. Sized by macro regime: 5% (calm) → 15% (crash).
        </p>
      </header>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mb-6">
        <div className="bg-paper border border-paper-rule rounded-[2px] p-3">
          <p className="font-sans text-[10px] text-ink-tertiary uppercase tracking-wide">Sleeve %</p>
          <p className="font-mono text-lg font-semibold text-ink-primary mt-1">{book.crisis_sleeve.total_pct.toFixed(1)}%</p>
        </div>
        <div className="bg-paper border border-paper-rule rounded-[2px] p-3">
          <p className="font-sans text-[10px] text-ink-tertiary uppercase tracking-wide">Regime score</p>
          <p className="font-mono text-lg font-semibold text-ink-primary mt-1">{book.regime.score}/5 · {book.regime.level}</p>
        </div>
        <div className="bg-paper border border-paper-rule rounded-[2px] p-3">
          <p className="font-sans text-[10px] text-ink-tertiary uppercase tracking-wide">Gross multiplier</p>
          <p className="font-mono text-lg font-semibold text-ink-primary mt-1">{book.regime.gross_multiplier.toFixed(2)}×</p>
        </div>
      </div>

      <div className="bg-paper border border-paper-rule rounded-[2px] overflow-hidden mb-6">
        <table className="w-full text-xs">
          <thead className="bg-paper-rule/20 border-b border-paper-rule text-ink-tertiary">
            <tr>
              <th className="text-left font-sans font-normal px-3 py-2">Symbol</th>
              <th className="text-left font-sans font-normal px-3 py-2">Name</th>
              <th className="text-right font-sans font-normal px-3 py-2">Weight in book</th>
              <th className="text-right font-sans font-normal px-3 py-2">12m TSMOM signal</th>
            </tr>
          </thead>
          <tbody>
            {book.crisis_sleeve.legs.map((l) => (
              <tr key={l.symbol} className="border-b border-paper-rule/40">
                <td className="px-3 py-2 font-mono text-ink-primary">{l.symbol}</td>
                <td className="px-3 py-2 font-sans text-ink-secondary">{l.name}</td>
                <td className="px-3 py-2 text-right font-mono">{l.weight_pct.toFixed(1)}%</td>
                <td className={`px-3 py-2 text-right font-mono ${l.tsmom_12m_return_pct > 0 ? 'text-emerald-700' : 'text-rose-700'}`}>
                  {l.tsmom_12m_return_pct > 0 ? '+' : ''}{l.tsmom_12m_return_pct.toFixed(1)}%
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="bg-paper border border-paper-rule rounded-[2px] p-4">
        <h3 className="font-serif text-base text-ink-primary mb-2">Why a sleeve?</h3>
        <p className="font-sans text-xs text-ink-secondary leading-relaxed">
          In bearish regimes the equity book cuts gross to 20-55%. The crisis sleeve scales up to 15% in cash-equivalent assets
          whose own 12m time-series momentum is positive. This converts &ldquo;less bad&rdquo; (cash sit-out) into &ldquo;positive
          crisis P&amp;L&rdquo; (gold + G-Sec rallies through equity drawdowns). SG Trend Index reference: +27% in 2022; +20%+ in 2008.
          v0.1 ships with two legs (gold ETF, G-Sec ETF). v0.2 adds USDINR + Nifty futures short for full multi-asset coverage.
        </p>
      </div>
    </main>
  )
}
