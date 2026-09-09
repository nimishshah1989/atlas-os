// src/components/themes/ThemeView.tsx — one theme: how its funds are doing as a group, and which
// one to own. A theme has no price of its own, so every figure here is a statement about its
// MEMBERS, and the page says which member and how many.
import { StatCard } from '@/components/ui/StatCard'
import { EodStamp } from '@/components/ui/EodStamp'
import { PageHeader } from '@/components/ui/PageHeader'
import { Section } from '@/components/ui/Section'
import { RsCell } from '@/components/countries/RsCell'
import { formatPct, formatUsd } from '@/lib/format'
import { THEME_WINDOWS, type ThemeDetail, type ThemeWindow } from '@/lib/themes'
import { decileColour } from '@/lib/scores'
import { ThemeFundTable } from './ThemeFundTable'

const WINDOW_LABEL: Record<ThemeWindow, string> = { '3m': '3 months', '6m': '6 months', '12m': '1 year' }

export function ThemeView({ detail, minMembers }: { detail: ThemeDetail; minMembers: number }) {
  const { row, funds, date } = detail
  const median = row.median_composite == null ? null : Number(row.median_composite)
  const top = row.top_composite == null ? null : Number(row.top_composite)
  const showDecile = row.n_scored >= minMembers

  return (
    <div className="page">
      <PageHeader
        title={row.name}
        lead={
          row.n_scored === 0
            ? 'No fund carrying this theme is scored yet — all are geared, hedged or below the liquidity floor.'
            : `${row.n_scored} of ${row.n_funds} funds carrying this theme are scored, and ranked against each other below.`
        }
        aside={<EodStamp eod={date} asOf={date} />}
      />

      <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
        <StatCard
          label="Median score"
          value={median == null ? '—' : median.toFixed(0)}
          sub={`over ${row.n_scored} scored ${row.n_scored === 1 ? 'fund' : 'funds'}`}
        />
        <StatCard
          label="Above 200-day"
          value={row.above_ema200_frac == null ? '—' : formatPct(row.above_ema200_frac, 0)}
          sub="members trading above their own EMA-200"
        />
        <StatCard label="Funds" value={row.n_funds} sub={row.sector_name ?? 'unparented'} />
        <StatCard
          label="AUM"
          value={row.aum_usd ? formatUsd(row.aum_usd, 0) : '—'}
          sub="across every member with a reported figure"
        />
        <StatCard
          label="The one to own"
          value={row.top_symbol ?? '—'}
          colour={decileColour(row.top_decile)}
          href={row.top_symbol ? `/etfs/${encodeURIComponent(row.top_symbol)}` : undefined}
          sub={top == null ? 'nothing scored yet' : `${row.top_name} · ${top.toFixed(0)}`}
        />
      </div>

      <Section title="Against the S&P 500" note="median member, (1+r)/(1+r SPY) − 1">
        <div className="dt panel">
          <table className="w-full border-collapse">
            <thead>
              <tr className="border-b border-rule">
                {THEME_WINDOWS.map((w) => (
                  <th key={w} className="bg-raised px-3 py-1.5 text-right text-meta font-semibold uppercase tracking-[0.1em] text-ink-3">
                    {WINDOW_LABEL[w]}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              <tr>
                {THEME_WINDOWS.map((w) => (
                  <RsCell key={w} value={row.rs[w]} />
                ))}
              </tr>
            </tbody>
          </table>
        </div>
      </Section>

      <Section
        title="Which fund to own"
        note={
          showDecile
            ? `ranked and decile-cut across the ${row.n_scored} scored members`
            : `ranked across ${row.n_scored} scored ${row.n_scored === 1 ? 'member' : 'members'} — too few for a decile (the FM's floor is ${minMembers})`
        }
      >
        <ThemeFundTable funds={funds} showDecile={showDecile} />
      </Section>
    </div>
  )
}
