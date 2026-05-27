// frontend/src/app/v6/stocks/page.tsx
//
// Page 05 Stock List — table of ~750 stocks from atlas.mv_stock_list_v6,
// ordered by confidence band then composite score. Filter chips on
// Nifty 50/100/500 + action are deferred for v6.0 (CSS-only chips need
// client state). Static table with composite, action, tape strip, returns.
//
// Refresh: nightly pg_cron at 20:05 IST.

import Link from 'next/link'
import { getStockListPage } from '@/lib/queries/v6/stock-list'

export const dynamic = 'force-dynamic'
export const revalidate = 0

function fmtPct(v: number | null, digits = 1): string {
  if (v == null) return '—'
  const pct = v * 100
  const sign = pct > 0 ? '+' : ''
  return `${sign}${pct.toFixed(digits)}%`
}

function fmtScore(v: number | null): string {
  if (v == null) return '—'
  const sign = v > 0 ? '+' : ''
  return `${sign}${v.toFixed(1)}`
}

function actionTint(action: string | null): string {
  if (action === 'POSITIVE') return 'text-signal-pos'
  if (action === 'NEGATIVE') return 'text-signal-neg'
  return 'text-ink-secondary'
}

function tapeDot(tape: string | null): string {
  if (tape === 'POS') return 'bg-signal-pos'
  if (tape === 'NEG') return 'bg-signal-neg'
  if (tape === 'NEU') return 'bg-ink-tertiary/40'
  return 'bg-paper-rule'
}

export default async function StockListPage() {
  const { rows, as_of_date } = await getStockListPage()

  return (
    <main className="container mx-auto px-8 py-12 max-w-[1400px]">
      <header className="mb-10 pb-8 border-b border-paper-rule">
        <div className="text-[11px] uppercase tracking-widest text-ink-tertiary font-semibold mb-3">
          Stock universe · {rows.length.toLocaleString()} listed
        </div>
        <h1 className="font-serif text-5xl leading-tight text-ink mb-3">
          Where conviction lives today
        </h1>
        <p className="text-base text-ink-secondary max-w-3xl">
          Ranked by confidence band, then composite score. HIGH band stocks have IC ≥ 0.05
          backing on the cell that fires; MED and LOW carry less statistical weight.
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
                <th className="px-3 py-3 text-left">Symbol</th>
                <th className="px-3 py-3 text-left">Sector</th>
                <th className="px-3 py-3 text-left">Tier</th>
                <th className="px-3 py-3 text-right">Composite</th>
                <th className="px-3 py-3 text-left">Conf</th>
                <th className="px-3 py-3 text-left">Action</th>
                <th className="px-3 py-3 text-left">Best cell</th>
                <th className="px-3 py-3 text-center">Tape</th>
                <th className="px-3 py-3 text-right">1M</th>
                <th className="px-3 py-3 text-right">3M</th>
                <th className="px-3 py-3 text-right">6M</th>
                <th className="px-3 py-3 text-right">12M</th>
                <th className="px-3 py-3 text-right">RS pctile</th>
              </tr>
            </thead>
            <tbody>
              {rows.map(r => (
                <tr key={r.instrument_id} className="border-t border-paper-rule hover:bg-paper-soft transition-colors">
                  <td className="px-3 py-2 font-mono text-ink">
                    <Link href={`/v6/stocks/${r.symbol}`} className="hover:underline">
                      {r.symbol}
                    </Link>
                  </td>
                  <td className="px-3 py-2 text-ink-secondary text-xs">{r.sector ?? '—'}</td>
                  <td className="px-3 py-2 text-ink-tertiary text-xs">{r.tier ?? '—'}</td>
                  <td className={`px-3 py-2 text-right font-mono ${actionTint(r.action)}`}>{fmtScore(r.composite_score)}</td>
                  <td className="px-3 py-2 text-[10px] uppercase tracking-wider font-semibold text-ink-tertiary">
                    {r.confidence_band ?? '—'}
                  </td>
                  <td className={`px-3 py-2 text-[10px] uppercase tracking-wider font-semibold ${actionTint(r.action)}`}>
                    {r.action === 'POSITIVE' ? 'BUY' : r.action === 'NEGATIVE' ? 'AVOID' : 'WATCH'}
                  </td>
                  <td className="px-3 py-2 text-ink-tertiary text-xs">{r.best_cell_name ?? '—'}</td>
                  <td className="px-3 py-2">
                    <div className="flex items-center justify-center gap-1">
                      <span className={`inline-block w-2 h-2 rounded-full ${tapeDot(r.tape_1m)}`} title={`1M ${r.tape_1m ?? '—'}`} />
                      <span className={`inline-block w-2 h-2 rounded-full ${tapeDot(r.tape_3m)}`} title={`3M ${r.tape_3m ?? '—'}`} />
                      <span className={`inline-block w-2 h-2 rounded-full ${tapeDot(r.tape_6m)}`} title={`6M ${r.tape_6m ?? '—'}`} />
                      <span className={`inline-block w-2 h-2 rounded-full ${tapeDot(r.tape_12m)}`} title={`12M ${r.tape_12m ?? '—'}`} />
                    </div>
                  </td>
                  <td className="px-3 py-2 text-right font-mono text-xs text-ink-secondary">{fmtPct(r.ret_1m)}</td>
                  <td className="px-3 py-2 text-right font-mono text-xs text-ink-secondary">{fmtPct(r.ret_3m)}</td>
                  <td className="px-3 py-2 text-right font-mono text-xs text-ink-secondary">{fmtPct(r.ret_6m)}</td>
                  <td className="px-3 py-2 text-right font-mono text-xs text-ink-secondary">{fmtPct(r.ret_12m)}</td>
                  <td className="px-3 py-2 text-right font-mono text-xs text-ink">
                    {r.rs_pctile_3m != null ? `${(r.rs_pctile_3m * 100).toFixed(0)}` : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <footer className="text-xs text-ink-tertiary leading-relaxed border-t border-paper-rule pt-6 mt-6">
        Composite = (conviction_score − 0.5) × 20 → [−10, +10]. Action label follows the
        underlying cell's directional bias. Tape dots show 1m/3m/6m/12m POS (green) / NEU (grey) / NEG (red).
        Click a symbol to see deep dive (deep-dive route is built in the next chunk).
      </footer>
    </main>
  )
}
