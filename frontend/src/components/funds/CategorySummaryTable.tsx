// The all-categories board: every category's composite against its own benchmark over
// 1/3/5 years, each name a link into that category's deep dive. Sorted by 1-year excess,
// so the categories beating their benchmark sit at the top.
import { Fragment } from 'react'
import Link from 'next/link'
import { Panel } from '@/components/ui/Panel'
import { growthReturn, type SpanReturn } from '@/lib/fundCategoryCurve'
import type { CategorySummaryRow } from '@/lib/queries/fund_category_curve'

const PERIODS = [
  { key: 'y1' as const, label: '1Y' },
  { key: 'y3' as const, label: '3Y' },
  { key: 'y5' as const, label: '5Y' },
]

const pct = (v: number | null | undefined): string =>
  v == null ? '—' : `${v >= 0 ? '+' : '−'}${Math.abs(v).toFixed(2)}%`

const tone = (v: number | null | undefined): string =>
  v == null ? 'text-txt-3' : v >= 0 ? 'text-sig-pos' : 'text-sig-neg'

const num = 'px-2.5 py-1.5 text-right font-num text-[12px] tabular-nums'
const head = 'px-2.5 py-1.5 font-num text-[9px] uppercase tracking-[0.14em] text-txt-3'

const cleanCat = (c: string): string =>
  c.replace(/^India\s+Fund\s*[-–—]?\s*/i, '').trim() || c

/** Excess is only meaningful when both legs cover the same span. */
const excess = (a: SpanReturn | null, b: SpanReturn | null): number | null =>
  a == null || b == null ? null : a.pct - b.pct

export function CategorySummaryTable({
  rows, days, activeCategory,
}: {
  rows: CategorySummaryRow[]
  /** Actual day count per period, so the CAGR gate uses real spans. */
  days: { y1: number; y3: number; y5: number }
  activeCategory: string
}) {
  const computed = rows.map((r) => {
    const comp = { y1: growthReturn(r.comp.y1, days.y1), y3: growthReturn(r.comp.y3, days.y3), y5: growthReturn(r.comp.y5, days.y5) }
    const bench = { y1: growthReturn(r.bench.y1, days.y1), y3: growthReturn(r.bench.y3, days.y3), y5: growthReturn(r.bench.y5, days.y5) }
    return { ...r, comp, bench }
  }).sort((a, b) => (excess(b.comp.y1, b.bench.y1) ?? -Infinity) - (excess(a.comp.y1, a.bench.y1) ?? -Infinity))

  return (
    <Panel
      eyebrow="All categories"
      title="Category vs its own benchmark — 1Y / 3Y / 5Y"
      info={{
        title: 'Reading this table',
        body: (
          <>Each category&apos;s equal-weighted composite against the index it is measured on, so
          the comparison differs row to row — Small-Cap against NIFTY SMLCAP 250, Large-Cap
          against NIFTY 100. Excess is the composite minus that benchmark. Beyond one year the
          figures are CAGR on actual day count. A dash means the category is younger than the
          period; nothing is filled in from a shorter span.</>
        ),
      }}
      bodyClassName="overflow-x-auto break-inside-avoid p-0"
    >
      <table className="w-full border-collapse">
        <thead className="border-b border-edge-rule">
          <tr>
            <th className={`${head} text-left`}>Category</th>
            <th className={`${head} text-left`}>Benchmark</th>
            {PERIODS.map((p) => (
              <th key={p.key} className={`${head} text-right`} colSpan={3}>{p.label}</th>
            ))}
          </tr>
          <tr>
            <th className={head} />
            <th className={head} />
            {PERIODS.map((p) => (
              <Fragment key={p.key}>
                <th className={`${head} text-right font-normal`}>cat</th>
                <th className={`${head} text-right font-normal`}>bmk</th>
                <th className={`${head} text-right font-normal`}>+/−</th>
              </Fragment>
            ))}
          </tr>
        </thead>
        <tbody>
          {computed.map((r) => (
            <tr key={r.category}
                className={`border-b border-edge-hair last:border-0 ${
                  r.category === activeCategory ? 'bg-surface-raised' : ''}`}>
              <td className="px-2.5 py-1.5 text-left font-sans text-[12px]">
                <Link href={`/funds/compare?cat=${encodeURIComponent(r.category)}`}
                      className="text-txt-1 no-underline hover:text-brand">
                  {cleanCat(r.category)}
                </Link>
              </td>
              <td className="px-2.5 py-1.5 text-left font-num text-[11px] text-txt-3">{r.indexCode}</td>
              {PERIODS.map((p) => {
                const c = r.comp[p.key]
                const b = r.bench[p.key]
                const x = excess(c, b)
                return (
                  <Fragment key={p.key}>
                    <td className={`${num} ${tone(c?.pct)}`}>{pct(c?.pct)}</td>
                    <td className={`${num} text-txt-2`}>{pct(b?.pct)}</td>
                    <td className={`${num} ${tone(x)} font-semibold`}>{pct(x)}</td>
                  </Fragment>
                )
              })}
            </tr>
          ))}
        </tbody>
      </table>
      <p className="px-2.5 py-2 font-sans text-[11px] text-txt-3">
        Absolute return at one year; CAGR on actual day count beyond it. Benchmarks are
        price-return and exclude dividends, so the excess column flatters the composite by
        roughly 1–1.5% a year. Click a category to open its deep dive.
      </p>
    </Panel>
  )
}
