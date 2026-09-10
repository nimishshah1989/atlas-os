// src/components/themes/ThemeView.tsx — one theme: how its funds are doing as a group, and which
// one to own. A theme has no price of its own, so every figure here is a statement about its
// MEMBERS, and the page says which member and how many.
import { StatCard } from '@/components/ui/StatCard'
import { EodStamp } from '@/components/ui/EodStamp'
import Link from 'next/link'
import { PageHeader } from '@/components/ui/PageHeader'
import { Section } from '@/components/ui/Section'
import { RsCell } from '@/components/countries/RsCell'
import { formatIsoDate, formatPct, formatUsd } from '@/lib/format'
import { InfoTip } from '@/components/ui/InfoTip'
import { MedianMemberTrend } from '@/components/shared/MedianMemberTrend'
import { THEME_WINDOWS, type ThemeDetail, type ThemeWindow } from '@/lib/themes'
import { decileColour } from '@/lib/scores'
import { BuildBasketLink, SEED_LIMIT } from '@/components/portfolios/BuildBasketLink'
import { ThemeFundTable } from './ThemeFundTable'

const WINDOW_LABEL: Record<ThemeWindow, string> = { '3m': '3 months', '6m': '6 months', '12m': '1 year' }

export function ThemeView({ detail, minMembers }: { detail: ThemeDetail; minMembers: number }) {
  const { row, funds, date, history } = detail
  const median = row.median_composite == null ? null : Number(row.median_composite)
  const top = row.top_composite == null ? null : Number(row.top_composite)
  const showDecile = row.n_offered >= minMembers
  // Rank order, and only what carries a rank: an unranked fund is one the FM's universe rules do
  // not offer — geared, inverse, or below his floor — so seeding one into a basket would propose
  // buying something the board deliberately keeps out.
  const ranked = funds.filter((f) => f.rank != null).map((f) => f.symbol)

  return (
    <div className="page">
      {/* Up one level. A drill-down that only goes down makes the reader use the back button to
          compare two themes in one sector, which is the cognitive load the board exists to remove. */}
      {row.sector_id && row.sector_name && (
        <nav className="mb-2 text-meta text-ink-3" aria-label="Breadcrumb">
          <Link href="/sectors" className="hover:underline">
            Sectors
          </Link>
          <span className="px-1.5">/</span>
          <Link href={`/sectors/${encodeURIComponent(row.sector_id)}`} className="hover:underline">
            {row.sector_name}
          </Link>
        </nav>
      )}
      <PageHeader
        title={row.name}
        lead={
          row.n_offered === 0
            ? 'No fund carrying this theme is one you can buy — every one is geared, inverse or below your liquidity floor.'
            : `${row.n_offered} of the ${row.n_funds} funds carrying this theme are ones you can buy, and are ranked against each other below. The score is over the ${row.n_comparable} whose grades are comparable.`
        }
        aside={<EodStamp eod={date} asOf={date} />}
      />

      <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
        <StatCard
          label="Median score"
          value={median == null ? '—' : median.toFixed(0)}
          sub={`median of ${row.n_comparable} comparable ${row.n_comparable === 1 ? 'fund' : 'funds'}`}
        />
        <StatCard
          label="Above 200-day"
          value={row.above_ema200_frac == null ? '—' : formatPct(row.above_ema200_frac, 0)}
          sub={`of those ${row.n_comparable}, above their own EMA-200`}
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
          sub={top == null ? 'nothing buyable yet' : `${row.top_name} · ${top.toFixed(0)}`}
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

      {/* THE THEME'S OWN THREE YEARS. The FM: "we can have much better representations of sectors
          at the theme level: different visuals… line charts, historic data." The sector had this
          line and the theme did not, which is backwards — a sub-thematic call is made HERE. */}
      {history.length > 1 && (
        <Section
          title="How this theme has been doing"
          note={`since ${formatIsoDate(history[0].date)}, rebased to 100`}
        >
          <div className="panel px-3 py-3">
            <MedianMemberTrend name={row.name} points={history} />
            <p className="mt-1 text-meta text-ink-3">
              The MEDIAN member fund&apos;s total return, each rebased to its own close on the first
              session shown, against the S&amp;P over the same sessions.{' '}
              <InfoTip title="What this line leaves out">
                Membership is fixed at the start of the window, so a fund listed since is not in
                this line and one that closed is not either. Geared and inverse funds are out of it
                for the same reason they are out of the score: their line is a multiple or a
                negation of the theme, not the theme.
              </InfoTip>
            </p>
          </div>
        </Section>
      )}

      <Section
        title="Which fund to own"
        aside={
          <BuildBasketLink
            symbols={ranked}
            name={row.name}
            label={`Build a basket from the top ${Math.min(ranked.length, SEED_LIMIT)}`}
          />
        }
        note={
          showDecile
            ? `ranked and decile-cut across the ${row.n_offered} members you can buy`
            : `ranked across ${row.n_offered} ${row.n_offered === 1 ? 'member' : 'members'} you can buy — too few for a decile (your floor is ${minMembers})`
        }
      >
        <ThemeFundTable funds={funds} showDecile={showDecile} />
      </Section>
    </div>
  )
}
