// PortfoliosPageV4 — the /portfolios board as kanban-style cards, color-coded by
// category: rule-based strategy simulations · system-generated (the learning
// expert agent) · FM baskets. Every figure is stored engine output.
import Link from 'next/link'
import { getPortfolios, type PortfolioSummary, type PortfolioCategory } from '@/lib/queries/portfolios'

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
        {p.kind === 'strategy' ? p.strategyLabel : 'FM-picked instruments'} · {p.assetClasses.join(' + ')}
      </p>
      <div className="mb-3 flex items-baseline justify-between">
        <span className="font-num text-[22px] font-semibold tabular-nums text-txt-1">{inr(p.nav)}</span>
        <span className={`font-num text-[14px] font-semibold tabular-nums ${retTone(p.sinceInceptionPct)}`}>
          {pct(p.sinceInceptionPct)}
        </span>
      </div>
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
          <div className="font-num text-[9px] uppercase tracking-wider text-txt-3">
            Backtest{p.btYears != null ? ` ${p.btYears.toFixed(0)}y` : ''}
          </div>
          <div className={`font-num text-[13px] font-semibold tabular-nums ${retTone(p.btTotalPct)}`}>
            {pct(p.btTotalPct)}
          </div>
        </div>
      </div>
    </Link>
  )
}

export async function PortfoliosPageV4() {
  const portfolios = await getPortfolios()
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
