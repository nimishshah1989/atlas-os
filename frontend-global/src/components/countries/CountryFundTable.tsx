'use client'
// src/components/countries/CountryFundTable.tsx — every US-listed fund covering one market,
// ranked against each other. The question this table answers is the FM's: given that I want this
// country, WHICH fund do I buy?
//
// So the ranking is cut WITHIN the market, not across the world. A Japan fund in the top decile
// here is the best way to own Japan; it says nothing about whether Japan is worth owning, which
// is what the market's own score above says. Two different questions, two different populations,
// and conflating them is how a table starts lying.
//
// A fund with no rank is not last. It is geared, inverse, currency-hedged or below the liquidity
// floor, so the scorer never looked at it — the flags column says which, and it sits below the
// ranked block rather than at the bottom of it.
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { DecileMeter } from '@/components/ui/DecileMeter'
import { formatPct, formatUsd } from '@/lib/format'
import type { CountryFund } from '@/lib/countries'
import { decileColour } from '@/lib/scores'
import { RsCell } from './RsCell'

const SHOWN = ['3m', '6m', '12m'] as const
const LABEL: Record<(typeof SHOWN)[number], string> = { '3m': '3M', '6m': '6M', '12m': '1Y' }

/** Why the scorer skipped this fund — the same three exclusions build_country_views.py applies. */
function flags(f: CountryFund): string | null {
  const on = [f.leveraged && 'geared', f.inverse && 'inverse', f.hedged && 'hedged'].filter(Boolean)
  return on.length ? on.join(' · ') : null
}

export function CountryFundTable({ funds }: { funds: CountryFund[] }) {
  const router = useRouter()
  if (funds.length === 0) {
    return <p className="text-body text-ink-2">No classified fund names this market yet.</p>
  }
  const th = 'bg-raised px-3 py-1.5 text-meta font-semibold uppercase tracking-[0.1em] text-ink-3'
  return (
    <div className="dt panel">
      <table className="w-full border-collapse">
        <thead>
          <tr className="border-b border-rule">
            <th className={`${th} text-right`}>#</th>
            <th className={`${th} text-left`}>Fund</th>
            <th className={`${th} border-l border-rule text-right`}>Score</th>
            <th className={`${th} text-left`}>Decile</th>
            <th className={`${th} text-right`}>ADV $</th>
            <th className={`${th} text-right`}>Expense</th>
            <th className={`${th} text-right`}>AUM</th>
            {SHOWN.map((w, i) => (
              <th key={w} className={`${th} text-right ${i === 0 ? 'border-l border-rule' : ''}`}>
                {LABEL[w]} vs SPY
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {funds.map((f) => {
            const href = `/etfs/${encodeURIComponent(f.symbol)}`
            const composite = f.composite == null ? null : Number(f.composite)
            const excluded = flags(f)
            return (
              <tr
                key={f.instrument_id}
                className="cursor-pointer border-t border-hair transition-colors hover:bg-raised"
                onClick={() => router.push(href)}
              >
                <td className="px-3 py-2 text-right text-table num text-ink-2">
                  {f.rank ?? <span className="text-ink-3">—</span>}
                </td>
                <td className="px-3 py-2 text-table">
                  <Link href={href} className="font-medium text-ink" onClick={(e) => e.stopPropagation()}>
                    {f.symbol}
                  </Link>
                  {f.is_representative && (
                    <span
                      className="ml-2 rounded-tile border border-edge-hair bg-inset px-1.5 py-0.5 text-meta text-ink-2"
                      title="The fund this market's score, chart and relative strength are taken from"
                    >
                      represents
                    </span>
                  )}
                  <span className="ml-2 text-meta text-ink-3">{f.name}</span>
                  {excluded && <span className="ml-2 text-meta text-neg">{excluded}</span>}
                </td>
                <td className="border-l border-rule px-3 py-2 text-right text-table num">
                  {composite == null ? (
                    <span className="text-ink-3">—</span>
                  ) : (
                    <span className="font-semibold" style={{ color: decileColour(f.decile) ?? undefined }}>
                      {composite.toFixed(0)}
                    </span>
                  )}
                </td>
                <td className="px-2 py-2">
                  <DecileMeter decile={f.decile} title="Within this market's scored funds" />
                </td>
                <td className="px-3 py-2 text-right text-table num text-ink-2">
                  {f.adv_usd_60d_median ? formatUsd(f.adv_usd_60d_median, 0) : '—'}
                </td>
                <td className="px-3 py-2 text-right text-table num text-ink-2">
                  {formatPct(f.expense_ratio, 2)}
                </td>
                <td className="px-3 py-2 text-right text-table num text-ink-2">
                  {f.aum_usd ? formatUsd(f.aum_usd, 0) : '—'}
                </td>
                {SHOWN.map((w, i) => (
                  <RsCell key={w} value={f.rs[w]} first={i === 0} />
                ))}
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
