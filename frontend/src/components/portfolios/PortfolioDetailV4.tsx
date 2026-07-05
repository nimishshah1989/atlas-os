// PortfolioDetailV4 — one portfolio, fully glass-box: config, live paper-track,
// backtest growth vs NIFTY 500, risk box (reusing the fund math), holdings by
// sector, and the raw trade log. Everything rendered is stored engine output.
import { notFound } from 'next/navigation'
import { getPortfolioDetail, type NavPointRow, type Holding, type AtlasRead } from '@/lib/queries/portfolios'
import { TradesTable } from './TradesTable'
import { PolicyJournal } from './PolicyJournal'
import { DeskLog } from './DeskLog'
import { describeStrategy } from '@/lib/strategyDescription'
import { decileColor } from '@/components/ui/decile'
import { computeFundRiskStats, type NavPoint } from '@/lib/fundStats'
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

const scoreStyle = (v: number | null) => ({
  color: v == null ? 'var(--color-txt-3)' : decileColor(Math.min(10, Math.max(1, Math.ceil(v / 10)))),
})

function HoldingsTable({ holdings, nav }: { holdings: Holding[]; nav: number | null }) {
  if (holdings.length === 0)
    return <p className="px-5 py-4 font-sans text-[13px] italic text-txt-3">No open positions.</p>
  return (
    <table className="w-full min-w-[1080px]">
      <thead>
        <tr className="border-b border-edge-rule">
          {['Instrument', 'Sector', 'Qty', 'Avg cost', 'Last', 'Value', 'Weight', 'P&L', 'Comp', 'Tech', 'Flow', 'Val', 'RS 3M', 'EMA 50/200'].map((h, i) => (
            <th key={h} className={`px-2.5 py-2 font-num text-[10px] uppercase tracking-wider text-txt-3 ${i <= 1 ? 'text-left' : 'text-right'}`}>{h}</th>
          ))}
        </tr>
      </thead>
      <tbody>
        {holdings.map((h) => {
          const avgCost = h.qty ? h.netCost / h.qty : null
          const pnlPct = h.value != null && h.netCost ? (h.value / h.netCost - 1) * 100 : null
          const score = (v: number | null) => (
            <td className="px-2.5 py-2 text-right font-num text-[11.5px] font-semibold tabular-nums" style={scoreStyle(v)}>
              {v == null ? '—' : v.toFixed(0)}
            </td>
          )
          return (
            <tr key={h.instrumentKey} className="border-b border-edge-hair">
              <td className="px-2.5 py-2">
                {h.assetClass === 'stock' ? (
                  <a href={`/stocks/${h.symbol}`} className="font-num text-[12.5px] font-semibold tabular-nums text-txt-1 no-underline hover:text-brand hover:underline">{h.symbol}</a>
                ) : (
                  <span className="font-num text-[12.5px] font-semibold tabular-nums text-txt-1">{h.symbol}</span>
                )}
                <div className="max-w-[220px] truncate font-sans text-[10.5px] text-txt-3">
                  {h.riskFlags && !['[]', '{}'].includes(h.riskFlags.trim()) && (
                    <span className="mr-1 text-sig-warn" title={h.riskFlags}>⚑</span>
                  )}
                  {h.name ?? h.assetClass}
                </div>
              </td>
              <td className="max-w-[130px] truncate px-2.5 py-2 font-sans text-[11.5px] text-txt-2">{h.sector ?? '—'}</td>
              <td className="px-2.5 py-2 text-right font-num text-[12px] tabular-nums text-txt-2">{h.qty.toLocaleString('en-IN')}</td>
              <td className="px-2.5 py-2 text-right font-num text-[12px] tabular-nums text-txt-2">{avgCost == null ? '—' : avgCost.toFixed(2)}</td>
              <td className="px-2.5 py-2 text-right font-num text-[12px] tabular-nums text-txt-2">{h.lastPrice == null ? '—' : h.lastPrice.toFixed(2)}</td>
              <td className="px-2.5 py-2 text-right font-num text-[12.5px] font-semibold tabular-nums text-txt-1">{inr(h.value)}</td>
              <td className="px-2.5 py-2 text-right font-num text-[12px] tabular-nums text-txt-2">
                {h.value != null && nav ? `${((h.value / nav) * 100).toFixed(1)}%` : '—'}
              </td>
              <td className={`px-2.5 py-2 text-right font-num text-[12px] tabular-nums ${retTone(pnlPct)}`}>{pct(pnlPct)}</td>
              {score(h.composite)}
              {score(h.lensTech)}
              {score(h.lensFlow)}
              {score(h.lensVal)}
              <td className={`px-2.5 py-2 text-right font-num text-[11.5px] tabular-nums ${retTone(h.rs3m != null ? h.rs3m * 100 : null)}`}>
                {h.rs3m == null ? '—' : `${h.rs3m >= 0 ? '+' : ''}${(h.rs3m * 100).toFixed(1)}%`}
              </td>
              <td className="px-2.5 py-2 text-right font-num text-[11.5px] tabular-nums">
                <span className={h.aboveEma50 ? 'text-sig-pos' : 'text-txt-3'}>{h.aboveEma50 == null ? '—' : h.aboveEma50 ? '✓' : '✗'}</span>
                <span className="mx-0.5 text-txt-3">/</span>
                <span className={h.aboveEma200 ? 'text-sig-pos' : 'text-txt-3'}>{h.aboveEma200 == null ? '—' : h.aboveEma200 ? '✓' : '✗'}</span>
              </td>
            </tr>
          )
        })}
      </tbody>
    </table>
  )
}

function SectorVsBench({ atlas }: { atlas: AtlasRead }) {
  const rows = atlas.sectorVsBenchmark
  if (!rows.length) return <p className="font-sans text-[13px] italic text-txt-3">No positions yet.</p>
  const max = Math.max(...rows.map((r) => Math.max(r.port, r.bench)), 1)
  return (
    <div className="space-y-2">
      {rows.map((r) => {
        const diff = r.port - r.bench
        return (
          <div key={r.sector}>
            <div className="mb-0.5 flex items-baseline justify-between">
              <span className="truncate font-sans text-[11.5px] text-txt-2">{r.sector}</span>
              <span className="font-num text-[10.5px] tabular-nums text-txt-3">
                {r.port.toFixed(1)}% vs {r.bench.toFixed(1)}%{' '}
                <span className={diff >= 0 ? 'text-sig-pos' : 'text-sig-neg'}>
                  ({diff >= 0 ? '+' : ''}{diff.toFixed(1)})
                </span>
              </span>
            </div>
            <div className="h-1.5 overflow-hidden rounded-full bg-surface-raised">
              <div className="h-full rounded-full bg-brand/70" style={{ width: `${(r.port / max) * 100}%` }} />
            </div>
            <div className="mt-px h-1 overflow-hidden rounded-full bg-surface-raised">
              <div className="h-full rounded-full bg-txt-3/50" style={{ width: `${(r.bench / max) * 100}%` }} />
            </div>
          </div>
        )
      })}
      <p className="pt-1 font-sans text-[10.5px] text-txt-3">Thick bar = this portfolio · thin bar = NIFTY 500 sector weight.</p>
    </div>
  )
}

function HowItWorks({ explain, isSystem }: { explain: NonNullable<ReturnType<typeof describeStrategy>>; isSystem: boolean }) {
  const rows: [string, string][] = [
    ['Buy rule', explain.entry],
    ['Sell rule', explain.exit],
    ['Universe', explain.universe],
    ['Which names', explain.selection],
    ['Position sizing', explain.sizing],
  ]
  return (
    <div>
      <p className="mb-3 font-sans text-[14px] font-medium text-txt-1">{explain.headline}.</p>
      <dl className="space-y-2.5">
        {rows.map(([k, v]) => (
          <div key={k} className="grid grid-cols-[110px_1fr] gap-3 sm:grid-cols-[130px_1fr]">
            <dt className="font-num text-[10px] uppercase tracking-wider text-txt-3 pt-0.5">{k}</dt>
            <dd className="font-sans text-[13px] leading-[1.55] text-txt-2">{v}</dd>
          </div>
        ))}
      </dl>
      {isSystem && (
        <p className="mt-3 border-t border-edge-hair pt-3 font-sans text-[12px] italic leading-[1.5] text-txt-3">
          This rulebook was chosen by the system&rsquo;s walk-forward search, not hand-written — the exact filters above are what won on out-of-sample data. See the Learning log below for how it got here and what it rejected.
        </p>
      )}
    </div>
  )
}

export async function PortfolioDetailV4({ id }: { id: string }) {
  const detail = await getPortfolioDetail(id).catch(() => null)
  if (!detail) notFound()
  const { summary: s, holdings, liveNav, backtestNav, benchmark, trades, totals, atlas, policyJournal, deskJournal } = detail
  const isSystem = s.category === 'system'
  const isDesk = s.params?.desk === true
  const explain = describeStrategy(s.kind, s.params, s.assetClasses, s.maxPositionPct, s.strategyKey)

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
          {isSystem ? `System-generated · ${s.strategyLabel}` : s.kind === 'strategy' ? `Rule-based · ${s.strategyLabel}` : 'FM basket'} · {s.assetClasses.join(' + ')} · inception {s.inceptionDate}
        </p>
        <h1 className="font-display text-[28px] font-medium tracking-tight text-txt-1">{s.name}</h1>
        <p className="mt-1 max-w-[860px] font-sans text-[13px] text-txt-2">
          Started with {inr(s.initialCapital)} · max {Math.round(s.maxPositionPct * 100)}% per position
          ({Math.floor(1 / s.maxPositionPct)} slots).
        </p>
      </div>

      {explain && (
        <Panel
          eyebrow={isSystem ? 'System-designed strategy' : s.kind === 'basket' ? 'Manual basket' : 'Rule-based strategy'}
          title="How this strategy works"
          info={{ body: 'A plain-English description of exactly what this portfolio does — its buy and sell rules, universe, and how positions are chosen and sized. Generated from the live strategy parameters, so it always matches what is actually running.' }}
          bodyClassName="px-5 py-4"
        >
          <HowItWorks explain={explain} isSystem={isSystem} />
        </Panel>
      )}

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
        <Panel
          eyebrow="Exposure"
          title="Sector weights vs NIFTY 500"
          info={{ body: 'Portfolio sector weights (by market value) against the live NIFTY 500 sector weights from index constituents — where this book is over- and under-weight the market.' }}
          bodyClassName="px-5 py-4"
        >
          <SectorVsBench atlas={atlas} />
        </Panel>
      </div>

      {holdings.length > 0 && (
        <Panel
          eyebrow="Atlas read"
          title="What the lens engine says about this book"
          info={{ body: 'Value-weighted over current holdings, from the latest lens snapshot and technicals: composite score, internal breadth (share of book above its 50/200 EMA), relative strength vs NIFTY 500 over 3 months, and any active risk flags.' }}
          bodyClassName="px-5 py-4"
        >
          <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-5">
            <Stat label="Weighted composite" value={atlas.weightedComposite == null ? '—' : atlas.weightedComposite.toFixed(1)} />
            <Stat label="Above 50 EMA" value={atlas.breadth50 == null ? '—' : `${atlas.breadth50.toFixed(0)}%`} tone={atlas.breadth50 != null && atlas.breadth50 >= 60 ? 'text-sig-pos' : undefined} />
            <Stat label="Above 200 EMA" value={atlas.breadth200 == null ? '—' : `${atlas.breadth200.toFixed(0)}%`} tone={atlas.breadth200 != null && atlas.breadth200 >= 60 ? 'text-sig-pos' : undefined} />
            <Stat label="Weighted RS 3M" value={atlas.weightedRs3m == null ? '—' : `${atlas.weightedRs3m >= 0 ? '+' : ''}${(atlas.weightedRs3m * 100).toFixed(1)}%`} tone={retTone(atlas.weightedRs3m)} />
            <Stat label="Risk flags" value={String(atlas.flaggedCount)} tone={atlas.flaggedCount > 0 ? 'text-sig-warn' : undefined} />
          </div>
        </Panel>
      )}

      <Panel eyebrow="Open positions" title={`Holdings (${holdings.length})`} bodyClassName="overflow-x-auto">
        <HoldingsTable holdings={holdings} nav={s.nav} />
      </Panel>

      {isDesk && (
        <Panel
          eyebrow="Desk log"
          title="The desk's nightly judgment"
          info={{ body: 'Every night after the marks: the Scout reads the fresh Atlas ranks and flags what changed; the Risk & Tax officer approves, defers or vetoes each proposal (weighing STCG vs LTCG and concentration); the PM issues orders, each with a thesis and a falsifiable exit condition. All of it is journaled — including the nights it correctly does nothing.' }}
          bodyClassName="px-5 py-4"
        >
          {detail.deskLessons.length > 0 && (
            <div className="mb-4 rounded-tile border border-edge-hair bg-surface-raised px-3 py-2.5">
              <p className="mb-1.5 font-num text-[9px] uppercase tracking-wider text-txt-3">
                Lessons earned from outcomes (confidence-weighted, weekly reflection)
              </p>
              {detail.deskLessons.map((l, i) => (
                <p key={i} className="font-sans text-[12px] leading-[1.5] text-txt-2">
                  <span className="font-num text-[10.5px] tabular-nums text-txt-3">{(l.confidence * 100).toFixed(0)}%</span>{' '}
                  {l.lesson}
                </p>
              ))}
            </div>
          )}
          <DeskLog cycles={deskJournal} />
        </Panel>
      )}

      {isSystem && !isDesk && (
        <Panel
          eyebrow="Learning log"
          title="How the policy has evolved"
          info={{ body: 'Each weekly walk-forward cycle: candidate policies are scored on a training window, validated out-of-sample, and a challenger is adopted only if it beats the champion’s excess return over NIFTY 500 while keeping max drawdown below the benchmark’s. Every evaluation and change is journaled here with its evidence.' }}
          bodyClassName="px-5 py-4"
        >
          <PolicyJournal entries={policyJournal} />
        </Panel>
      )}

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
