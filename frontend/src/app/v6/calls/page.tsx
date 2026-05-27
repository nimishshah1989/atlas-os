// frontend/src/app/v6/calls/page.tsx
//
// Page 08 Calls Performance — all signal calls (in-flight + closed) from
// atlas.mv_calls_performance with summary hit rate, average realized
// excess, and a single sortable table. Backtest evidence is "real call /
// real subsequent return" — predicted_excess at entry vs realized excess
// today.
//
// Refresh: nightly pg_cron at 20:05 IST.

import Link from 'next/link'
import { getCallsPerformancePage } from '@/lib/queries/v6/calls-performance'

export const dynamic = 'force-dynamic'
export const revalidate = 0

function fmtPctRaw(v: number | null, digits = 1): string {
  if (v == null) return '—'
  const sign = v > 0 ? '+' : ''
  return `${sign}${v.toFixed(digits)}%`
}

function actionTint(action: string | null): string {
  if (action === 'POSITIVE') return 'text-signal-pos'
  if (action === 'NEGATIVE') return 'text-signal-neg'
  return 'text-ink-secondary'
}

function hitTint(is_hit: boolean): string {
  return is_hit ? 'text-signal-pos' : 'text-signal-neg'
}

export default async function CallsPerformancePage() {
  const { calls, summary } = await getCallsPerformancePage()

  return (
    <main className="container mx-auto px-8 py-12 max-w-[1400px]">
      <header className="mb-10 pb-8 border-b border-paper-rule">
        <div className="text-[11px] uppercase tracking-widest text-ink-tertiary font-semibold mb-3">
          Calls performance · {summary.total.toLocaleString()} calls
        </div>
        <h1 className="font-serif text-5xl leading-tight text-ink mb-3">
          What did the calls actually do?
        </h1>
        <p className="text-base text-ink-secondary max-w-3xl">
          Every signal call ever fired by the 24-cell discovery matrix, with predicted excess at
          entry and realized excess against the benchmark since.
        </p>
      </header>

      {/* Summary tiles */}
      <section className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-10">
        <div className="border border-paper-rule bg-paper-soft p-5 rounded-sm">
          <div className="text-[10px] uppercase tracking-widest text-ink-tertiary font-semibold mb-2">Total calls</div>
          <div className="font-mono text-3xl text-ink">{summary.total.toLocaleString()}</div>
        </div>
        <div className="border border-paper-rule bg-paper-soft p-5 rounded-sm">
          <div className="text-[10px] uppercase tracking-widest text-ink-tertiary font-semibold mb-2">Hit rate</div>
          <div className="font-mono text-3xl text-ink">
            {summary.hit_rate != null ? `${(summary.hit_rate * 100).toFixed(0)}%` : '—'}
          </div>
          <div className="text-xs text-ink-tertiary mt-1">
            {summary.hits.toLocaleString()} of {summary.total.toLocaleString()}
          </div>
        </div>
        <div className="border border-paper-rule bg-paper-soft p-5 rounded-sm">
          <div className="text-[10px] uppercase tracking-widest text-ink-tertiary font-semibold mb-2">Avg realized excess</div>
          <div className={`font-mono text-3xl ${
            summary.avg_realized_excess_pct == null ? 'text-ink-tertiary'
              : summary.avg_realized_excess_pct > 0 ? 'text-signal-pos' : 'text-signal-neg'
          }`}>
            {fmtPctRaw(summary.avg_realized_excess_pct)}
          </div>
          <div className="text-xs text-ink-tertiary mt-1">vs benchmark since entry</div>
        </div>
        <div className="border border-paper-rule bg-paper-soft p-5 rounded-sm">
          <div className="text-[10px] uppercase tracking-widest text-ink-tertiary font-semibold mb-2">By status</div>
          <div className="text-xs text-ink space-y-1 mt-1">
            {Object.entries(summary.by_status).map(([s, n]) => (
              <div key={s} className="flex justify-between">
                <span className="text-ink-secondary">{s}</span>
                <span className="font-mono">{n.toLocaleString()}</span>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Calls table */}
      <section className="border border-paper-rule rounded-sm overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-paper-deep border-b border-paper-rule">
              <tr className="text-[10px] uppercase tracking-wider text-ink-tertiary font-semibold">
                <th className="px-3 py-3 text-left">Entry</th>
                <th className="px-3 py-3 text-left">Symbol</th>
                <th className="px-3 py-3 text-left">Cell</th>
                <th className="px-3 py-3 text-left">Action</th>
                <th className="px-3 py-3 text-right">Conf</th>
                <th className="px-3 py-3 text-right">Predicted</th>
                <th className="px-3 py-3 text-right">Stock</th>
                <th className="px-3 py-3 text-right">Bench</th>
                <th className="px-3 py-3 text-right">Excess</th>
                <th className="px-3 py-3 text-right">Days</th>
                <th className="px-3 py-3 text-center">Hit</th>
                <th className="px-3 py-3 text-left">Status</th>
              </tr>
            </thead>
            <tbody>
              {calls.map(c => (
                <tr key={c.signal_call_id} className="border-t border-paper-rule hover:bg-paper-soft transition-colors">
                  <td className="px-3 py-2 font-mono text-xs text-ink-tertiary">{c.entry_date ?? '—'}</td>
                  <td className="px-3 py-2 font-mono text-ink">
                    <Link href={`/v6/stocks/${c.symbol}`} className="hover:underline">
                      {c.symbol}
                    </Link>
                  </td>
                  <td className="px-3 py-2 text-xs text-ink-secondary">{c.cell_name ?? '—'}</td>
                  <td className={`px-3 py-2 text-[10px] uppercase tracking-wider font-semibold ${actionTint(c.action)}`}>
                    {c.action === 'POSITIVE' ? 'BUY' : c.action === 'NEGATIVE' ? 'AVOID' : 'WATCH'}
                  </td>
                  <td className="px-3 py-2 text-right font-mono text-xs text-ink">
                    {c.confidence_unconditional != null ? c.confidence_unconditional.toFixed(2) : '—'}
                  </td>
                  <td className="px-3 py-2 text-right font-mono text-xs text-ink-secondary">
                    {c.predicted_excess != null ? `${(c.predicted_excess * 100).toFixed(1)}%` : '—'}
                  </td>
                  <td className="px-3 py-2 text-right font-mono text-xs">{fmtPctRaw(c.stock_ret_pct)}</td>
                  <td className="px-3 py-2 text-right font-mono text-xs">{fmtPctRaw(c.bench_ret_pct)}</td>
                  <td className={`px-3 py-2 text-right font-mono text-xs ${
                    c.realized_excess_pct == null ? 'text-ink-tertiary'
                      : c.realized_excess_pct > 0 ? 'text-signal-pos' : 'text-signal-neg'
                  }`}>
                    {fmtPctRaw(c.realized_excess_pct)}
                  </td>
                  <td className="px-3 py-2 text-right font-mono text-xs text-ink-tertiary">{c.days_in_position}</td>
                  <td className={`px-3 py-2 text-center font-mono text-xs ${hitTint(c.is_hit)}`}>
                    {c.is_hit ? '✓' : '·'}
                  </td>
                  <td className="px-3 py-2 text-[10px] uppercase tracking-wider text-ink-tertiary">{c.status}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <footer className="text-xs text-ink-tertiary leading-relaxed border-t border-paper-rule pt-6 mt-6">
        A call is &quot;hit&quot; when realized excess for BUY (or negative realized excess for AVOID) clears
        the cell's threshold. Excess return is stock_ret − bench_ret since entry. In-flight calls
        will continue to update until the tenure window closes.
      </footer>
    </main>
  )
}
