// frontend/src/app/v6/regime/page.tsx
//
// Page 01 Market Regime landing — single wide MV row from
// atlas.mv_market_regime_landing. Composes:
//   - hero strip (regime state + days + deployment + LIQUIDBEES yield)
//   - 12-week journey table
//   - 4 pulse tiles (next-state probs)
//   - 6 cells-favored cards (sub-component)
//   - 3-section conviction list (stocks/funds/ETFs, sub-components)
//
// Refresh: nightly pg_cron at 20:05 IST.

import { getMarketRegimePage } from '@/lib/queries/v6/market-regime'
import {
  CellFavoredCard,
  ConvictionStocksColumn,
  ConvictionFundsColumn,
  ConvictionEtfsColumn,
} from './_components'

export const dynamic = 'force-dynamic'
export const revalidate = 0

function fmtPct(v: number | null, digits = 1): string {
  if (v == null) return '—'
  return `${(v * 100).toFixed(digits)}%`
}

function fmtNum(v: number | null, digits = 2): string {
  if (v == null) return '—'
  return v.toFixed(digits)
}

export default async function MarketRegimePage() {
  const data = await getMarketRegimePage()

  if (!data) {
    return (
      <main className="container mx-auto px-8 py-12 max-w-7xl">
        <header className="mb-12 pb-8 border-b border-paper-rule">
          <h1 className="font-serif text-5xl leading-tight text-ink mb-3">
            Market regime is loading
          </h1>
          <p className="text-base text-ink-secondary">
            The materialized view is being refreshed. Check back shortly.
          </p>
        </header>
      </main>
    )
  }

  const {
    as_of_date, regime_state, deployment_multiplier, days_in_regime,
    entered_date, prior_regime_state, typical_length_days,
    liquid_bees_yield_pct, next_state_probs, twelve_week_journey,
    cells_favored, conviction_stocks, conviction_funds, conviction_etfs,
  } = data

  const topNextStates = Object.entries(next_state_probs)
    .map(([state, prob]) => ({ state, prob: Number(prob) || 0 }))
    .sort((a, b) => b.prob - a.prob)
    .slice(0, 4)

  return (
    <main className="container mx-auto px-8 py-12 max-w-7xl">
      <header className="mb-12 pb-8 border-b border-paper-rule">
        <div className="text-[11px] uppercase tracking-widest text-ink-tertiary font-semibold mb-3">
          Market regime — discovery-first equity intelligence
        </div>
        <h1 className="font-serif text-5xl leading-tight text-ink mb-3">
          The market is <span className="italic">{regime_state}</span>
        </h1>
        <p className="text-base text-ink-secondary max-w-3xl">
          {days_in_regime} {days_in_regime === 1 ? 'day' : 'days'} in this regime
          {prior_regime_state && (<>, previously {prior_regime_state}</>)}
          {typical_length_days && (<>. Typical length: {typical_length_days} days.</>)}
        </p>
        {as_of_date && (
          <div className="text-xs font-mono text-ink-tertiary mt-3">
            As of {as_of_date} · refreshed nightly 20:05 IST
          </div>
        )}
      </header>

      <section className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-12">
        <div className="border border-paper-rule bg-paper-soft p-5 rounded-sm">
          <div className="text-[10px] uppercase tracking-widest text-ink-tertiary font-semibold mb-2">Regime state</div>
          <div className="font-serif text-2xl text-ink leading-tight">{regime_state}</div>
          <div className="text-xs text-ink-tertiary mt-2">{entered_date ? `Entered ${entered_date}` : '—'}</div>
        </div>
        <div className="border border-paper-rule bg-paper-soft p-5 rounded-sm">
          <div className="text-[10px] uppercase tracking-widest text-ink-tertiary font-semibold mb-2">Deployment</div>
          <div className="font-mono text-3xl text-ink leading-tight">
            {deployment_multiplier != null ? `${(deployment_multiplier * 100).toFixed(0)}%` : '—'}
          </div>
          <div className="text-xs text-ink-tertiary mt-2">Suggested book gross</div>
        </div>
        <div className="border border-paper-rule bg-paper-soft p-5 rounded-sm">
          <div className="text-[10px] uppercase tracking-widest text-ink-tertiary font-semibold mb-2">Days in regime</div>
          <div className="font-mono text-3xl text-ink leading-tight">{days_in_regime}</div>
          <div className="text-xs text-ink-tertiary mt-2">Streak since transition</div>
        </div>
        <div className="border border-paper-rule bg-paper-soft p-5 rounded-sm">
          <div className="text-[10px] uppercase tracking-widest text-ink-tertiary font-semibold mb-2">LIQUIDBEES yield</div>
          <div className="font-mono text-3xl text-ink leading-tight">
            {liquid_bees_yield_pct != null ? `${liquid_bees_yield_pct.toFixed(2)}%` : '—'}
          </div>
          <div className="text-xs text-ink-tertiary mt-2">Idle cash overnight rate</div>
        </div>
      </section>

      {twelve_week_journey.length > 0 && (
        <section className="mb-12">
          <h2 className="font-serif text-2xl text-ink mb-4">12-week journey</h2>
          <div className="border border-paper-rule rounded-sm overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-paper-deep border-b border-paper-rule">
                <tr className="text-[10px] uppercase tracking-wider text-ink-tertiary font-semibold">
                  <th className="px-4 py-3 text-left">Week start</th>
                  <th className="px-4 py-3 text-left">Regime</th>
                  <th className="px-4 py-3 text-right">Breadth %</th>
                  <th className="px-4 py-3 text-right">India VIX</th>
                </tr>
              </thead>
              <tbody>
                {twelve_week_journey.map((w, i) => (
                  <tr key={`${w.week_start}-${i}`} className="border-t border-paper-rule hover:bg-paper-soft transition-colors">
                    <td className="px-4 py-3 font-mono text-ink">{w.week_start}</td>
                    <td className="px-4 py-3 text-ink">{w.regime_state}</td>
                    <td className="px-4 py-3 text-right font-mono text-ink">{fmtPct(w.breadth_pct)}</td>
                    <td className="px-4 py-3 text-right font-mono text-ink">{fmtNum(w.india_vix, 1)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {topNextStates.length > 0 && (
        <section className="mb-12">
          <h2 className="font-serif text-2xl text-ink mb-4">Next-state probabilities</h2>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {topNextStates.map(({ state, prob }) => (
              <div key={state} className="border border-paper-rule bg-paper-soft p-5 rounded-sm">
                <div className="text-[10px] uppercase tracking-widest text-ink-tertiary font-semibold mb-2">{state}</div>
                <div className="font-mono text-3xl text-ink leading-tight">{prob}%</div>
              </div>
            ))}
          </div>
        </section>
      )}

      {cells_favored.length > 0 && (
        <section className="mb-12">
          <h2 className="font-serif text-2xl text-ink mb-4">Cells favored today</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {cells_favored.slice(0, 6).map(c => (
              <CellFavoredCard key={c.cell_id} cell={c} />
            ))}
          </div>
        </section>
      )}

      <section className="mb-12 grid grid-cols-1 lg:grid-cols-3 gap-8">
        <ConvictionStocksColumn rows={conviction_stocks} />
        <ConvictionFundsColumn rows={conviction_funds} />
        <ConvictionEtfsColumn rows={conviction_etfs} />
      </section>

      <footer className="text-xs text-ink-tertiary leading-relaxed border-t border-paper-rule pt-6">
        Cells-favored derived from the 24-cell discovery matrix. Conviction lists drawn from
        scorecard_daily where confidence ≥ MED. Deployment multiplier is methodology default,
        not a personalised allocation.
      </footer>
    </main>
  )
}
