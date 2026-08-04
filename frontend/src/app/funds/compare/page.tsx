// /funds/compare — equal-weighted category composite vs benchmarks. Everything the reader
// needs in order to distrust the numbers appropriately is on the page: the fund count, the
// last NAV date, the price-return mismatch and the survivorship bias.
export const revalidate = 3600

import { Suspense } from 'react'
import { PrintButton } from '@/components/maal/PrintButton'
import { CategoryCompareControls } from '@/components/funds/CategoryCompareControls'
import { CategoryCompareChart } from '@/components/funds/CategoryCompareChart'
import { CategorySummaryTable } from '@/components/funds/CategorySummaryTable'
import {
  ConstituentsTable, ReturnsTable, RollingStatsTable,
} from '@/components/funds/CategoryCompareTables'
import { fetchStart, minusMonths, thinCoverage } from '@/lib/fundCategoryCurve'
import {
  CATEGORY_INDEX, getCategoryComposite, getCategoryConstituents, getCategoryOptions,
  getCategorySummary,
} from '@/lib/queries/fund_category_curve'

const PERIOD_MONTHS: Record<string, number | null> = {
  '1m': 1, '3m': 3, '6m': 6, '1y': 12, '2y': 24, '3y': 36, '5y': 60, max: null,
}

const WINDOW_YEARS: Record<string, number> = { '1y': 1, '3y': 3, '5y': 5 }

const cleanCat = (c: string): string =>
  c.replace(/^India\s+Fund\s*[-–—]?\s*/i, '').trim() || c

export default async function ComparePage({
  searchParams,
}: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const sp = await searchParams
  const one = (k: string): string | undefined =>
    Array.isArray(sp[k]) ? (sp[k] as string[])[0] : (sp[k] as string | undefined)

  const options = await getCategoryOptions()
  if (options.length === 0) {
    return (
      <main className="report-page report-wide mx-auto max-w-[1180px] px-6 py-8">
        <p className="font-sans text-[14px] text-txt-2">No fund categories carry NAV history.</p>
      </main>
    )
  }

  // Freshness is judged against the freshest category we hold, not against today's clock —
  // the whole pipeline lags the market, and a page that called every category stale on a
  // quiet weekend would cry wolf. A category more than a month behind the leader is broken.
  const freshest = options.reduce<string>((a, o) => (o.lastNav && o.lastNav > a ? o.lastNav : a), '')
  const staleBefore = minusMonths(freshest, 1)

  const chosen = options.find((o) => o.category === one('cat'))
    ?? options.find((o) => o.category === 'India Fund Flexi Cap')
    ?? options[0]

  // Validate against the known keys rather than trusting the param: PERIOD_MONTHS[unknown]
  // is undefined, and `undefined == null` would silently mean "max" — a junk query string
  // would quietly render twenty years of history instead of the default window.
  const requestedPeriod = one('period') ?? '3y'
  const period = requestedPeriod === 'custom' || requestedPeriod in PERIOD_MONTHS
    ? requestedPeriod
    : '3y'
  const view = one('view') === 'rolling' ? 'rolling' : 'growth'
  const windowYears = WINDOW_YEARS[one('window') ?? '3y'] ?? 3

  const anchorTo = chosen.lastNav ?? freshest
  const months = PERIOD_MONTHS[period]
  const to = period === 'custom' ? (one('to') || anchorTo) : anchorTo
  const from = period === 'custom'
    ? (one('from') || minusMonths(to, 36))
    : months == null ? '1990-01-01' : minusMonths(to, months)

  // The summary board is anchored on the data's own last date, independent of the period the
  // reader picked — it is a fixed 1/3/5-year scan of every category, not a view of this one.
  const sumAnchors = {
    to: anchorTo,
    y1: minusMonths(anchorTo, 12),
    y3: minusMonths(anchorTo, 36),
    y5: minusMonths(anchorTo, 60),
  }
  const dayCount = (a: string) =>
    Math.round((Date.parse(anchorTo) - Date.parse(a)) / 86400000)

  // fetchStart reaches back a full rolling window before the displayed period, or a rolling
  // chart as long as its own period has nothing to plot. `shown` is what the growth chart and
  // the returns table use; the rolling views use the full series.
  const [rows, funds, summary] = await Promise.all([
    getCategoryComposite(chosen.category, fetchStart(from, windowYears), to),
    getCategoryConstituents(chosen.category, from, to),
    getCategorySummary(sumAnchors),
  ])
  const shown = rows.filter((r) => r.d >= from)

  const label = cleanCat(chosen.category)
  const indexLabel = CATEGORY_INDEX[chosen.category] ?? 'NIFTY 500'
  const stale = chosen.lastNav != null && chosen.lastNav < staleBefore
  // Coverage is stated in words, not charted: plotted against a 0–90 axis the holiday dips
  // (one scheme reporting) look like the category collapsed to zero, which is what a reader
  // actually took from the strip that used to sit here.
  const thin = thinCoverage(shown)
  const coverage = { first: shown.find((r) => r.n > 0)?.n ?? 0, peak: thin.peak }

  return (
    <main className="report-page report-wide mx-auto max-w-[1180px] px-6 py-8">
      <header className="mb-6">
        <p className="font-num text-[9px] uppercase tracking-[0.14em] text-txt-3">
          Funds · Category vs benchmark
        </p>
        <div className="flex flex-wrap items-baseline justify-between gap-3">
          <h1 className="font-display text-[26px] font-medium tracking-tight text-txt-1">
            {label} — equal-weighted composite
          </h1>
          <div className="print:hidden"><PrintButton /></div>
        </div>
        <p className="mt-1 font-sans text-[13px] text-txt-2">
          {funds.length} of {chosen.nFunds} funds with NAV history contributed over{' '}
          {from} → {to}. Composite as of {rows.at(-1)?.d ?? '—'}.
        </p>
        {stale && (
          <p className="mt-2 rounded-tile border border-sig-neg/40 bg-sig-neg/10 px-3 py-2 font-sans text-[12px] text-txt-1">
            This category&apos;s NAV feed stopped on {chosen.lastNav}, while other categories run to{' '}
            {freshest}. The curve below ends there and is not current.
          </p>
        )}
        <p className="mt-2 font-sans text-[12px] text-txt-3">
          Coverage over the window ran {coverage.first}–{coverage.peak} funds.
          {thin.days > 0 && thin.worst && (
            <> On {thin.days} of {shown.length - 1} days fewer than half the category reported a NAV
            (worst: {thin.worst.n} on {thin.worst.d}) — mostly weekends and holidays where a few
            schemes still stamp one. The composite averages whoever reported, so treat single-day
            moves on those dates as noise rather than a collapse in the category.</>
          )}
        </p>
      </header>

      <div className="mb-6">
        <Suspense fallback={null}>
          <CategoryCompareControls options={options} staleBefore={staleBefore} />
        </Suspense>
      </div>

      <div className="mb-6">
        <CategorySummaryTable
          rows={summary}
          days={{ y1: dayCount(sumAnchors.y1), y3: dayCount(sumAnchors.y3), y5: dayCount(sumAnchors.y5) }}
          activeCategory={chosen.category}
        />
      </div>

      {shown.length < 2 ? (
        <p className="font-sans text-[14px] text-txt-2">
          No NAV data for {label} between {from} and {to}.
        </p>
      ) : (
        <div className="flex flex-col gap-6">
          <CategoryCompareChart rows={rows} shown={shown} view={view} windowYears={windowYears}
                                categoryLabel={label} indexLabel={indexLabel} />
          <ReturnsTable rows={shown} categoryLabel={label} indexLabel={indexLabel} />
          <RollingStatsTable rows={rows} shown={shown} windowYears={windowYears}
                             categoryLabel={label} indexLabel={indexLabel} />
          <ConstituentsTable funds={funds} rows={shown} from={from} to={to}
                             categoryLabel={label} indexLabel={indexLabel} />
        </div>
      )}

      <footer className="mt-8 border-t border-edge-hair pt-4 font-sans text-[11px] leading-relaxed text-txt-3">
        <p className="mb-1.5">
          <strong className="text-txt-2">Sources.</strong> Fund NAVs from
          atlas_foundation.de_mf_nav_daily (AMFI / Morningstar). Index levels from
          atlas_foundation.index_prices (NSE). Composite computed as a chain-linked
          equal-weighted daily return series.
        </p>
        <p className="mb-1.5">
          <strong className="text-txt-2">Benchmarks exclude dividends.</strong> Every index here is
          price-return; fund NAVs are total-return. The composite is therefore flattered by roughly
          1–1.5% a year against these benchmarks.
        </p>
        <p>
          <strong className="text-txt-2">Survivorship bias.</strong> Our fund master carries live
          funds only — schemes that closed or merged are absent from the source data entirely. The
          composite therefore omits the losers that disappeared and reads better than the category
          truly performed.
        </p>
      </footer>
    </main>
  )
}
