'use client'
// src/components/themes/ThemeFundTable.tsx — every fund carrying one theme, ranked against each
// other. This is the FM's question: given that I want AI, or uranium, or water — which fund?
//
// THE RANK IS CUT INSIDE THE THEME. A fund's decile on /etfs is its standing in its global peer
// group; "#1 in Water" and "#1 fund" are different sentences. The decile column appears only where
// the theme has enough scored members to be cut into ten (the FM's `peer_group_min_members`); the
// rank is exact at any size and is always shown.
//
// The three lens columns are there because "which fund" is rarely one number: two AI funds an
// inch apart on composite can be a cheap liquid one and an expensive concentrated one, and cost &
// liquidity is the column that says so.
import Link from 'next/link'
import { AddToDraft } from '@/components/portfolios/AddToDraft'
import { useRouter } from 'next/navigation'
import { RsCell } from '@/components/countries/RsCell'
import { DecileMeter } from '@/components/ui/DecileMeter'
import { formatPct, formatUsd } from '@/lib/format'
import { THEME_WINDOWS, type ThemeFund, type ThemeWindow } from '@/lib/themes'
import { decileColour } from '@/lib/scores'
import { whyNotOffered } from '@/lib/universe'

const LABEL: Record<ThemeWindow, string> = { '3m': '3M', '6m': '6M', '12m': '1Y' }

const ROLE: Record<string, string> = {
  pure_play: 'pure play',
  picks_and_shovels: 'picks & shovels',
  diversified: 'diversified',
  not_applicable: '',
}

/** Why this fund is not in the ranking, in the producer's own words. Not a judgement on the fund
 *  — its composite is right there beside it — but on whether the FM's rules offer it. */
function flags(f: ThemeFund): string | null {
  const on = [whyNotOffered(f.exclusion_reason), f.hedged ? 'hedged' : null]
  const set = on.filter((x): x is string => typeof x === 'string' && x.length > 0)
  return set.length ? set.join(' · ') : null
}

const lens = (v: string | null) => (v == null ? '—' : Number(v).toFixed(0))

export function ThemeFundTable({ funds, showDecile }: { funds: ThemeFund[]; showDecile: boolean }) {
  const router = useRouter()
  if (funds.length === 0) return <p className="text-body text-ink-2">No fund carries this theme.</p>
  const th = 'bg-raised px-3 py-1.5 text-meta font-semibold uppercase tracking-[0.1em] text-ink-3'
  return (
    <div className="dt panel">
      <table className="w-full border-collapse">
        <thead>
          <tr className="border-b border-rule">
            <th className={`${th} text-right`}>#</th>
            <th className={`${th} text-left`}>Fund</th>
            <th className={`${th} border-l border-rule text-right`}>Score</th>
            {showDecile && <th className={`${th} text-left`}>Decile</th>}
            <th className={`${th} text-right`} title="Trend, relative strength and structure">Technical</th>
            <th className={`${th} text-right`} title="Volatility, drawdown, downside deviation, beta">Risk</th>
            <th className={`${th} text-right`} title="Expense, liquidity, size, concentration">Cost &amp; liq.</th>
            <th className={`${th} border-l border-rule text-right`}>ADV $</th>
            <th className={`${th} text-right`}>Expense</th>
            <th className={`${th} text-right`}>AUM</th>
            {THEME_WINDOWS.map((w, i) => (
              <th key={w} className={`${th} text-right ${i === 0 ? 'border-l border-rule' : ''}`}>
                {LABEL[w]} vs SPY
              </th>
            ))}
            <th className={`${th} text-center`} title="Add to a draft basket">+</th>
          </tr>
        </thead>
        <tbody>
          {funds.map((f) => {
            const href = `/etfs/${encodeURIComponent(f.symbol)}`
            const composite = f.composite == null ? null : Number(f.composite)
            const excluded = flags(f)
            const role = f.role_id ? ROLE[f.role_id] : ''
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
                  <span className="ml-2 text-meta text-ink-3">{f.name}</span>
                  {role && <span className="ml-2 text-meta text-ink-2">{role}</span>}
                  {excluded && <span className="ml-2 text-meta text-neg">{excluded}</span>}
                </td>
                <td className="border-l border-rule px-3 py-2 text-right text-table num">
                  {composite == null ? (
                    <span className="text-ink-3">—</span>
                  ) : (
                    <span className="font-semibold" style={{ color: decileColour(f.decile) ?? 'var(--color-ink)' }}>
                      {composite.toFixed(0)}
                    </span>
                  )}
                </td>
                {showDecile && (
                  <td className="px-2 py-2">
                    <DecileMeter decile={f.decile} title="Within this theme's buyable funds" />
                  </td>
                )}
                <td className="px-3 py-2 text-right text-table num text-ink-2">{lens(f.technical)}</td>
                <td className="px-3 py-2 text-right text-table num text-ink-2">{lens(f.risk)}</td>
                <td className="px-3 py-2 text-right text-table num text-ink-2">{lens(f.cost_liquidity)}</td>
                <td className="border-l border-rule px-3 py-2 text-right text-table num text-ink-2">
                  {f.adv_usd_60d_median ? formatUsd(f.adv_usd_60d_median, 0) : '—'}
                </td>
                <td className="px-3 py-2 text-right text-table num text-ink-2">{formatPct(f.expense_ratio, 2)}</td>
                <td className="px-3 py-2 text-right text-table num text-ink-2">
                  {f.aum_usd ? formatUsd(f.aum_usd, 0) : '—'}
                </td>
                {THEME_WINDOWS.map((w, i) => (
                  <RsCell key={w} value={f.rs[w]} first={i === 0} />
                ))}
                <td className="px-2 py-2 text-center">
                  <AddToDraft kind="etf" symbol={f.symbol} />
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
