// PortfolioDetailV4 — one portfolio, fully glass-box: config, live paper-track,
// backtest growth vs NIFTY 500, risk box (reusing the fund math), holdings by
// sector, and the raw trade log. Everything rendered is stored engine output.
import { notFound } from 'next/navigation'
import { getPortfolioDetail, type NavPointRow, type Holding } from '@/lib/queries/portfolios'
import { TradesTable } from './TradesTable'
import { computeFundRiskStats, sectorComposition, type NavPoint } from '@/lib/fundStats'
import { FundRiskStats } from '@/components/funds/FundRiskStats'
import { AtlasLightweightChart, type ChartSeries } from '@/components/charts/AtlasLightweightChart'
import { Panel } from '@/components/ui/Panel'

const inr = (v: number | null) =>
  v == null ? '—' : `₹${v.toLocaleString('en-IN', { maximumFractionDigits: 0 })}`
const pct = (v: number | null, signed = true) =>
  v == null ? '—' : `${signed && v > 0 ? '+' : ''}${v.toFixed(1)}%`
const retTone = (v: number | null) =>
  v == null ? 'text-txt-3' : v >= 0 ? 'text-sig-pos' : 'text-sig-neg'

// month-end sample of a daily NAV series (fundStats annualises with √12)
function monthly(points: NavPointRow[]): NavPoint[] {
  const byMonth = new Map<string, NavPointRow>()
  for (const p of points) byMonth.set(p.d.slice(0, 7), p) // ascending → last wins
  return [...byMonth.values()].map((p) => ({ d: p.d, nav: p.nav }))
}

function maxDrawdownDaily(points: NavPointRow[]): number | null {
  if (points.length < 2) return null
  let peak = points[0].nav
  let dd = 0
  for (const p of points) {
    if (p.nav > peak) peak = p.nav
    dd = Math.min(dd, p.nav / peak - 1)
  }
  return dd
}

const rebase = (pts: NavPointRow[]): { time: string; value: number }[] =>
  pts.length ? pts.map((p) => ({ time: p.d, value: (p.nav / pts[0].nav) * 100 })) : []

const totalPct = (pts: NavPointRow[]): number | null =>
  pts.length > 1 ? (pts[pts.length - 1].nav / pts[0].nav - 1) * 100 : null

const postTaxTotalPct = (pts: NavPointRow[], tax: number): number | null =>
  pts.length > 1 ? ((pts[pts.length - 1].nav - tax) / pts[0].nav - 1) * 100 : null

function Stat({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return (
    <div className="rounded-tile border border-edge-hair bg-surface-panel px-3 py-2.5">
      <div className="font-num text-[9px] uppercase tracking-wider text-txt-3">{label}</div>
      <div className={`mt-1 font-num text-[18px] font-semibold tabular-nums ${tone ?? 'text-txt-1'}`}>{value}</div>
    </div>
  )
}

function HoldingsTable({ holdings, nav }: { holdings: Holding[]; nav: number | null }) {
  if (holdings.length === 0)
    return <p className="px-5 py-4 font-sans text-[13px] italic text-txt-3">No open positions.</p>
  return (
    <table className="w-full min-w-[760px]">
      <thead>
        <tr className="border-b border-edge-rule">
          {['Instrument', 'Sector', 'Qty', 'Avg cost', 'Last', 'Value', 'Weight', 'P&L'].map((h, i) => (
            <th key={h} className={`px-3 py-2 font-num text-[10px] uppercase tracking-wider text-txt-3 ${i <= 1 ? 'text-left' : 'text-right'}`}>{h}</th>
          ))}
        </tr>
      </thead>
      <tbody>
        {holdings.map((h) => {
          const avgCost = h.qty ? h.netCost / h.qty : null
          const pnlPct = h.value != null && h.netCost ? (h.value / h.netCost - 1) * 100 : null
          return (
            <tr key={h.instrumentKey} className="border-b border-edge-hair">
              <td className="px-3 py-2">
                {h.assetClass === 'stock' ? (
                  <a href={`/stocks/${h.symbol}`} className="font-num text-[12.5px] font-semibold tabular-nums text-txt-1 no-underline hover:text-brand hover:underline">{h.symbol}</a>
                ) : (
                  <span className="font-num text-[12.5px] font-semibold tabular-nums text-txt-1">{h.symbol}</span>
                )}
                <div className="max-w-[240px] truncate font-sans text-[10.5px] text-txt-3">{h.name ?? h.assetClass}</div>
              </td>
              <td className="max-w-[140px] truncate px-3 py-2 font-sans text-[11.5px] text-txt-2">{h.sector ?? '—'}</td>
              <td className="px-3 py-2 text-right font-num text-[12px] tabular-nums text-txt-2">{h.qty.toLocaleString('en-IN')}</td>
              <td className="px-3 py-2 text-right font-num text-[12px] tabular-nums text-txt-2">{avgCost == null ? '—' : avgCost.toFixed(2)}</td>
              <td className="px-3 py-2 text-right font-num text-[12px] tabular-nums text-txt-2">{h.lastPrice == null ? '—' : h.lastPrice.toFixed(2)}</td>
              <td className="px-3 py-2 text-right font-num text-[12.5px] font-semibold tabular-nums text-txt-1">{inr(h.value)}</td>
              <td className="px-3 py-2 text-right font-num text-[12px] tabular-nums text-txt-2">
                {h.value != null && nav ? `${((h.value / nav) * 100).toFixed(1)}%` : '—'}
              </td>
              <td className={`px-3 py-2 text-right font-num text-[12px] tabular-nums ${retTone(pnlPct)}`}>{pct(pnlPct)}</td>
            </tr>
          )
        })}
      </tbody>
    </table>
  )
}

function SectorBars({ holdings }: { holdings: Holding[] }) {
  const total = holdings.reduce((a, h) => a + (h.value ?? 0), 0)
  if (!total) return null
  const slices = sectorComposition(
    holdings.map((h) => ({ sector: h.sector, weight: ((h.value ?? 0) / total) * 100 })),
  )
  return (
    <div className="space-y-1.5">
      {slices.map((s) => (
        <div key={s.sector} className="flex items-center gap-2">
          <span className="w-44 shrink-0 truncate font-sans text-[11.5px] text-txt-2">{s.sector}</span>
          <div className="h-2 flex-1 overflow-hidden rounded-full bg-surface-raised">
            <div className="h-full rounded-full bg-brand/70" style={{ width: `${Math.min(100, s.weight)}%` }} />
          </div>
          <span className="w-16 shrink-0 text-right font-num text-[11.5px] tabular-nums text-txt-1">
            {s.weight.toFixed(1)}% <span className="text-txt-3">·{s.count}</span>
          </span>
        </div>
      ))}
    </div>
  )
}

export async function PortfolioDetailV4({ id }: { id: string }) {
  const detail = await getPortfolioDetail(id).catch(() => null)
  if (!detail) notFound()
  const { summary: s, holdings, liveNav, backtestNav, benchmark, trades, totals } = detail

  const btStats = computeFundRiskStats(monthly(backtestNav))
  const btMaxDd = maxDrawdownDaily(backtestNav)
  const stats = { ...btStats, maxDrawdown: btMaxDd ?? btStats.maxDrawdown }

  const btSeries: ChartSeries[] = [
    { name: s.name, data: rebase(backtestNav), color: 'teal', lineWidth: 2 },
    { name: 'NIFTY 500', data: rebase(benchmark), color: 'warn', lineWidth: 1 },
  ]
  const liveSeries: ChartSeries[] = [
    { name: 'NAV', data: liveNav.map((p) => ({ time: p.d, value: p.nav })), color: 'teal', lineWidth: 2 },
  ]

  return (
    <div className="mx-auto max-w-[1400px] space-y-6 px-6 py-7">
      <div>
        <p className="font-num text-[9px] uppercase tracking-[0.14em] text-txt-3">
          {s.kind === 'strategy' ? `Rule-based · ${s.strategyLabel}` : 'FM basket'} · {s.assetClasses.join(' + ')} · inception {s.inceptionDate}
        </p>
        <h1 className="font-display text-[28px] font-medium tracking-tight text-txt-1">{s.name}</h1>
        <p className="mt-1 max-w-[860px] font-sans text-[13px] text-txt-2">
          Started with {inr(s.initialCapital)}, max {Math.round(s.maxPositionPct * 100)}% per position
          ({Math.floor(1 / s.maxPositionPct)} slots). Signals detected at one close execute at the next
          session&rsquo;s close; entries beyond open slots are ranked by Atlas composite.
        </p>
      </div>

      <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-3 lg:grid-cols-6">
        <Stat label={`NAV · ${s.navDate ?? '—'}`} value={inr(s.nav)} />
        <Stat label="Since inception" value={pct(s.sinceInceptionPct)} tone={retTone(s.sinceInceptionPct)} />
        <Stat label="Open positions" value={s.nPositions?.toString() ?? '—'} />
        <Stat label="Cash" value={inr(s.cash)} />
        <Stat label="Costs paid (in NAV)" value={inr(totals.live.costs)} />
        <Stat
          label="Tax accrued · post-tax NAV"
          value={s.nav != null ? `${inr(totals.live.tax)} · ${inr(s.nav - totals.live.tax)}` : '—'}
        />
      </div>

      {backtestNav.length > 5 && (
        <Panel
          eyebrow={`Backtest · ${btStats.navFrom} → ${btStats.navTo}`}
          title="If this rulebook had run for the last 5 years"
          info={{ body: 'The same engine replayed over stored history: same entry/exit rule, same composite ranking, same sizing — trades fill at real stored closes, next session after the signal.' }}
        >
          <div className="grid gap-5 lg:grid-cols-[1.4fr_1fr]">
            <div>
              <AtlasLightweightChart series={btSeries} height={300} title="Growth of ₹100 vs NIFTY 500" asOf={btStats.navTo ?? ''} precision={0} />
            </div>
            <div>
              <FundRiskStats stats={stats} />
              {backtestNav.length > 0 && (
                <p className="mt-3 rounded-tile border border-edge-hair bg-surface-raised px-3 py-2 font-sans text-[12px] leading-[1.55] text-txt-2">
                  Execution costs of <strong className="text-txt-1">{inr(totals.backtest.costs)}</strong> are already
                  inside this curve. Realized tax (FIFO, STCG/LTCG netted per FY):{' '}
                  <strong className="text-txt-1">{inr(totals.backtest.tax)}</strong> → post-tax total return{' '}
                  <strong className={retTone(postTaxTotalPct(backtestNav, totals.backtest.tax))}>
                    {pct(postTaxTotalPct(backtestNav, totals.backtest.tax))}
                  </strong>
                  {' '}vs {pct(totalPct(backtestNav))} pre-tax.
                </p>
              )}
            </div>
          </div>
        </Panel>
      )}

      <div className="grid gap-6 lg:grid-cols-[1.4fr_1fr]">
        <Panel eyebrow="Live paper-track" title="NAV since inception" bodyClassName="px-5 py-4">
          {liveNav.length > 1 ? (
            <AtlasLightweightChart series={liveSeries} height={260} asOf={s.navDate ?? ''} precision={0} />
          ) : (
            <p className="font-sans text-[13px] italic text-txt-3">
              Marked daily from inception ({s.inceptionDate}) — the curve appears after a few sessions.
            </p>
          )}
        </Panel>
        <Panel eyebrow="Exposure" title="Holdings by sector" bodyClassName="px-5 py-4">
          <SectorBars holdings={holdings} />
        </Panel>
      </div>

      <Panel eyebrow="Open positions" title={`Holdings (${holdings.length})`} bodyClassName="overflow-x-auto">
        <HoldingsTable holdings={holdings} nav={s.nav} />
      </Panel>

      <Panel
        eyebrow="Audit trail"
        title="Transactions"
        info={{ body: 'Every fill with its execution cost (STT/stamp/exchange/GST at the booked rates) and, on sells, the FIFO realized P&L, holding days, STCG/LTCG bucket and provisional tax. Rates are editable on /admin/thresholds.' }}
        bodyClassName="px-5 py-4"
      >
        <TradesTable trades={trades} />
      </Panel>
    </div>
  )
}
