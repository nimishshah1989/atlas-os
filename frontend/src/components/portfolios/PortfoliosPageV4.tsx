// PortfoliosPageV4 — the /portfolios board as kanban-style cards, color-coded by
// category: rule-based strategy simulations · system-generated (the learning
// expert agent) · FM baskets. Every figure is stored engine output.
import Link from 'next/link'
import { Leaderboard } from './Leaderboard'
import { getPortfolios, getCompareCurves, type PortfolioSummary, type PortfolioCategory } from '@/lib/queries/portfolios'
import { AtlasLightweightChart, type ChartSeries } from '@/components/charts/AtlasLightweightChart'
import { Panel } from '@/components/ui/Panel'

const inr = (v: number | null) =>
  v == null ? '—' : `₹${v.toLocaleString('en-IN', { maximumFractionDigits: 0 })}`
const pct = (v: number | null) =>
  v == null ? '—' : `${v > 0 ? '+' : ''}${v.toFixed(1)}%`
const retTone = (v: number | null) =>
  v == null ? 'text-txt-3' : v >= 0 ? 'text-sig-pos' : 'text-sig-neg'

const CATEGORY: Record<PortfolioCategory, { label: string; accent: string; chip: string }> = {
  rule: {
    label: 'Rule-based',
    accent: 'border-l-brand',
    chip: 'border-brand/30 bg-brand/10 text-brand',
  },
  system: {
    label: 'System-generated',
    accent: 'border-l-sig-warn',
    chip: 'border-sig-warn/30 bg-sig-warn/10 text-sig-warn',
  },
  basket: {
    label: 'FM basket',
    accent: 'border-l-txt-3',
    chip: 'border-edge-rule bg-surface-raised text-txt-2',
  },
}

function Card({ p }: { p: PortfolioSummary }) {
  const cat = CATEGORY[p.category]
  return (
    <Link
      href={`/portfolios/${p.id}`}
      className={`block rounded-panel border border-edge-hair border-l-[3px] ${cat.accent} bg-surface-panel p-4 no-underline shadow-tile transition-colors hover:border-edge-strong`}
    >
      <div className="mb-1 flex items-start justify-between gap-2">
        <span className={`shrink-0 rounded-tile border px-2 py-0.5 font-sans text-[10px] font-semibold uppercase tracking-wider ${cat.chip}`}>
          {cat.label}
        </span>
        <span className="font-num text-[10px] tabular-nums text-txt-3">since {p.inceptionDate}</span>
      </div>
      <h3 className="font-display text-[16px] font-semibold leading-snug text-txt-1">{p.name}</h3>
      <p className="mb-3 font-sans text-[11.5px] text-txt-3">
        {p.strategyLabel ?? 'FM-picked instruments'} · {p.assetClasses.join(' + ')}
      </p>
      {p.nav == null ? (
        <p className="mb-3 rounded-tile border border-edge-hair bg-surface-raised px-2.5 py-2 font-sans text-[11.5px] leading-[1.45] text-txt-3">
          Awaiting first mark — goes live at the next EOD cycle.
        </p>
      ) : (
        <div className="mb-3 flex items-baseline justify-between">
          <span className="font-num text-[22px] font-semibold tabular-nums text-txt-1">{inr(p.nav)}</span>
          <span className={`font-num text-[14px] font-semibold tabular-nums ${retTone(p.sinceInceptionPct)}`}>
            {pct(p.sinceInceptionPct)}
          </span>
        </div>
      )}
      <div className="grid grid-cols-3 gap-2 border-t border-edge-hair pt-2.5">
        <div>
          <div className="font-num text-[9px] uppercase tracking-wider text-txt-3">Positions</div>
          <div className="font-num text-[13px] tabular-nums text-txt-1">{p.nPositions ?? '—'}</div>
        </div>
        <div>
          <div className="font-num text-[9px] uppercase tracking-wider text-txt-3">Cash</div>
          <div className="font-num text-[13px] tabular-nums text-txt-1">
            {p.nav && p.cash != null ? `${((p.cash / p.nav) * 100).toFixed(0)}%` : '—'}
          </div>
        </div>
        <div>
          <div className="font-num text-[9px] uppercase tracking-wider text-txt-3">5Y CAGR · backtest</div>
          <div className={`font-num text-[13px] font-semibold tabular-nums ${retTone(p.btCagr5Pct)}`}>
            {p.btCagr5Pct == null ? '—' : `${p.btCagr5Pct > 0 ? '+' : ''}${p.btCagr5Pct.toFixed(1)}%`}
          </div>
        </div>
      </div>
    </Link>
  )
}

const CURVE_COLOR: Record<PortfolioCategory, ChartSeries['color']> = {
  rule: 'teal',
  system: 'warn',
  basket: 'ink',
}

export async function PortfoliosPageV4() {
  const [portfolios, curves] = await Promise.all([getPortfolios(), getCompareCurves()])
  const compareSeries: ChartSeries[] = curves.map((c) => ({
    name: c.name,
    data: c.points.map((p) => ({ time: p.d, value: p.v })),
    color: CURVE_COLOR[c.category],
    lineWidth: c.category === 'system' ? 2 : 1,
  }))
  const groups: { cat: PortfolioCategory; items: PortfolioSummary[] }[] = (
    ['rule', 'system', 'basket'] as PortfolioCategory[]
  )
    .map((cat) => ({ cat, items: portfolios.filter((p) => p.category === cat) }))
    .filter((g) => g.items.length > 0)

  return (
    <div className="mx-auto max-w-[1400px] space-y-7 px-6 py-7">
      <div>
        <p className="font-num text-[9px] uppercase tracking-[0.14em] text-txt-3">Paper-traded · marked at every EOD · costs in NAV</p>
        <h1 className="font-display text-[28px] font-medium tracking-tight text-txt-1">Portfolios</h1>
        <p className="mt-2 max-w-[860px] font-sans text-[13.5px] text-txt-2">
          Model portfolios run by the Atlas engine — rule-based strategies, system-generated books,
          and FM baskets — paper-traded from inception at real EOD closes with execution costs in
          the NAV and a FIFO tax ledger. Click a card for the full glass-box view.
        </p>
      </div>

      {portfolios.length === 0 && (
        <p className="font-sans text-[13px] italic text-txt-3">No portfolios yet.</p>
      )}

      <Leaderboard />

      {compareSeries.length > 1 && (
        <Panel
          eyebrow="Backtest horse-race"
          title="Every rulebook, ₹100 rebased"
          info={{ body: 'Each portfolio’s backtest NAV rebased to 100 at the start of its history (month-end sampled). Rule-based = teal, system-generated = amber, FM baskets = grey. Costs are already in each curve.' }}
          bodyClassName="px-5 py-4"
        >
          <AtlasLightweightChart series={compareSeries} height={320} yLabel="Growth of ₹100 · backtest" precision={0} />
        </Panel>
      )}
      {groups.map(({ cat, items }) => (
        <section key={cat} aria-label={CATEGORY[cat].label}>
          <h2 className="mb-2.5 font-num text-[10px] uppercase tracking-[0.14em] text-txt-3">
            {CATEGORY[cat].label} · {items.length}
          </h2>
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            {items.map((p) => <Card key={p.id} p={p} />)}
          </div>
        </section>
      ))}
    </div>
  )
}
