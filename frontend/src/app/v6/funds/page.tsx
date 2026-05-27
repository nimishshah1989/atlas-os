// frontend/src/app/v6/funds/page.tsx
//
// Page 06 Fund List — ~587 mutual fund schemes from atlas.mv_fund_list_v6,
// ordered by atlas-leader flag then composite. Renders a compact table with
// composite + 4 sub-pillars + quartile + recommendation. AMC stats panel
// deferred; the per-fund deep dive carries the holding-level detail.
//
// Refresh: nightly pg_cron at 20:05 IST.

import Link from 'next/link'
import { getFundListPage } from '@/lib/queries/v6/fund-list'

export const dynamic = 'force-dynamic'
export const revalidate = 0

function fmtScore(v: number | null): string {
  if (v == null) return '—'
  return v.toFixed(1)
}

function fmtPctRaw(v: number | null, digits = 2): string {
  if (v == null) return '—'
  return `${v.toFixed(digits)}%`
}

function recoTint(reco: string | null): string {
  if (reco === 'BUY') return 'text-signal-pos'
  if (reco === 'AVOID' || reco === 'SELL') return 'text-signal-neg'
  return 'text-ink-secondary'
}

export default async function FundListPage() {
  const { rows, as_of_date } = await getFundListPage()

  return (
    <main className="container mx-auto px-8 py-12 max-w-[1400px]">
      <header className="mb-10 pb-8 border-b border-paper-rule">
        <div className="text-[11px] uppercase tracking-widest text-ink-tertiary font-semibold mb-3">
          Mutual funds · {rows.length.toLocaleString()} schemes
        </div>
        <h1 className="font-serif text-5xl leading-tight text-ink mb-3">
          Which funds are doing real work?
        </h1>
        <p className="text-base text-ink-secondary max-w-3xl">
          Composite combines risk-adjusted return, holdings conviction, style/sector fit, and
          cost/manager efficiency. Atlas leaders are top-quartile on all four pillars.
        </p>
        {as_of_date && (
          <div className="text-xs font-mono text-ink-tertiary mt-3">
            As of {as_of_date} · refreshed nightly 20:05 IST
          </div>
        )}
      </header>

      <section className="border border-paper-rule rounded-sm overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-paper-deep border-b border-paper-rule">
              <tr className="text-[10px] uppercase tracking-wider text-ink-tertiary font-semibold">
                <th className="px-3 py-3 text-left">Fund</th>
                <th className="px-3 py-3 text-left">AMC</th>
                <th className="px-3 py-3 text-left">Category</th>
                <th className="px-3 py-3 text-right">AUM ₹Cr</th>
                <th className="px-3 py-3 text-right">Composite</th>
                <th className="px-3 py-3 text-right">RAR</th>
                <th className="px-3 py-3 text-right">Conv</th>
                <th className="px-3 py-3 text-right">Style</th>
                <th className="px-3 py-3 text-right">Cost</th>
                <th className="px-3 py-3 text-center">Quartile</th>
                <th className="px-3 py-3 text-center">Reco</th>
                <th className="px-3 py-3 text-right">Expense</th>
              </tr>
            </thead>
            <tbody>
              {rows.map(r => (
                <tr key={r.scheme_code} className="border-t border-paper-rule hover:bg-paper-soft transition-colors">
                  <td className="px-3 py-2">
                    <Link href={`/v6/funds/${r.scheme_code}`} className="text-ink hover:underline">
                      {r.fund_name}
                    </Link>
                    {r.is_atlas_leader && (
                      <span className="ml-2 text-[9px] uppercase tracking-wider text-signal-pos font-semibold">★ leader</span>
                    )}
                  </td>
                  <td className="px-3 py-2 text-xs text-ink-secondary">{r.amc}</td>
                  <td className="px-3 py-2 text-xs text-ink-tertiary">{r.fund_category ?? '—'}</td>
                  <td className="px-3 py-2 text-right font-mono text-xs text-ink-secondary">
                    {r.aum_cr != null ? r.aum_cr.toFixed(0) : '—'}
                  </td>
                  <td className="px-3 py-2 text-right font-mono text-ink">{fmtScore(r.composite_score)}</td>
                  <td className="px-3 py-2 text-right font-mono text-xs text-ink-secondary">{fmtScore(r.risk_adjusted_return_score)}</td>
                  <td className="px-3 py-2 text-right font-mono text-xs text-ink-secondary">{fmtScore(r.holdings_conviction_score)}</td>
                  <td className="px-3 py-2 text-right font-mono text-xs text-ink-secondary">{fmtScore(r.style_sector_score)}</td>
                  <td className="px-3 py-2 text-right font-mono text-xs text-ink-secondary">{fmtScore(r.cost_manager_score)}</td>
                  <td className="px-3 py-2 text-center font-mono text-xs text-ink">{r.peer_quartile ?? '—'}</td>
                  <td className={`px-3 py-2 text-center text-[10px] uppercase tracking-wider font-semibold ${recoTint(r.recommendation)}`}>
                    {r.recommendation ?? '—'}
                  </td>
                  <td className="px-3 py-2 text-right font-mono text-xs text-ink-tertiary">
                    {r.expense_ratio != null ? fmtPctRaw(r.expense_ratio * 100, 2) : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <footer className="text-xs text-ink-tertiary leading-relaxed border-t border-paper-rule pt-6 mt-6">
        Pillars are 0–100 scaled. RAR = risk-adjusted return; Conv = holdings conviction;
        Style = style/sector fit; Cost = cost/manager efficiency. Q1 is top quartile within
        the same category. Click a fund to see top-10 holdings and sub-metrics.
      </footer>
    </main>
  )
}
