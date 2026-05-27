// frontend/src/app/v6/funds/[scheme]/page.tsx
//
// Page 06a Fund Deep-Dive — one MV row from atlas.mv_fund_deepdive,
// keyed by scheme_code. Composes: hero (composite + 4 pillars) + ELI5 +
// top-10 holdings + sub-metrics + 12m NAV trail + 90d decisions.
//
// Refresh: nightly pg_cron at 20:05 IST.

import Link from 'next/link'
import { notFound } from 'next/navigation'
import { getFundDeepdive } from '@/lib/queries/v6/fund-deepdive'

export const dynamic = 'force-dynamic'
export const revalidate = 0

function fmtScore(v: number | null): string {
  if (v == null) return '—'
  return v.toFixed(1)
}

function fmtNum(v: number | null, digits = 2): string {
  if (v == null) return '—'
  return v.toFixed(digits)
}

function recoTint(reco: string | null): string {
  if (reco === 'BUY' || reco === 'Add') return 'text-signal-pos'
  if (reco === 'AVOID' || reco === 'SELL' || reco === 'Reduce') return 'text-signal-neg'
  return 'text-ink-secondary'
}

export default async function FundDeepdivePage({ params }: { params: Promise<{ scheme: string }> }) {
  const { scheme } = await params
  const d = await getFundDeepdive(scheme)
  if (!d) notFound()

  return (
    <main className="container mx-auto px-8 py-12 max-w-7xl">
      <Link href="/v6/funds" className="text-xs text-ink-tertiary hover:underline font-mono mb-6 inline-block">
        ← Back to funds
      </Link>

      <header className="mb-10 pb-6 border-b border-paper-rule">
        <div className="text-[11px] uppercase tracking-widest text-ink-tertiary font-semibold mb-2">
          {d.amc} · {d.fund_category ?? '—'} · {d.plan_type ?? '—'}
        </div>
        <h1 className="font-serif text-4xl leading-tight text-ink mb-2">{d.fund_name}</h1>
        <div className="text-sm text-ink-secondary">
          <span className="font-mono text-xs text-ink-tertiary">scheme {d.scheme_code}</span>
          {d.is_atlas_leader && (<span className="ml-3 text-signal-pos">★ atlas leader</span>)}
          {d.is_avoid && (<span className="ml-3 text-signal-neg">avoid</span>)}
        </div>
      </header>

      <section className="grid grid-cols-2 md:grid-cols-5 gap-4 mb-10">
        <div className="border border-paper-rule bg-paper-soft p-5 rounded-sm">
          <div className="text-[10px] uppercase tracking-widest text-ink-tertiary font-semibold mb-2">Composite</div>
          <div className="font-mono text-3xl text-ink">{fmtScore(d.composite_score)}</div>
          <div className="text-[10px] uppercase tracking-widest text-ink-tertiary mt-1">{d.peer_quartile ?? '—'}</div>
        </div>
        <div className="border border-paper-rule bg-paper-soft p-5 rounded-sm">
          <div className="text-[10px] uppercase tracking-widest text-ink-tertiary font-semibold mb-2">RAR</div>
          <div className="font-mono text-2xl text-ink">{fmtScore(d.risk_adjusted_return_score)}</div>
        </div>
        <div className="border border-paper-rule bg-paper-soft p-5 rounded-sm">
          <div className="text-[10px] uppercase tracking-widest text-ink-tertiary font-semibold mb-2">Conviction</div>
          <div className="font-mono text-2xl text-ink">{fmtScore(d.holdings_conviction_score)}</div>
        </div>
        <div className="border border-paper-rule bg-paper-soft p-5 rounded-sm">
          <div className="text-[10px] uppercase tracking-widest text-ink-tertiary font-semibold mb-2">Style</div>
          <div className="font-mono text-2xl text-ink">{fmtScore(d.style_sector_score)}</div>
        </div>
        <div className="border border-paper-rule bg-paper-soft p-5 rounded-sm">
          <div className="text-[10px] uppercase tracking-widest text-ink-tertiary font-semibold mb-2">Cost / Mgr</div>
          <div className="font-mono text-2xl text-ink">{fmtScore(d.cost_manager_score)}</div>
        </div>
      </section>

      {d.eli5 && (
        <section className="mb-10 border-l-2 border-paper-rule pl-4 italic text-base text-ink-secondary">
          {d.eli5}
        </section>
      )}

      <section className="mb-10 grid grid-cols-1 lg:grid-cols-2 gap-8">
        <div>
          <h2 className="font-serif text-xl text-ink mb-3">Top holdings</h2>
          {d.top_holdings.length === 0 ? (
            <p className="text-sm text-ink-tertiary">Holdings unjoinable for this fund.</p>
          ) : (
            <ul className="space-y-2">
              {d.top_holdings.slice(0, 10).map((h, i) => (
                <li key={`${h.symbol}-${i}`} className="flex items-baseline justify-between border-b border-paper-rule pb-2">
                  <span className="text-sm text-ink">{h.symbol}</span>
                  <span className="font-mono text-sm text-ink">{h.weight_pct.toFixed(2)}%</span>
                </li>
              ))}
            </ul>
          )}
          {d.holdings_as_of && (
            <div className="text-[11px] font-mono text-ink-tertiary mt-3">
              Holdings as of {d.holdings_as_of}
            </div>
          )}
        </div>
        <div>
          <h2 className="font-serif text-xl text-ink mb-3">Sub-metrics</h2>
          {d.sub_metrics ? (
            <dl className="text-sm space-y-2">
              <div className="flex justify-between border-b border-paper-rule pb-1">
                <dt className="text-ink-tertiary text-xs">Sharpe</dt>
                <dd className="font-mono text-xs text-ink">{fmtNum(d.sub_metrics.sharpe, 2)}</dd>
              </div>
              <div className="flex justify-between border-b border-paper-rule pb-1">
                <dt className="text-ink-tertiary text-xs">Sortino</dt>
                <dd className="font-mono text-xs text-ink">{fmtNum(d.sub_metrics.sortino, 2)}</dd>
              </div>
              <div className="flex justify-between border-b border-paper-rule pb-1">
                <dt className="text-ink-tertiary text-xs">Calmar</dt>
                <dd className="font-mono text-xs text-ink">{fmtNum(d.sub_metrics.calmar, 2)}</dd>
              </div>
              <div className="flex justify-between border-b border-paper-rule pb-1">
                <dt className="text-ink-tertiary text-xs">Max drawdown</dt>
                <dd className="font-mono text-xs text-signal-neg">
                  {d.sub_metrics.max_dd != null ? `-${(d.sub_metrics.max_dd * 100).toFixed(1)}%` : '—'}
                </dd>
              </div>
              <div className="flex justify-between border-b border-paper-rule pb-1">
                <dt className="text-ink-tertiary text-xs">Up / down capture</dt>
                <dd className="font-mono text-xs text-ink">
                  {fmtNum(d.sub_metrics.up_capture, 2)} / {fmtNum(d.sub_metrics.down_capture, 2)}
                </dd>
              </div>
              <div className="flex justify-between border-b border-paper-rule pb-1">
                <dt className="text-ink-tertiary text-xs">Fund age</dt>
                <dd className="font-mono text-xs text-ink">
                  {d.sub_metrics.fund_age_years != null ? `${d.sub_metrics.fund_age_years.toFixed(1)} yr` : '—'}
                </dd>
              </div>
              <div className="flex justify-between border-b border-paper-rule pb-1">
                <dt className="text-ink-tertiary text-xs">AUM ₹Cr</dt>
                <dd className="font-mono text-xs text-ink">{d.aum_cr != null ? d.aum_cr.toFixed(0) : '—'}</dd>
              </div>
              <div className="flex justify-between border-b border-paper-rule pb-1">
                <dt className="text-ink-tertiary text-xs">Expense ratio</dt>
                <dd className="font-mono text-xs text-ink">
                  {d.expense_ratio != null ? `${(d.expense_ratio * 100).toFixed(2)}%` : '—'}
                </dd>
              </div>
            </dl>
          ) : (
            <p className="text-sm text-ink-tertiary">Sub-metrics unavailable.</p>
          )}
        </div>
      </section>

      {d.nav_12m.length > 0 && (
        <section className="mb-10">
          <h2 className="font-serif text-xl text-ink mb-3">12-month NAV</h2>
          <div className="border border-paper-rule rounded-sm overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-paper-deep border-b border-paper-rule">
                <tr className="text-[10px] uppercase tracking-wider text-ink-tertiary font-semibold">
                  <th className="px-4 py-2 text-left">Month</th>
                  <th className="px-4 py-2 text-right">NAV</th>
                </tr>
              </thead>
              <tbody>
                {d.nav_12m.map((p, i) => (
                  <tr key={`${p.month}-${i}`} className="border-t border-paper-rule">
                    <td className="px-4 py-2 font-mono text-ink">{p.month}</td>
                    <td className="px-4 py-2 text-right font-mono text-ink">{p.nav.toFixed(4)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {d.recent_decisions_90d.length > 0 && (
        <section className="mb-10">
          <h2 className="font-serif text-xl text-ink mb-3">Recent decisions (90d)</h2>
          <ul className="space-y-2">
            {d.recent_decisions_90d.map((rd, i) => (
              <li key={`${rd.date}-${i}`} className="flex items-baseline justify-between border-b border-paper-rule pb-2">
                <span className="font-mono text-xs text-ink-tertiary">{rd.date}</span>
                <span className={`text-sm font-semibold ${recoTint(rd.recommendation)}`}>
                  {rd.recommendation}
                </span>
                <span className="text-xs text-ink-tertiary">
                  {rd.is_investable ? 'investable' : 'not investable'}
                </span>
              </li>
            ))}
          </ul>
        </section>
      )}

      <footer className="text-xs text-ink-tertiary leading-relaxed border-t border-paper-rule pt-6">
        Pillars (0–100): Risk-Adjusted Return, Holdings Conviction, Style/Sector fit, Cost/Manager.
        Atlas leaders are top-quartile on all four pillars. Holdings join uses stock universe;
        when unjoinable we still compute return-based pillars but suppress conviction.
      </footer>
    </main>
  )
}
