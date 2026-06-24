// ETFDetailV4 — the v4 ETF detail page (behind LENS_V4). Lens-first, native foundation_staging.
// An ETF is a holdings-weighted roll-up of the stock atom (D26/D27): the HEADLINE is
// LEADERSHIP-BREADTH (% of holdings weight that are top-decile leaders in ≥2 conviction lenses),
// NOT a composite. The 6-lens vector + look-through are a TRANSPARENCY view of what's held and
// how it scores — descriptive, explicitly NOT positioned as an outperformance predictor.
import Link from 'next/link'
import { notFound } from 'next/navigation'

import { getEtfLensDetail, type EtfLensDetail, type EtfHolding } from '@/lib/queries/v6/etf_lens'
import { TVRatioChart } from '@/components/charts/TVRatioChart'

const HOLDING_CAP = 50

// ── colour helpers (shared idioms with the stocks pages) ──────────────────
const decileText = (d: number | null) =>
  d == null ? 'text-ink-tertiary' : d >= 8 ? 'text-signal-pos' : d >= 5 ? 'text-ink-secondary' : 'text-signal-neg'

const leadText = (lead: number) =>
  lead >= 3 ? 'text-signal-pos' : lead === 2 ? 'text-teal' : lead === 1 ? 'text-signal-warn' : 'text-ink-tertiary'

const pctText = (v: number | null) =>
  v == null ? 'text-ink-tertiary' : v >= 0 ? 'text-signal-pos' : 'text-signal-neg'

const fmtRs = (v: number | null) => (v == null ? '—' : `${v >= 0 ? '+' : ''}${(v * 100).toFixed(1)}%`)

// ── holdings-weighted six-lens vector (0..100, bars) ──────────────────────
const LENS_VECTOR: { key: keyof Pick<EtfLensDetail, 'v_tech' | 'v_fund' | 'v_cat' | 'v_flow' | 'v_val'>; label: string }[] = [
  { key: 'v_tech', label: 'Technical' },
  { key: 'v_fund', label: 'Fundamental' },
  { key: 'v_cat', label: 'Catalyst' },
  { key: 'v_flow', label: 'Flow' },
  { key: 'v_val', label: 'Valuation' },
]
const barColor = (v: number) => (v >= 80 ? 'bg-signal-pos' : v >= 50 ? 'bg-signal-warn' : 'bg-signal-neg')

function LensVector({ etf }: { etf: EtfLensDetail }) {
  const scored = LENS_VECTOR
    .map(l => ({ label: l.label, v: etf[l.key] }))
    .filter((x): x is { label: string; v: number } => x.v != null)
  return (
    <div className="space-y-2 max-w-[560px]">
      {scored.length === 0 && <p className="font-sans text-[13px] text-ink-tertiary italic">No scored holdings.</p>}
      {scored.map(l => (
        <div key={l.label} className="flex items-center gap-3">
          <span className="w-[96px] shrink-0 font-sans text-xs text-ink-secondary">{l.label}</span>
          <span className="w-[34px] shrink-0 font-mono text-xs tabular-nums text-ink-primary text-right">{l.v.toFixed(0)}</span>
          <span className="flex-1 h-[7px] bg-paper-deep rounded-[2px] overflow-hidden">
            <span className={`block h-full rounded-[2px] ${barColor(l.v)}`} style={{ width: `${Math.min(100, l.v)}%` }} />
          </span>
        </div>
      ))}
    </div>
  )
}

// ── look-through holdings table (sorted by weight desc upstream) ──────────
function HoldingsTable({ holdings }: { holdings: EtfHolding[] }) {
  const rows = holdings.slice(0, HOLDING_CAP)
  const truncated = holdings.length > HOLDING_CAP
  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse">
        <thead>
          <tr className="border-b border-paper-rule">
            {(['Symbol', 'Sector'] as const).map(h => (
              <th key={h} className="font-sans text-[10px] uppercase tracking-wider pb-2 px-2 text-left text-ink-tertiary whitespace-nowrap">{h}</th>
            ))}
            {(['Weight', 'Tch', 'Fnd', 'Cat', 'Flw', 'Val', 'Lead', 'RS 3M'] as const).map(h => (
              <th key={h} className="font-sans text-[10px] uppercase tracking-wider pb-2 px-2 text-right text-ink-tertiary whitespace-nowrap">{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map(h => (
            <tr key={h.symbol} className="border-b border-paper-rule/50 hover:bg-paper-soft">
              <td className="py-1.5 px-2 font-mono text-[12px] font-semibold whitespace-nowrap">
                <a href={`/stocks/${h.symbol}`} className="text-ink-primary no-underline hover:text-teal hover:underline">{h.symbol}</a>
              </td>
              <td className="py-1.5 px-2 font-sans text-[11px] text-ink-secondary truncate max-w-[160px]">{h.sector ?? '—'}</td>
              <td className="py-1.5 px-2 text-right font-mono text-[12px] tabular-nums text-ink-secondary">
                {h.weight == null ? '—' : `${(h.weight * 100).toFixed(2)}%`}
              </td>
              <td className={`py-1.5 px-2 text-right font-mono text-[12px] tabular-nums ${decileText(h.d_tech)}`}>{h.d_tech ?? '—'}</td>
              <td className={`py-1.5 px-2 text-right font-mono text-[12px] tabular-nums ${decileText(h.d_fund)}`}>{h.d_fund ?? '—'}</td>
              <td className={`py-1.5 px-2 text-right font-mono text-[12px] tabular-nums ${decileText(h.d_cat)}`}>{h.d_cat ?? '—'}</td>
              <td className={`py-1.5 px-2 text-right font-mono text-[12px] tabular-nums ${decileText(h.d_flow)}`}>{h.d_flow ?? '—'}</td>
              <td className={`py-1.5 px-2 text-right font-mono text-[12px] tabular-nums ${decileText(h.d_val)}`}>{h.d_val ?? '—'}</td>
              <td className={`py-1.5 px-2 text-right font-mono text-[12px] tabular-nums ${leadText(h.lead)}`}>{h.lead}/4</td>
              <td className={`py-1.5 px-2 text-right font-mono text-[12px] tabular-nums ${pctText(h.rs_3m)}`}>{fmtRs(h.rs_3m)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {truncated && (
        <p className="font-sans text-[11px] text-ink-tertiary mt-3">
          showing top {HOLDING_CAP} of {holdings.length} holdings by weight
        </p>
      )}
    </div>
  )
}

export async function ETFDetailV4({ fcode }: { fcode: string }) {
  const etf = await getEtfLensDetail(fcode)
  if (!etf) notFound()

  const breadthPct = etf.breadth == null ? '—' : `${(etf.breadth * 100).toFixed(0)}%`
  const expenseStr = etf.expense == null ? null : `${etf.expense.toFixed(2)}%` // already in percent units
  const subParts = [
    etf.category,
    etf.amc,
    expenseStr ? `expense ${expenseStr}` : null,
    `${etf.n_holdings} holdings`,
    etf.isin,
  ].filter((x): x is string => !!x)

  return (
    <div className="max-w-[1400px] mx-auto">
      {/* ── Header ── */}
      <section className="px-8 py-9 border-b border-paper-rule">
        <nav className="font-sans text-[12px] text-ink-tertiary mb-3" aria-label="Breadcrumb">
          <Link href="/" className="text-teal hover:underline no-underline">Atlas</Link> ›{' '}
          <Link href="/etfs" className="text-teal hover:underline no-underline">ETFs</Link> ›{' '}
          <span aria-current="page">{etf.name}</span>
        </nav>
        <div className="flex items-start justify-between gap-6 flex-wrap">
          <div className="min-w-0 flex-1">
            <h1 className="font-serif text-[44px] font-normal tracking-[-0.011em] text-ink-primary leading-[1.05]">{etf.name}</h1>
            <div className="font-mono text-[12px] text-ink-tertiary mt-2">{subParts.join(' · ')}</div>
            <p className="font-sans text-[15px] text-ink-secondary max-w-[760px] mt-3">
              How this ETF&apos;s holdings score on the six lenses, weighted by holding weight. A transparency
              roll-up of the stock atom — descriptive, <em>not</em> a forecast of outperformance.
            </p>
          </div>
          {/* leadership-breadth headline badge */}
          <div className="shrink-0 bg-paper-soft border border-paper-rule rounded-sm px-5 py-4 text-center min-w-[180px]">
            <div className="font-mono text-[40px] font-medium leading-none text-signal-pos">{breadthPct}</div>
            <div className="font-sans text-[10px] uppercase tracking-[0.14em] text-ink-tertiary font-semibold mt-2">leadership-breadth</div>
            <div className="font-sans text-[11px] text-ink-tertiary mt-1 leading-snug">
              {etf.n_leaders} of {etf.n_holdings} holdings lead ≥2 lenses
            </div>
          </div>
        </div>
      </section>

      {/* ── Holdings-weighted six-lens vector ── */}
      <section className="px-8 py-9 border-b border-paper-rule" aria-label="Holdings-weighted lens vector">
        <div className="mb-5">
          <h2 className="font-serif text-[28px] font-normal tracking-tight text-ink-primary">How the holdings score on each lens</h2>
          <p className="font-sans text-[13px] text-ink-tertiary max-w-[760px] leading-[1.45] mt-1">
            Weight-weighted average of each holding&apos;s lens score (0–100) — descriptive, not a forecast.
          </p>
        </div>
        <LensVector etf={etf} />
      </section>

      {/* ── Charts (matched ETFs only) ── */}
      <section className="px-8 py-9 border-b border-paper-rule" aria-label="Price & RS charts">
        <div className="mb-5">
          <h2 className="font-serif text-[28px] font-normal tracking-tight text-ink-primary">Price &amp; relative strength</h2>
          {etf.benchmark && (
            <p className="font-sans text-[13px] text-ink-tertiary mt-1">Benchmark: {etf.benchmark}</p>
          )}
        </div>
        {etf.nse_ticker ? (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <TVRatioChart symbol={`NSE:${etf.nse_ticker}`} title="Price" interval="W" height={360} />
            <TVRatioChart
              symbol={`NSE:${etf.nse_ticker}/NSE:NIFTY`}
              title="RS vs Nifty 50"
              subtitle="Rising = outperforming the broad market"
              interval="W"
              height={300}
            />
          </div>
        ) : (
          <p className="font-sans text-[13px] text-ink-tertiary italic">
            No NSE price series mapped for this ETF — lens roll-up only.
          </p>
        )}
      </section>

      {/* ── Look-through holdings ── */}
      <section className="px-8 py-9 border-b border-paper-rule" aria-label="Look-through holdings">
        <div className="mb-5">
          <h2 className="font-serif text-[28px] font-normal tracking-tight text-ink-primary">Look-through holdings</h2>
          <p className="font-sans text-[13px] text-ink-tertiary max-w-[760px] leading-[1.45] mt-1">
            Every holding by weight, with each name&apos;s lens deciles, leadership and 3-month RS. Click a symbol for its full evidence.
          </p>
        </div>
        {etf.holdings.length > 0
          ? <HoldingsTable holdings={etf.holdings} />
          : <p className="font-sans text-[13px] text-ink-tertiary italic">No scored holdings for this ETF.</p>}
      </section>

      <div className="px-8 py-6 font-sans text-[12px] text-ink-tertiary leading-[1.6]">
        Native from <strong className="text-ink-secondary">foundation_staging</strong> — the lens journal looked through
        de_etf_holdings; identity from Morningstar (de_mf_master).{' '}
        <Link href="/etfs" className="text-teal hover:underline">← Back to ETFs</Link>
      </div>
    </div>
  )
}
