// Growth and rolling chart modes for /funds/compare, plus a strip showing how many funds
// were in the composite on each date — a curve built from three funds should not look like
// one built from ninety.
import { AtlasLightweightChart, type ChartSeries } from '@/components/charts/AtlasLightweightChart'
import { Panel } from '@/components/ui/Panel'
import { rebase, rollingReturns, type CurvePoint } from '@/lib/fundCategoryCurve'
import type { CompositeRow } from '@/lib/queries/fund_category_curve'

const pick = (rows: CompositeRow[], key: 'nifty50' | 'nifty500' | 'catIndex'): CurvePoint[] =>
  rows.filter((r) => r[key] != null).map((r) => ({ d: r.d, v: r[key] as number }))

const toChart = (pts: CurvePoint[]) => pts.map((p) => ({ time: p.d, value: p.v }))

export function CategoryCompareChart({
  rows, view, windowYears, categoryLabel, indexLabel,
}: {
  rows: CompositeRow[]
  view: 'growth' | 'rolling'
  windowYears: number
  categoryLabel: string
  indexLabel: string
}) {
  const composite: CurvePoint[] = rows.map((r) => ({ d: r.d, v: r.v }))
  const catIdx = pick(rows, 'catIndex')

  const series: ChartSeries[] = view === 'rolling'
    ? [
        { name: `${categoryLabel} rolling ${windowYears}Y`,
          data: toChart(rollingReturns(composite, windowYears)), color: 'teal', lineWidth: 2 },
        { name: `${indexLabel} rolling ${windowYears}Y`,
          data: toChart(rollingReturns(rebase(catIdx), windowYears)), color: 'warn', lineWidth: 2 },
      ]
    : [
        { name: `${categoryLabel} composite`, data: toChart(composite), color: 'teal', lineWidth: 2 },
        { name: indexLabel, data: toChart(rebase(catIdx)), color: 'warn', lineWidth: 1 },
        { name: 'Nifty 500', data: toChart(rebase(pick(rows, 'nifty500'))), color: 'pos', lineWidth: 1 },
        { name: 'Nifty 50', data: toChart(rebase(pick(rows, 'nifty50'))), color: 'ink', lineWidth: 1 },
      ]

  const counts: ChartSeries[] = [{
    name: 'Funds in composite',
    data: rows.slice(1).map((r) => ({ time: r.d, value: r.n })),
    color: 'ink',
    lineWidth: 1,
  }]

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
      <div className="mt-3 border-t border-edge-hair pt-3">
        <p className="mb-1 font-num text-[9px] uppercase tracking-[0.14em] text-txt-3">
          Funds in the composite
        </p>
        <AtlasLightweightChart series={counts} height={72} precision={0} compact />
      </div>
    </Panel>
  )
}
