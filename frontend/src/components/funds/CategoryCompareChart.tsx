// Growth and rolling chart modes for /funds/compare.
//
// `rows` reaches back a full rolling window before `shown` so the rolling view has history to
// work with; the growth view plots `shown` alone, which is the period the reader asked for.
import { AtlasLightweightChart, type ChartSeries } from '@/components/charts/AtlasLightweightChart'
import { Panel } from '@/components/ui/Panel'
import { rebase, rollingReturns, type CurvePoint } from '@/lib/fundCategoryCurve'
import type { CompositeRow } from '@/lib/queries/fund_category_curve'

const pick = (rows: CompositeRow[], key: 'nifty50' | 'nifty500' | 'catIndex'): CurvePoint[] =>
  rows.filter((r) => r[key] != null).map((r) => ({ d: r.d, v: r[key] as number }))

const toChart = (pts: CurvePoint[]) => pts.map((p) => ({ time: p.d, value: p.v }))

export function CategoryCompareChart({
  rows, shown, view, windowYears, categoryLabel, indexLabel,
}: {
  /** Full series, reaching back a rolling window before `shown`. */
  rows: CompositeRow[]
  /** The displayed period only. */
  shown: CompositeRow[]
  view: 'growth' | 'rolling'
  windowYears: number
  categoryLabel: string
  indexLabel: string
}) {
  // Rolling returns are computed over the full series, then trimmed to the displayed period —
  // the extra history is there to give the earliest displayed dates a window, not to be plotted.
  const from = shown[0]?.d ?? ''
  const trim = (pts: CurvePoint[]) => pts.filter((p) => p.d >= from)
  const rollOf = (pts: CurvePoint[]) => toChart(trim(rollingReturns(pts, windowYears)))

  const series: ChartSeries[] = view === 'rolling'
    ? [
        { name: `${categoryLabel} rolling ${windowYears}Y`,
          data: rollOf(rows.map((r) => ({ d: r.d, v: r.v }))), color: 'teal', lineWidth: 2 },
        { name: `${indexLabel} rolling ${windowYears}Y`,
          data: rollOf(rebase(pick(rows, 'catIndex'))), color: 'warn', lineWidth: 2 },
        { name: 'Zero', data: rollOf(rows.map((r) => ({ d: r.d, v: r.v }))).map((p) => ({ time: p.time, value: 0 })),
          color: 'ink', lineWidth: 1 },
      ]
    : [
        { name: `${categoryLabel} composite`,
          data: toChart(rebase(shown.map((r) => ({ d: r.d, v: r.v })))), color: 'teal', lineWidth: 2 },
        { name: indexLabel, data: toChart(rebase(pick(shown, 'catIndex'))), color: 'warn', lineWidth: 1 },
        { name: 'Nifty 500', data: toChart(rebase(pick(shown, 'nifty500'))), color: 'pos', lineWidth: 1 },
        { name: 'Nifty 50', data: toChart(rebase(pick(shown, 'nifty50'))), color: 'ink', lineWidth: 1 },
      ]

  return (
    <Panel
      eyebrow={view === 'rolling' ? `Rolling ${windowYears}-year returns` : 'Growth of ₹100'}
      title={view === 'rolling'
        ? `${categoryLabel} rolling returns vs ${indexLabel}`
        : `${categoryLabel} equal-weighted composite vs benchmarks`}
      info={{
        title: 'How this curve is built',
        body: (
          <>Each day we average the daily return of every fund in the category that reported a NAV
          on both that day and the previous one, then compound those averages. Funds entering or
          leaving the category do not step the curve. Benchmarks are price-return indices and
          exclude dividends, so the composite is flattered by roughly 1–1.5% a year.</>
        ),
      }}
      bodyClassName="break-inside-avoid"
    >
      <AtlasLightweightChart
        series={series}
        height={360}
        yLabel={view === 'rolling' ? 'Return %' : 'Index (start = 100)'}
        precision={1}
      />
    </Panel>
  )
}
