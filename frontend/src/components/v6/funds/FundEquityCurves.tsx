// FundEquityCurves — the fund's ~5-year performance, two reads side by side:
//   • Growth of ₹100 — fund NAV vs Nifty 50 and Nifty 500, all rebased to 100.
//   • Relative strength — fund ÷ benchmark × 100; above 100 = outperforming, the dotted
//     parity line marks 100. Same two baselines the /funds RS matrix uses.
// Server component: fetches month-end series, rebases via the tested pure builder, renders
// two AtlasLightweightChart panels. All REAL (de_mf_nav_daily + index_prices).
import { getFundEquityCurve } from '@/lib/queries/v6/fund_lens'
import { buildFundCurves } from '@/lib/v6/fundEquityCurve'
import { AtlasLightweightChart, type ChartSeries } from '@/components/charts/AtlasLightweightChart'

function Legend({ items }: { items: { label: string; cls: string }[] }) {
  return (
    <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1">
      {items.map((i) => (
        <span key={i.label} className="flex items-center gap-1.5 font-sans text-[11px] text-txt-2">
          <span className={`inline-block h-[3px] w-4 rounded-full ${i.cls}`} />
          {i.label}
        </span>
      ))}
    </div>
  )
}

const pct = (v: number) => `${v >= 0 ? '+' : '−'}${Math.abs(v).toFixed(0)}%`

export async function FundEquityCurves({ mstarId }: { mstarId: string }) {
  const points = await getFundEquityCurve(mstarId).catch(() => [])
  const { equity, rs } = buildFundCurves(points)
  if (equity.length < 6) return null // need a meaningful span to bother charting

  const asOf = equity.at(-1)!.d
  const first = equity[0].d
  const years = (new Date(asOf).getTime() - new Date(first).getTime()) / (365.25 * 24 * 3600 * 1000)

  const ePts = (key: 'fund' | 'nifty50' | 'nifty500') =>
    equity.filter((r) => r[key] != null).map((r) => ({ time: r.d, value: r[key] as number }))
  const equitySeries: ChartSeries[] = [
    { name: 'Fund', data: ePts('fund'), color: 'teal', lineWidth: 2 },
    { name: 'Nifty 500', data: ePts('nifty500'), color: 'warn', lineWidth: 1 },
    { name: 'Nifty 50', data: ePts('nifty50'), color: 'ink', lineWidth: 1 },
  ]

  const rPts = (key: 'vsNifty50' | 'vsNifty500') =>
    rs.filter((r) => r[key] != null).map((r) => ({ time: r.d, value: r[key] as number }))
  const rsSeries: ChartSeries[] = [
    { name: 'Parity (100)', data: rs.map((r) => ({ time: r.d, value: 100 })), color: 'ink', lineWidth: 1 },
    { name: 'RS vs Nifty 50', data: rPts('vsNifty50'), color: 'teal', lineWidth: 2 },
    { name: 'RS vs Nifty 500', data: rPts('vsNifty500'), color: 'warn', lineWidth: 2 },
  ]

  // headline read (rebased values are growth-of-100, so last − 100 = total return %)
  const eLast = equity.at(-1)!
  const rLast = rs.at(-1)!
  const fundRet = (eLast.fund ?? 100) - 100
  const n50Ret = (eLast.nifty50 ?? 100) - 100
  const n500Ret = (eLast.nifty500 ?? 100) - 100

  return (
    <section aria-label="Performance vs benchmarks">
      <div className="mb-3">
        <p className="font-num text-[9px] uppercase tracking-[0.14em] text-txt-3">Performance · {years.toFixed(1)}y</p>
        <h2 className="font-display text-[22px] font-medium tracking-tight text-txt-1">Growth &amp; relative strength vs the market</h2>
        <p className="mt-1 max-w-[820px] font-sans text-[13px] text-txt-2">
          Over the last {years.toFixed(1)} years ₹100 in the fund grew to{' '}
          <strong className="text-txt-1">₹{(eLast.fund ?? 100).toFixed(0)}</strong> ({pct(fundRet)}), vs{' '}
          <strong className="text-txt-1">₹{(eLast.nifty500 ?? 100).toFixed(0)}</strong> for Nifty 500 ({pct(n500Ret)}) and{' '}
          <strong className="text-txt-1">₹{(eLast.nifty50 ?? 100).toFixed(0)}</strong> for Nifty 50 ({pct(n50Ret)}). Its
          relative-strength line ended at <strong className="text-txt-1">{rLast.vsNifty50?.toFixed(0)}</strong> vs Nifty 50
          and <strong className="text-txt-1">{rLast.vsNifty500?.toFixed(0)}</strong> vs Nifty 500 —{' '}
          {(rLast.vsNifty50 ?? 100) >= 100 ? 'above 100, sustained outperformance' : 'below 100, lagging the market'}.
        </p>
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        <div>
          <AtlasLightweightChart
            series={equitySeries}
            height={300}
            title="Growth of ₹100"
            yLabel="Fund NAV vs Nifty 50 / 500 · rebased to 100"
            asOf={asOf}
            precision={0}
          />
          <Legend
            items={[
              { label: 'Fund', cls: 'bg-brand' },
              { label: 'Nifty 500', cls: 'bg-sig-warn' },
              { label: 'Nifty 50', cls: 'bg-txt-3' },
            ]}
          />
        </div>
        <div>
          <AtlasLightweightChart
            series={rsSeries}
            height={300}
            title="Relative strength"
            yLabel="Fund ÷ benchmark × 100 · above 100 = outperforming"
            asOf={asOf}
            precision={0}
          />
          <Legend
            items={[
              { label: 'vs Nifty 50', cls: 'bg-brand' },
              { label: 'vs Nifty 500', cls: 'bg-sig-warn' },
              { label: 'Parity = 100', cls: 'bg-txt-3' },
            ]}
          />
        </div>
      </div>
    </section>
  )
}
