// ETFDetailV4 — the v4 ETF detail page (behind LENS_V4). Lens-first, native foundation_staging.
// An ETF is a holdings-weighted roll-up of the stock atom (D26/D27): the HEADLINE is
// LEADERSHIP-BREADTH (% of holdings weight that are top-decile leaders in ≥2 conviction lenses),
// NOT a composite. The 6-lens vector + look-through are a TRANSPARENCY view of what's held and
// how it scores — descriptive, explicitly NOT positioned as an outperformance predictor.
import Link from 'next/link'
import { notFound } from 'next/navigation'

import { getEtfLensDetail, getEtfChartSeries, type EtfHolding } from '@/lib/queries/v6/etf_lens'
import { StockPriceEMAChart } from '@/components/v6/stock-detail/StockPriceEMAChart'
import { StockRSChart } from '@/components/v6/stock-detail/StockRSChart'
import { Panel } from '@/components/v4/ui/Panel'
import { StatCard } from '@/components/v4/ui/StatCard'
import { decileColor } from '@/components/v4/ui/decile'
import { ScoreDerivationTree } from '@/components/v6/shared/ScoreDerivationTree'
import { holdingsToDerivation } from '@/components/v4/adapters/holdingsToDerivation'
import { TermInfo } from '@/components/v6/shared/TermInfo'

const HOLDING_CAP = 50

// ── colour helpers (shared idioms with the stocks pages) ──────────────────
// Per-holding deciles colour the figure via the shared perceptual ramp; null → tertiary.
const decileStyle = (d: number | null) => ({ color: d == null ? 'var(--color-txt-3)' : decileColor(d) })

const leadText = (lead: number) =>
  lead >= 3 ? 'text-sig-pos' : lead === 2 ? 'text-brand' : lead === 1 ? 'text-sig-warn' : 'text-txt-3'

const pctText = (v: number | null) =>
  v == null ? 'text-txt-3' : v >= 0 ? 'text-sig-pos' : 'text-sig-neg'

const fmtRs = (v: number | null) => (v == null ? '—' : `${v >= 0 ? '+' : ''}${(v * 100).toFixed(1)}%`)

// ── look-through holdings table (sorted by weight desc upstream) ──────────
function HoldingsTable({ holdings }: { holdings: EtfHolding[] }) {
  const rows = holdings.slice(0, HOLDING_CAP)
  const truncated = holdings.length > HOLDING_CAP
  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse">
        <thead>
          <tr className="border-b border-edge-rule">
            {([['Symbol', undefined], ['Sector', 'sector_name']] as const).map(([h, term]) => (
              <th key={h} className="whitespace-nowrap px-2 pb-2 text-left font-sans text-[10px] uppercase tracking-wider text-txt-3">{h}{term && <TermInfo term={term} />}</th>
            ))}
            {([['Weight', 'holding_weight'], ['Tch', 'decile'], ['Fnd', 'decile'], ['Cat', 'decile'], ['Flw', 'decile'], ['Val', 'decile'], ['Lead', 'lead'], ['RS 3M', 'rs']] as const).map(([h, term]) => (
              <th key={h} className="whitespace-nowrap px-2 pb-2 text-right font-sans text-[10px] uppercase tracking-wider text-txt-3">{h}{term && <TermInfo term={term} />}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map(h => (
            <tr key={h.symbol} className="border-b border-edge-hair hover:bg-surface-raised">
              <td className="whitespace-nowrap px-2 py-1.5 font-num text-[12px] font-semibold tabular-nums">
                <Link href={`/stocks/${h.symbol}`} className="text-txt-1 hover:text-brand hover:underline">{h.symbol}</Link>
              </td>
              <td className="max-w-[160px] truncate px-2 py-1.5 font-sans text-[11px] text-txt-2">{h.sector ?? '—'}</td>
              <td className="px-2 py-1.5 text-right font-num text-[12px] tabular-nums text-txt-2">
                {h.weight == null ? '—' : `${(h.weight * 100).toFixed(2)}%`}
              </td>
              <td className="px-2 py-1.5 text-right font-num text-[12px] tabular-nums" style={decileStyle(h.d_tech)}>{h.d_tech ?? '—'}</td>
              <td className="px-2 py-1.5 text-right font-num text-[12px] tabular-nums" style={decileStyle(h.d_fund)}>{h.d_fund ?? '—'}</td>
              <td className="px-2 py-1.5 text-right font-num text-[12px] tabular-nums" style={decileStyle(h.d_cat)}>{h.d_cat ?? '—'}</td>
              <td className="px-2 py-1.5 text-right font-num text-[12px] tabular-nums" style={decileStyle(h.d_flow)}>{h.d_flow ?? '—'}</td>
              <td className="px-2 py-1.5 text-right font-num text-[12px] tabular-nums" style={decileStyle(h.d_val)}>{h.d_val ?? '—'}</td>
              <td className={`px-2 py-1.5 text-right font-num text-[12px] tabular-nums ${leadText(h.lead)}`}>{h.lead}/4</td>
              <td className={`px-2 py-1.5 text-right font-num text-[12px] tabular-nums ${pctText(h.rs_3m)}`}>{fmtRs(h.rs_3m)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {truncated && (
        <p className="mt-3 font-sans text-[11px] text-txt-3">
          showing top {HOLDING_CAP} of {holdings.length} holdings by weight
        </p>
      )}
    </div>
  )
}

export async function ETFDetailV4({ fcode }: { fcode: string }) {
  const etf = await getEtfLensDetail(fcode)
  if (!etf) notFound()
  // Native Lightweight charts (price ÷ index) for bridged ETFs — TV's embed refuses NSE symbols.
  const etfRows = etf.nse_ticker ? await getEtfChartSeries(etf.nse_ticker).catch(() => []) : []

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
    <div className="mx-auto max-w-[1280px] space-y-6 px-6 py-7">
      {/* ── Header ── */}
      <header>
        <nav className="mb-3 font-num text-[11px] text-txt-3" aria-label="Breadcrumb">
          <Link href="/" className="text-brand hover:underline">Atlas</Link> ›{' '}
          <Link href="/etfs" className="text-brand hover:underline">ETFs</Link> ›{' '}
          <span aria-current="page">{etf.name}</span>
        </nav>
        <div className="flex flex-wrap items-start justify-between gap-6">
          <div className="min-w-0 flex-1">
            <h1 className="font-display text-[36px] font-bold leading-[1.05] tracking-tight text-txt-1">{etf.name}</h1>
            <div className="mt-2 font-num text-[12px] text-txt-3">{subParts.join(' · ')}</div>
            <p className="mt-3 max-w-[760px] font-sans text-[14px] leading-[1.5] text-txt-2">
              How this ETF&apos;s holdings score on the six lenses, weighted by holding weight. A transparency
              roll-up of the stock atom — descriptive, <em>not</em> a forecast of outperformance.
            </p>
          </div>
          {/* leadership-breadth headline badge */}
          <div className="w-[200px] shrink-0">
            <StatCard
              label="Leadership-breadth"
              value={breadthPct}
              tone="pos"
              sub={`${etf.n_leaders} of ${etf.n_holdings} holdings lead ≥2 lenses`}
            />
          </div>
        </div>
      </header>

      {/* ── Glass box: Score-Derivation Tree (Leadership-breadth → lens → holdings by contribution) ── */}
      <section aria-label="How the score is built">
        <div className="mb-4">
          <p className="font-num text-[9px] uppercase tracking-[0.14em] text-txt-3">Glass box</p>
          <h2 className="font-display text-[22px] font-medium tracking-tight text-txt-1">How the score is built</h2>
          <p className="mt-1 max-w-[760px] font-sans text-[13px] text-txt-2">
            Click a lens to expand its holdings, ranked by contribution (weight × decile); each name links to its own evidence. Descriptive, not a forecast.
          </p>
        </div>
        <ScoreDerivationTree root={holdingsToDerivation(etf.name, etf, etf.holdings)} />
      </section>

      {/* ── Charts (native Lightweight; bridged ETFs only) ── */}
      {etfRows.length > 0 && etf.nse_ticker ? (
        <Panel eyebrow="Trend" title="Price & relative strength" bodyClassName="space-y-8 px-5 py-4">
          <StockPriceEMAChart rows={etfRows} symbol={etf.nse_ticker} />
          <StockRSChart rows={etfRows} symbol={etf.nse_ticker} />
        </Panel>
      ) : (
        <Panel eyebrow="Trend" title="Price & relative strength">
          <p className="font-sans text-[13px] italic text-txt-3">
            No NSE price series mapped for this ETF — lens roll-up only.
          </p>
        </Panel>
      )}

      {/* ── Look-through holdings ── */}
      <Panel
        eyebrow="Look-through"
        title="Look-through holdings"
        info={{ body: 'Every holding by weight, with each name’s lens deciles, leadership and 3-month RS. Click a symbol for its full evidence.' }}
      >
        {etf.holdings.length > 0
          ? <HoldingsTable holdings={etf.holdings} />
          : <p className="font-sans text-[13px] italic text-txt-3">No scored holdings for this ETF.</p>}
      </Panel>

      <p className="font-sans text-[12px] leading-[1.6] text-txt-3">
        Native from <strong className="text-txt-2">foundation_staging</strong> — the lens journal looked through
        de_etf_holdings; identity from Morningstar (de_mf_master).{' '}
        <Link href="/etfs" className="text-brand hover:underline">← Back to ETFs</Link>
      </p>
    </div>
  )
}
