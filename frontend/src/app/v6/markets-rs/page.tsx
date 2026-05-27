// frontend/src/app/v6/markets-rs/page.tsx
//
// Page 03 Markets RS — 9 baselines × 5 windows grid + 4 hero readouts.
// Reads from atlas.mv_markets_rs_grid via getMarketsRsPage().
//
// Data refresh: nightly pg_cron at 20:05 IST.

import { getMarketsRsPage } from '@/lib/queries/v6/markets-rs'

export const dynamic = 'force-dynamic'
export const revalidate = 0

function fmtPct(v: number | null, digits = 1): string {
  if (v == null) return '—'
  const pct = v * 100
  const sign = pct > 0 ? '+' : ''
  return `${sign}${pct.toFixed(digits)}%`
}

function fmtRank(r: number | null): string {
  if (r == null) return '—'
  return `${r} / 9`
}

function cellTint(ret: number | null): string {
  if (ret == null) return 'text-ink-tertiary'
  if (ret >= 0.05) return 'text-signal-pos font-medium'
  if (ret > 0)     return 'text-signal-pos'
  if (ret > -0.05) return 'text-signal-neg'
  return 'text-signal-neg font-medium'
}

export default async function MarketsRsPage() {
  const data = await getMarketsRsPage()
  const { baselines, hero, as_of_date } = data

  return (
    <main className="container mx-auto px-8 py-12 max-w-7xl">
      {/* Header */}
      <header className="mb-12 pb-8 border-b border-paper-rule">
        <div className="text-[11px] uppercase tracking-widest text-ink-tertiary font-semibold mb-3">
          Cross-market relative strength
        </div>
        <h1 className="font-serif text-5xl leading-tight text-ink mb-3">
          Where is money working today?
        </h1>
        <p className="text-base text-ink-secondary max-w-3xl">
          Nine baselines across India, cross-market, and commodities — ranked across five time windows.
          All returns in INR (foreign baselines USD-converted at RBI reference rate).
        </p>
        {as_of_date && (
          <div className="text-xs font-mono text-ink-tertiary mt-3">
            As of {as_of_date} · refreshed nightly 20:00 IST
          </div>
        )}
      </header>

      {/* Hero readouts — 4 cards */}
      <section className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-12">
        <div className="border border-paper-rule bg-paper-soft p-5 rounded-sm">
          <div className="text-[10px] uppercase tracking-widest text-ink-tertiary font-semibold mb-2">
            Today&apos;s leadership
          </div>
          <div className="font-serif text-xl text-ink leading-tight">
            {hero.today_leader ?? '—'}
          </div>
          <div className="text-xs text-ink-tertiary mt-2">
            Top performer this week
          </div>
        </div>
        <div className="border border-paper-rule bg-paper-soft p-5 rounded-sm">
          <div className="text-[10px] uppercase tracking-widest text-ink-tertiary font-semibold mb-2">
            India vs world
          </div>
          <div className="font-mono text-2xl text-ink leading-tight">
            {hero.india_rank_1m != null ? `${hero.india_rank_1m} / 9` : '—'}
          </div>
          <div className="text-xs text-ink-tertiary mt-2">
            Nifty 500 rank on 1-month
          </div>
        </div>
        <div className="border border-paper-rule bg-paper-soft p-5 rounded-sm">
          <div className="text-[10px] uppercase tracking-widest text-ink-tertiary font-semibold mb-2">
            Within India
          </div>
          <div className={`font-mono text-2xl leading-tight ${
            hero.large_vs_midsmall_spread_3m != null && hero.large_vs_midsmall_spread_3m > 0
              ? 'text-signal-pos' : 'text-signal-neg'
          }`}>
            {hero.large_vs_midsmall_spread_3m != null
              ? `${hero.large_vs_midsmall_spread_3m > 0 ? '+' : ''}${hero.large_vs_midsmall_spread_3m.toFixed(1)}pp`
              : '—'}
          </div>
          <div className="text-xs text-ink-tertiary mt-2">
            Large vs mid+small (3M spread)
          </div>
        </div>
        <div className="border border-paper-rule bg-paper-soft p-5 rounded-sm">
          <div className="text-[10px] uppercase tracking-widest text-ink-tertiary font-semibold mb-2">
            India RS grade
          </div>
          <div className="font-serif text-4xl text-ink leading-none">
            {hero.india_rs_grade ?? '—'}
          </div>
          <div className="text-xs text-ink-tertiary mt-2">
            Nifty 500 vs all 9 baselines
          </div>
        </div>
      </section>

      {/* 9 × 5 RS grid */}
      <section className="mb-12">
        <h2 className="font-serif text-2xl text-ink mb-4">RS grid · 9 baselines × 5 windows</h2>
        <div className="border border-paper-rule rounded-sm overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-paper-deep border-b border-paper-rule">
              <tr className="text-[10px] uppercase tracking-wider text-ink-tertiary font-semibold">
                <th className="px-4 py-3 text-left">Baseline</th>
                <th className="px-4 py-3 text-right">1W</th>
                <th className="px-4 py-3 text-right">1M</th>
                <th className="px-4 py-3 text-right">3M</th>
                <th className="px-4 py-3 text-right">6M</th>
                <th className="px-4 py-3 text-right">12M</th>
              </tr>
            </thead>
            <tbody>
              {baselines.map(b => (
                <tr key={b.baseline_name} className="border-t border-paper-rule hover:bg-paper-soft transition-colors">
                  <td className="px-4 py-3 font-medium text-ink">{b.baseline_name}</td>
                  <td className={`px-4 py-3 text-right font-mono ${cellTint(b.ret_1w)}`}>
                    {fmtPct(b.ret_1w)}
                    <span className="text-[9px] text-ink-tertiary ml-2 font-sans">{fmtRank(b.rank_1w)}</span>
                  </td>
                  <td className={`px-4 py-3 text-right font-mono ${cellTint(b.ret_1m)}`}>
                    {fmtPct(b.ret_1m)}
                    <span className="text-[9px] text-ink-tertiary ml-2 font-sans">{fmtRank(b.rank_1m)}</span>
                  </td>
                  <td className={`px-4 py-3 text-right font-mono ${cellTint(b.ret_3m)}`}>
                    {fmtPct(b.ret_3m)}
                    <span className="text-[9px] text-ink-tertiary ml-2 font-sans">{fmtRank(b.rank_3m)}</span>
                  </td>
                  <td className={`px-4 py-3 text-right font-mono ${cellTint(b.ret_6m)}`}>
                    {fmtPct(b.ret_6m)}
                    <span className="text-[9px] text-ink-tertiary ml-2 font-sans">{fmtRank(b.rank_6m)}</span>
                  </td>
                  <td className={`px-4 py-3 text-right font-mono ${cellTint(b.ret_12m)}`}>
                    {fmtPct(b.ret_12m)}
                    <span className="text-[9px] text-ink-tertiary ml-2 font-sans">{fmtRank(b.rank_12m)}</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {/* Footnote */}
      <footer className="text-xs text-ink-tertiary leading-relaxed border-t border-paper-rule pt-6">
        All returns are total return in INR. Foreign baselines USD-converted at the prevailing RBI reference rate.
        Gold is GOLDBEES (₹/g, Mumbai), not the international USD spot. MSCI EM is proxied by VWO (USD-denominated, FX-adjusted).
      </footer>
    </main>
  )
}
