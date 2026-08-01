// The circulated report. Everything here is the stored snapshot — a published
// report renders exactly as it was published, forever.
//
// Shape (FM, 2026-08-01): the desk needs to ACT first and read second. So the
// document leads with one checklist of everything to be done, then gives one card
// per instrument carrying the chart and the reasoning. The old layout split buys
// and sells into separate tables with the notes stranded underneath, which meant
// reading the whole document to know what to trade.
export const dynamic = 'force-dynamic'

import { notFound } from 'next/navigation'
import Link from 'next/link'

import { PrintButton } from '@/components/maal/PrintButton'
import { SectorPie } from '@/components/maal/SectorPie'
import { ActionChecklist, InstrumentCard } from '@/components/maal/ReportActions'
import { cashPct, instrumentHref, MAAL_CODES, MAAL_NAMES, type MaalCode } from '@/lib/maal'
import { getConfirmation, type CallRow } from '@/lib/queries/maal'
import { formatIST } from '@/lib/format-date'

export const metadata = { title: 'MaaL report · Atlas' }

const pct1 = (v: number) => `${v.toFixed(1)}%`
const inr = (v: number | null) =>
  v == null
    ? '—'
    : `₹${v.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`

export default async function ReportPage({
  params,
}: {
  params: Promise<{ code: string; week: string }>
}) {
  const { code, week } = await params
  if (!(MAAL_CODES as readonly string[]).includes(code)) notFound()
  const pf = code as MaalCode
  const c = await getConfirmation(pf, week)
  if (!c) notFound()

  // Sells first: freeing the money comes before deploying it, and that is the order
  // the desk works in.
  const actions = [
    ...c.calls.filter((k) => k.side === 'sell'),
    ...c.calls.filter((k) => k.side === 'buy'),
  ]
  const cash = cashPct(c.resultingBook)
  const buyCount = c.calls.filter((k) => k.side === 'buy').length
  const sellCount = c.calls.length - buyCount

  return (
    <div className="report-page mx-auto max-w-[1000px] space-y-6 px-6 py-7">
      <div className="flex items-start justify-between gap-4 print:hidden">
        <Link
          href={`/portfolios/maal/${pf}/${week}`}
          className="font-num text-[11px] uppercase tracking-[0.14em] text-accent no-underline hover:underline"
        >
          ← Back to the editor
        </Link>
        <PrintButton />
      </div>

      <header className="border-b border-edge-rule pb-4">
        <p className="font-num text-[9px] uppercase tracking-[0.14em] text-txt-3">
          MaaL Process · weekly buy / sell document
        </p>
        <h1 className="font-display text-[26px] font-medium tracking-tight text-txt-1">
          {MAAL_NAMES[pf]}
        </h1>
        <p className="font-sans text-[13px] text-txt-2">
          Week of {formatIST(week)}
          {c.status === 'published' && c.publishedAt
            ? ` · published ${formatIST(c.publishedAt, true)}`
            : ' · DRAFT'}
          {' · '}
          {sellCount} sell{sellCount === 1 ? '' : 's'}, {buyCount} buy
          {buyCount === 1 ? '' : 's'}
        </p>
      </header>

      {actions.length === 0 ? (
        <p className="font-sans text-[13px] italic text-txt-3">
          No calls this week — the book carries forward unchanged.
        </p>
      ) : (
        <>
          {/* ── 1. THE CHECKLIST ─────────────────────────────────────────────
              Everything to be done, in execution order, on one page. The tick
              boxes are for the person working the list on paper. */}
          <section className="break-inside-avoid">
            <h2 className="mb-2 font-num text-[10px] uppercase tracking-[0.14em] text-txt-3">
              What to do this week
            </h2>
            <ActionChecklist actions={actions} />
          </section>

          {/* ── 2. THE EVIDENCE ──────────────────────────────────────────────
              One card per instrument, in the same order as the checklist. */}
          <section>
            <h2 className="mb-2 font-num text-[10px] uppercase tracking-[0.14em] text-txt-3">
              The case, instrument by instrument
            </h2>
            <div className="space-y-3">
              {actions.map((k) => (
                <InstrumentCard key={`card:${k.side}:${k.key}`} k={k} />
              ))}
            </div>
          </section>
        </>
      )}

      {c.evidence.length > 0 && (
        <section>
          <h2 className="mb-2 font-num text-[10px] uppercase tracking-[0.14em] text-txt-3">
            Additional weight of evidence
          </h2>
          <div className="space-y-4">
            {c.evidence.map((e) => (
              <figure
                key={e.position}
                className="break-inside-avoid rounded-panel border border-edge-hair bg-surface-panel p-4"
              >
                {e.title && (
                  <h3 className="font-display text-[15px] font-semibold text-txt-1">{e.title}</h3>
                )}
                {e.comment && (
                  <p className="mt-1 font-sans text-[12.5px] leading-relaxed text-txt-2">
                    {e.comment}
                  </p>
                )}
                {e.hasImage && e.evidenceId != null && (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img
                    src={`/api/maal/image/evidence/${e.evidenceId}`}
                    alt={e.title || 'Supporting chart'}
                    className="mt-2 max-w-full rounded-tile border border-edge-hair"
                  />
                )}
              </figure>
            ))}
          </div>
        </section>
      )}

      <section className="break-inside-avoid">
        <h2 className="mb-2 font-num text-[10px] uppercase tracking-[0.14em] text-txt-3">
          Model portfolio after these changes
        </h2>
        <div className="flex flex-wrap items-start gap-8">
          <table className="min-w-[300px] flex-1 border-collapse font-sans text-[12.5px]">
            <thead>
              <tr className="border-b border-edge-rule text-left font-num text-[9px] uppercase tracking-wider text-txt-3">
                <th className="py-1.5">Instrument</th>
                <th className="py-1.5">Sector</th>
                <th className="py-1.5 text-right">Weight</th>
              </tr>
            </thead>
            <tbody>
              {c.resultingBook.map((p) => (
                <tr key={p.key} className="border-b border-edge-hair">
                  <td className="py-1.5">
                    <Link
                      href={instrumentHref(p.key)}
                      className="font-num text-txt-1 no-underline hover:text-accent hover:underline"
                    >
                      {p.symbol}
                    </Link>
                  </td>
                  <td className="py-1.5 text-txt-2">{p.sector ?? '—'}</td>
                  <td className="py-1.5 text-right font-num tabular-nums text-txt-1">
                    {pct1(p.weightPct)}
                  </td>
                </tr>
              ))}
              <tr className="border-b border-edge-hair">
                <td className="py-1.5 font-num text-txt-2">Cash</td>
                <td />
                <td className="py-1.5 text-right font-num tabular-nums text-txt-2">{pct1(cash)}</td>
              </tr>
              <tr>
                <td className="py-1.5 font-num font-semibold text-txt-1">Total</td>
                <td />
                <td className="py-1.5 text-right font-num font-semibold tabular-nums text-txt-1">
                  100.0%
                </td>
              </tr>
            </tbody>
          </table>
          <SectorPie book={c.resultingBook} cash={cash} />
        </div>
      </section>

      <footer className="border-t border-edge-rule pt-3 font-sans text-[11px] text-txt-3">
        Generated by Atlas · {MAAL_NAMES[pf]} · week of {formatIST(week)}. Weights are model
        targets, not executed positions.
      </footer>
    </div>
  )
}
