// frontend/src/app/v6/stocks/[symbol]/page.tsx
//
// Page 05a Stock Deep-Dive — one MV row from atlas.mv_stock_deepdive,
// keyed by symbol. Composes: hero (composite + action + state) +
// open signal calls + technicals snapshot + 30d trajectory + family + gates.
//
// Refresh: nightly pg_cron at 20:05 IST.

import Link from 'next/link'
import { notFound } from 'next/navigation'
import { getStockDeepdive } from '@/lib/queries/v6/stock-deepdive'

export const dynamic = 'force-dynamic'
export const revalidate = 0

function fmtPct(v: number | null, digits = 1): string {
  if (v == null) return '—'
  const pct = v * 100
  const sign = pct > 0 ? '+' : ''
  return `${sign}${pct.toFixed(digits)}%`
}

function fmtNum(v: number | null, digits = 2): string {
  if (v == null) return '—'
  return v.toFixed(digits)
}

function actionTint(action: string | null): string {
  if (action === 'POSITIVE') return 'text-signal-pos'
  if (action === 'NEGATIVE') return 'text-signal-neg'
  return 'text-ink-secondary'
}

function tapeTint(state: string | null): string {
  if (state === 'POSITIVE') return 'text-signal-pos'
  if (state === 'NEGATIVE') return 'text-signal-neg'
  return 'text-ink-tertiary'
}

export default async function StockDeepdivePage({ params }: { params: Promise<{ symbol: string }> }) {
  const { symbol } = await params
  // Indian symbols like M&M, J&KBANK come URL-encoded in the path segment.
  const d = await getStockDeepdive(decodeURIComponent(symbol).toUpperCase())
  if (!d) notFound()

  const tape = d.conviction_tape as { '1m'?: string | null; '3m'?: string | null; '6m'?: string | null; '12m'?: string | null }

  return (
    <main className="container mx-auto px-8 py-12 max-w-7xl">
      <Link href="/v6/stocks" className="text-xs text-ink-tertiary hover:underline font-mono mb-6 inline-block">
        ← Back to stocks
      </Link>

      {/* Header */}
      <header className="mb-10 pb-6 border-b border-paper-rule">
        <div className="text-[11px] uppercase tracking-widest text-ink-tertiary font-semibold mb-2">
          {d.sector ?? '—'} · {d.industry ?? '—'} · {d.tier ?? '—'}
        </div>
        <h1 className="font-serif text-5xl leading-tight text-ink mb-2">
          <span className="font-mono text-3xl text-ink-secondary mr-3">{d.symbol}</span>
          {d.company_name}
        </h1>
        <div className="text-sm text-ink-secondary">
          {d.in_nifty_50 && <span className="mr-2">Nifty 50</span>}
          {d.in_nifty_100 && !d.in_nifty_50 && <span className="mr-2">Nifty 100</span>}
          {d.in_nifty_500 && !d.in_nifty_100 && <span className="mr-2">Nifty 500</span>}
          {d.refreshed_at && <span className="font-mono text-xs text-ink-tertiary">· refreshed {d.refreshed_at}</span>}
        </div>
      </header>

      {/* Hero readouts */}
      <section className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-10">
        <div className="border border-paper-rule bg-paper-soft p-5 rounded-sm">
          <div className="text-[10px] uppercase tracking-widest text-ink-tertiary font-semibold mb-2">Composite</div>
          <div className={`font-mono text-3xl ${actionTint(d.composite_score != null && d.composite_score > 0 ? 'POSITIVE' : d.composite_score != null && d.composite_score < 0 ? 'NEGATIVE' : null)}`}>
            {d.composite_score != null ? (d.composite_score > 0 ? '+' : '') + d.composite_score.toFixed(1) : '—'}
          </div>
          <div className="text-[10px] uppercase tracking-widest text-ink-tertiary mt-1">{d.confidence_band ?? '—'}</div>
        </div>
        <div className="border border-paper-rule bg-paper-soft p-5 rounded-sm">
          <div className="text-[10px] uppercase tracking-widest text-ink-tertiary font-semibold mb-2">Backing IC</div>
          <div className="font-mono text-3xl text-ink">{fmtNum(d.backing_ic, 3)}</div>
        </div>
        <div className="border border-paper-rule bg-paper-soft p-5 rounded-sm">
          <div className="text-[10px] uppercase tracking-widest text-ink-tertiary font-semibold mb-2">RS state</div>
          <div className="font-mono text-xl text-ink">{d.rs_state ?? '—'}</div>
          <div className="text-[10px] uppercase tracking-widest text-ink-tertiary mt-1">
            since {d.state_since_date ?? '—'}
          </div>
        </div>
        <div className="border border-paper-rule bg-paper-soft p-5 rounded-sm">
          <div className="text-[10px] uppercase tracking-widest text-ink-tertiary font-semibold mb-2">Momentum / Risk</div>
          <div className="font-mono text-base text-ink">{d.momentum_state ?? '—'}</div>
          <div className="font-mono text-base text-ink-secondary">{d.risk_state ?? '—'}</div>
        </div>
      </section>

      {/* Conviction tape strip */}
      <section className="mb-10">
        <h2 className="font-serif text-xl text-ink mb-3">Conviction tape</h2>
        <div className="flex gap-3">
          {(['1m', '3m', '6m', '12m'] as const).map(k => (
            <div key={k} className="flex-1 border border-paper-rule bg-paper-soft p-4 rounded-sm">
              <div className="text-[10px] uppercase tracking-widest text-ink-tertiary font-semibold">{k}</div>
              <div className={`font-mono text-lg mt-1 ${tapeTint(tape[k] ?? null)}`}>{tape[k] ?? '—'}</div>
            </div>
          ))}
        </div>
      </section>

      {/* Open signal calls */}
      {d.open_signal_calls.length > 0 && (
        <section className="mb-10">
          <h2 className="font-serif text-xl text-ink mb-3">Open signal calls</h2>
          <div className="space-y-3">
            {d.open_signal_calls.map(c => (
              <div key={c.cell_id + c.tenure} className="border border-paper-rule p-4 rounded-sm">
                <div className="flex items-baseline justify-between mb-2">
                  <div className="font-serif text-base text-ink">{c.cell_name}</div>
                  <div className={`text-[10px] uppercase tracking-widest font-semibold ${actionTint(c.action)}`}>
                    {c.action === 'POSITIVE' ? 'BUY' : c.action === 'NEGATIVE' ? 'AVOID' : 'WATCH'}
                  </div>
                </div>
                {c.cell_explain && <div className="text-xs text-ink-secondary leading-relaxed mb-2">{c.cell_explain}</div>}
                <div className="text-[11px] font-mono text-ink-tertiary">
                  entry {c.entry_date} · conf {c.confidence}
                  {c.predicted_excess != null && <> · pred {(c.predicted_excess * 100).toFixed(1)}pp</>}
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Returns + RS grid */}
      <section className="mb-10">
        <h2 className="font-serif text-xl text-ink mb-3">Returns &amp; relative strength</h2>
        <div className="border border-paper-rule rounded-sm overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-paper-deep border-b border-paper-rule">
              <tr className="text-[10px] uppercase tracking-wider text-ink-tertiary font-semibold">
                <th className="px-4 py-2 text-left">Window</th>
                <th className="px-4 py-2 text-right">Return</th>
                <th className="px-4 py-2 text-right">RS vs Nifty 500</th>
              </tr>
            </thead>
            <tbody>
              <tr className="border-t border-paper-rule">
                <td className="px-4 py-2 text-ink">1M</td>
                <td className="px-4 py-2 text-right font-mono">{fmtPct(d.ret_1m)}</td>
                <td className="px-4 py-2 text-right font-mono">{fmtPct(d.rs_1m_nifty500)}</td>
              </tr>
              <tr className="border-t border-paper-rule">
                <td className="px-4 py-2 text-ink">3M</td>
                <td className="px-4 py-2 text-right font-mono">{fmtPct(d.ret_3m)}</td>
                <td className="px-4 py-2 text-right font-mono">{fmtPct(d.rs_3m_nifty500)}</td>
              </tr>
              <tr className="border-t border-paper-rule">
                <td className="px-4 py-2 text-ink">6M</td>
                <td className="px-4 py-2 text-right font-mono">{fmtPct(d.ret_6m)}</td>
                <td className="px-4 py-2 text-right font-mono">—</td>
              </tr>
              <tr className="border-t border-paper-rule">
                <td className="px-4 py-2 text-ink">12M</td>
                <td className="px-4 py-2 text-right font-mono">{fmtPct(d.ret_12m)}</td>
                <td className="px-4 py-2 text-right font-mono">—</td>
              </tr>
            </tbody>
          </table>
        </div>
        <div className="text-xs font-mono text-ink-tertiary mt-2">
          RS percentile 3M: {d.rs_pctile_3m != null ? (d.rs_pctile_3m * 100).toFixed(0) : '—'}
          {' · '}vol 63d: {fmtPct(d.realized_vol_63)}
          {' · '}max DD 252d: {fmtPct(d.max_drawdown_252)}
        </div>
      </section>

      {/* Pattern family + gates */}
      <section className="mb-10 grid grid-cols-1 md:grid-cols-2 gap-6">
        <div>
          <h2 className="font-serif text-xl text-ink mb-3">Pattern family</h2>
          <dl className="text-sm space-y-2">
            {(['family_trend', 'family_volatility', 'family_volume', 'family_path', 'family_sector'] as const).map(k => (
              <div key={k} className="flex justify-between border-b border-paper-rule pb-1">
                <dt className="text-ink-tertiary text-xs">{k.replace('family_', '')}</dt>
                <dd className="font-mono text-xs text-ink">{d[k] ?? '—'}</dd>
              </div>
            ))}
          </dl>
        </div>
        <div>
          <h2 className="font-serif text-xl text-ink mb-3">Gates</h2>
          <dl className="text-sm space-y-2">
            <div className="flex justify-between border-b border-paper-rule pb-1">
              <dt className="text-ink-tertiary text-xs">Weinstein</dt>
              <dd className={`font-mono text-xs ${d.weinstein_gate_pass ? 'text-signal-pos' : 'text-signal-neg'}`}>
                {d.weinstein_gate_pass ? 'PASS' : 'FAIL'}
              </dd>
            </div>
            <div className="flex justify-between border-b border-paper-rule pb-1">
              <dt className="text-ink-tertiary text-xs">History</dt>
              <dd className={`font-mono text-xs ${d.history_gate_pass ? 'text-signal-pos' : 'text-signal-neg'}`}>
                {d.history_gate_pass ? 'PASS' : 'FAIL'}
              </dd>
            </div>
            <div className="flex justify-between border-b border-paper-rule pb-1">
              <dt className="text-ink-tertiary text-xs">Liquidity</dt>
              <dd className={`font-mono text-xs ${d.liquidity_gate_pass ? 'text-signal-pos' : 'text-signal-neg'}`}>
                {d.liquidity_gate_pass ? 'PASS' : 'FAIL'}
              </dd>
            </div>
            <div className="flex justify-between border-b border-paper-rule pb-1">
              <dt className="text-ink-tertiary text-xs">Stage-1 base</dt>
              <dd className={`font-mono text-xs ${d.stage1_base_qualifies ? 'text-signal-pos' : 'text-ink-tertiary'}`}>
                {d.stage1_base_qualifies ? 'QUALIFIES' : 'no'}
              </dd>
            </div>
          </dl>
        </div>
      </section>

      <footer className="text-xs text-ink-tertiary leading-relaxed border-t border-paper-rule pt-6">
        Composite score = (conviction_score − 0.5) × 20 ∈ [−10, +10]. Backing IC is the
        information coefficient on the cell signing the call. State machine columns reflect the
        live RS / momentum / risk / volume regime classification.
      </footer>
    </main>
  )
}
