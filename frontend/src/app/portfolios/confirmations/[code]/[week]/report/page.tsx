// The circulated report. Everything here is the stored snapshot — a published
// report renders exactly as it was published, forever.
export const dynamic = 'force-dynamic'

import { notFound } from 'next/navigation'
import Link from 'next/link'

import { PrintButton } from '@/components/confirmations/PrintButton'
import { SectorPie } from '@/components/confirmations/SectorPie'
import {
  cashPct,
  instrumentHref,
  PORTFOLIO_CODES,
  PORTFOLIO_NAMES,
  type PortfolioCode,
} from '@/lib/confirmations'
import { getConfirmation, type CallRow } from '@/lib/queries/confirmations'
import { formatIST } from '@/lib/format-date'

export const metadata = { title: 'Confirmation report · Atlas' }

/** The rationale + attached chart under a side's table. */
function CallNotes({ calls }: { calls: CallRow[] }) {
  const withNotes = calls.filter((k) => k.comment || (k.hasImage && k.callId != null))
  if (withNotes.length === 0) return null
  return (
    <div className="mt-3 space-y-3">
      {withNotes.map((k) => (
        <figure key={k.key} className="break-inside-avoid">
          {k.comment && (
            <p className="font-sans text-[12.5px] text-txt-2">
              <span className="font-num font-semibold text-txt-1">{k.symbol} — </span>
              {k.comment}
            </p>
          )}
          {k.hasImage && k.callId != null && (
            <img
              src={`/api/confirmations/image/call/${k.callId}`}
              alt={`${k.symbol} chart`}
              className="mt-1.5 max-w-full rounded-tile border border-edge-hair"
            />
          )}
        </figure>
      ))}
    </div>
  )
}

const pct1 = (v: number) => `${v.toFixed(1)}%`
const inr = (v: number | null) => (v == null ? '—' : `₹${v.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`)

export default async function ReportPage({ params }: { params: Promise<{ code: string; week: string }> }) {
  const { code, week } = await params
  if (!(PORTFOLIO_CODES as readonly string[]).includes(code)) notFound()
  const pf = code as PortfolioCode
  const c = await getConfirmation(pf, week)
  if (!c) notFound()

  const buys = c.calls.filter((k) => k.side === 'buy')
  const sells = c.calls.filter((k) => k.side === 'sell')
  const cash = cashPct(c.resultingBook)

  return (
    <div className="report-page mx-auto max-w-[1000px] space-y-6 px-6 py-7">
      <div className="flex items-start justify-between gap-4 print:hidden">
        <Link
          href={`/portfolios/confirmations/${pf}/${week}`}
          className="font-num text-[11px] uppercase tracking-[0.14em] text-accent no-underline hover:underline"
        >
          ← Back to the editor
        </Link>
        <PrintButton />
      </div>

      <header className="border-b border-edge-rule pb-4">
        <p className="font-num text-[9px] uppercase tracking-[0.14em] text-txt-3">
          Model portfolio · confirmation &amp; stock selection
        </p>
        <h1 className="font-display text-[26px] font-medium tracking-tight text-txt-1">
          {PORTFOLIO_NAMES[pf]}
        </h1>
        <p className="font-sans text-[13px] text-txt-2">
          Week of {formatIST(week)}
          {c.status === 'published' && c.publishedAt ? ` · published ${formatIST(c.publishedAt, true)}` : ' · DRAFT'}
        </p>
      </header>

      {buys.length > 0 && (
        <section className="break-inside-avoid">
          <h2 className="mb-2 font-num text-[10px] uppercase tracking-[0.14em] text-sig-pos">Buy</h2>
          <table className="w-full border-collapse font-sans text-[12.5px]">
            <thead>
              <tr className="border-b border-edge-rule text-left font-num text-[9px] uppercase tracking-wider text-txt-3">
                <th className="py-1.5">Instrument</th>
                <th className="py-1.5">Sector</th>
                <th className="py-1.5 text-right">Weight</th>
                <th className="py-1.5 text-right">Trigger</th>
                <th className="py-1.5 text-right">Stop</th>
              </tr>
            </thead>
            <tbody>
              {buys.map((k) => (
                <tr key={k.key} className="border-b border-edge-hair align-top">
                  <td className="py-2">
                    <Link
                      href={instrumentHref(k.key)}
                      className="font-num font-semibold text-txt-1 no-underline hover:text-accent hover:underline"
                    >
                      {k.symbol}
                    </Link>
                    <div className="text-[11.5px] text-txt-3">{k.name}</div>
                  </td>
                  <td className="py-2 text-txt-2">{k.sector ?? '—'}</td>
                  <td className="py-2 text-right font-num tabular-nums text-txt-1">{pct1(k.weightPct)}</td>
                  <td className="py-2 text-right font-num tabular-nums text-txt-2">{inr(k.triggerPrice)}</td>
                  <td className="py-2 text-right font-num tabular-nums text-txt-2">{inr(k.stopPrice)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <CallNotes calls={buys} />
        </section>
      )}

      {sells.length > 0 && (
        <section className="break-inside-avoid">
          <h2 className="mb-2 font-num text-[10px] uppercase tracking-[0.14em] text-sig-neg">Sell</h2>
          <table className="w-full border-collapse font-sans text-[12.5px]">
            <thead>
              <tr className="border-b border-edge-rule text-left font-num text-[9px] uppercase tracking-wider text-txt-3">
                <th className="py-1.5">Instrument</th>
                <th className="py-1.5">Sector</th>
                <th className="py-1.5 pr-6 text-right">Weight sold</th>
                <th className="py-1.5">Reason</th>
              </tr>
            </thead>
            <tbody>
              {sells.map((k) => (
                <tr key={k.key} className="border-b border-edge-hair align-top">
                  <td className="py-2">
                    <Link
                      href={instrumentHref(k.key)}
                      className="font-num font-semibold text-txt-1 no-underline hover:text-accent hover:underline"
                    >
                      {k.symbol}
                    </Link>
                    <div className="text-[11.5px] text-txt-3">{k.name}</div>
                  </td>
                  <td className="py-2 text-txt-2">{k.sector ?? '—'}</td>
                  <td className="py-2 pr-6 text-right font-num tabular-nums text-txt-1">{pct1(k.weightPct)}</td>
                  <td className="py-2 text-txt-2">{k.reasons.join(' · ') || '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <CallNotes calls={sells} />
        </section>
      )}

      {c.evidence.length > 0 && (
        <section>
          <h2 className="mb-2 font-num text-[10px] uppercase tracking-[0.14em] text-txt-3">
            Additional weight of evidence
          </h2>
          <div className="space-y-4">
            {c.evidence.map((e) => (
              <figure key={e.position} className="break-inside-avoid">
                {e.title && <h3 className="font-display text-[15px] font-semibold text-txt-1">{e.title}</h3>}
                {e.comment && <p className="font-sans text-[12.5px] text-txt-2">{e.comment}</p>}
                {e.hasImage && e.evidenceId != null && (
                  <img
                    src={`/api/confirmations/image/evidence/${e.evidenceId}`}
                    alt={e.title || 'Supporting chart'}
                    className="mt-1.5 max-w-full rounded-tile border border-edge-hair"
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
                  <td className="py-1.5 text-right font-num tabular-nums text-txt-1">{pct1(p.weightPct)}</td>
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
                <td className="py-1.5 text-right font-num font-semibold tabular-nums text-txt-1">100.00%</td>
              </tr>
            </tbody>
          </table>
          <SectorPie book={c.resultingBook} cash={cash} />
        </div>
      </section>

      <footer className="border-t border-edge-rule pt-3 font-sans text-[11px] text-txt-3">
        Generated by Atlas · {PORTFOLIO_NAMES[pf]} · week of {formatIST(week)}. Weights are model
        targets, not executed positions.
      </footer>
    </div>
  )
}
