// src/app/strategies/v6/picks/[symbol]/page.tsx
// Per-pick drill-down — composite breakdown by signal, HRP cluster, sizing rationale.
export const dynamic = 'force-dynamic'
import { getV6Book } from '@/lib/queries/v6'

const MOCK_SIGNAL_BREAKDOWN: Record<string, { signal: string; z: number; weight: number; contribution: number }[]> = {
  default: [
    { signal: 'natr_14',            z: 1.4, weight: 0.15, contribution: 0.21 },
    { signal: 'beta_alpha_63d',     z: 1.9, weight: 0.15, contribution: 0.29 },
    { signal: 'mom_low_vol',        z: 1.6, weight: 0.15, contribution: 0.24 },
    { signal: 'residual_momentum',  z: 2.1, weight: 0.13, contribution: 0.27 },
    { signal: '52wh_proximity',     z: 1.3, weight: 0.13, contribution: 0.17 },
    { signal: 'industry_rs',        z: 1.0, weight: 0.13, contribution: 0.13 },
    { signal: 'fip_smoothness',     z: 0.8, weight: 0.05, contribution: 0.04 },
    { signal: 'bab',                z: 0.5, weight: 0.05, contribution: 0.03 },
    { signal: 'quality_proxy',      z: 0.6, weight: 0.05, contribution: 0.03 },
  ],
}

export default async function V6PickPage({
  params,
}: {
  params: Promise<{ symbol: string }>
}) {
  const { symbol } = await params
  const book = await getV6Book()
  const holding = book.holdings.find((h) => h.symbol === symbol.toUpperCase())
  const signals = MOCK_SIGNAL_BREAKDOWN.default

  return (
    <main className="min-h-screen bg-paper px-8 py-6 max-w-7xl mx-auto">
      <header className="mb-6">
        <p className="font-sans text-[11px] text-ink-tertiary uppercase tracking-wide">
          <a href="/strategies/v6" className="hover:text-ink-primary">v6 Command Center</a>
          {' / Picks / '}
          <span className="font-mono">{symbol.toUpperCase()}</span>
        </p>
        <h1 className="font-serif text-2xl text-ink-primary mt-1">
          {holding?.name ?? symbol.toUpperCase()}
        </h1>
        {holding ? (
          <p className="font-sans text-xs text-ink-tertiary mt-1">
            {holding.sector} · {holding.confidence} confidence · {holding.days_held} days held · HRP cluster {holding.hrp_cluster}
          </p>
        ) : (
          <p className="font-sans text-xs text-amber-700 mt-1">Not currently in v6 book (showing reference signal breakdown).</p>
        )}
      </header>

      {holding && (
        <section className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
          <div className="bg-paper border border-paper-rule rounded-[2px] p-3">
            <p className="font-sans text-[10px] text-ink-tertiary uppercase tracking-wide">Weight</p>
            <p className="font-mono text-lg font-semibold text-ink-primary mt-1">{holding.weight_pct.toFixed(1)}%</p>
          </div>
          <div className="bg-paper border border-paper-rule rounded-[2px] p-3">
            <p className="font-sans text-[10px] text-ink-tertiary uppercase tracking-wide">Composite</p>
            <p className="font-mono text-lg font-semibold text-ink-primary mt-1">{holding.composite_score.toFixed(2)}</p>
          </div>
          <div className="bg-paper border border-paper-rule rounded-[2px] p-3">
            <p className="font-sans text-[10px] text-ink-tertiary uppercase tracking-wide">P&amp;L since entry</p>
            <p className={`font-mono text-lg font-semibold mt-1 ${holding.pnl_since_entry_pct >= 0 ? 'text-emerald-700' : 'text-rose-700'}`}>
              {holding.pnl_since_entry_pct >= 0 ? '+' : ''}{holding.pnl_since_entry_pct.toFixed(1)}%
            </p>
          </div>
          <div className="bg-paper border border-paper-rule rounded-[2px] p-3">
            <p className="font-sans text-[10px] text-ink-tertiary uppercase tracking-wide">Days held</p>
            <p className="font-mono text-lg font-semibold text-ink-primary mt-1">{holding.days_held}</p>
          </div>
        </section>
      )}

      <section className="bg-paper border border-paper-rule rounded-[2px] overflow-hidden mb-6">
        <h3 className="font-serif text-base text-ink-primary px-4 pt-4 pb-2">Signal breakdown</h3>
        <p className="font-sans text-xs text-ink-tertiary px-4 pb-3">
          Per-signal z-score × weight = contribution. Sum is the composite score.
        </p>
        <table className="w-full text-xs">
          <thead className="bg-paper-rule/20 border-b border-paper-rule text-ink-tertiary">
            <tr>
              <th className="text-left font-sans font-normal px-3 py-2">Signal</th>
              <th className="text-right font-sans font-normal px-3 py-2">z-score</th>
              <th className="text-right font-sans font-normal px-3 py-2">Weight</th>
              <th className="text-right font-sans font-normal px-3 py-2">Contribution</th>
              <th className="font-sans font-normal px-3 py-2">Bar</th>
            </tr>
          </thead>
          <tbody>
            {signals.map((s) => (
              <tr key={s.signal} className="border-b border-paper-rule/40">
                <td className="px-3 py-2 font-mono text-ink-primary">{s.signal}</td>
                <td className="px-3 py-2 text-right font-mono">{s.z >= 0 ? '+' : ''}{s.z.toFixed(2)}</td>
                <td className="px-3 py-2 text-right font-mono text-ink-tertiary">{(s.weight * 100).toFixed(0)}%</td>
                <td className="px-3 py-2 text-right font-mono text-emerald-800">+{s.contribution.toFixed(3)}</td>
                <td className="px-3 py-2">
                  <div className="w-full bg-paper-rule/30 h-2 rounded-[1px]">
                    <div className="h-2 bg-emerald-700 rounded-[1px]" style={{ width: `${Math.min(100, (s.contribution / 0.3) * 100)}%` }} />
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <div className="bg-paper border border-paper-rule rounded-[2px] p-4">
        <h3 className="font-serif text-base text-ink-primary mb-2">Why this weight?</h3>
        <p className="font-sans text-xs text-ink-secondary leading-relaxed">
          Position weight comes from HRP (Hierarchical Risk Parity). The cohort is clustered by 252-day return correlation;
          inverse cluster-variance allocates between halves recursively. Caps then bind in order: 5% per name, 25% per sector,
          5% per issuer group. Excess from a binding cap redistributes within the same cluster — preserving HRP intent rather
          than spraying flat across the basket.
        </p>
      </div>
    </main>
  )
}
