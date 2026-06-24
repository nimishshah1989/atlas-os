// FundsPageV4 — lens-first /funds. All data native foundation_staging.
// The list is a FUNNEL into the fund roll-up atom. Funds are a holdings-weighted roll-up of
// the stock atom (D26/D27): the HEADLINE is LEADERSHIP-BREADTH (% of holdings weight that are
// top-decile leaders in ≥2 conviction lenses), NOT a composite. This is a TRANSPARENCY view —
// what's held, how it scores — explicitly NOT an outperformance predictor. The fund-specific
// differentiator (on each detail page) is ACTIVE-MOVEMENT: month-over-month holdings deltas.
// Order: 1. leadership-breadth strip + a few top cards · 2. the sortable lens table.
import { getFundLensList, type FundLensRow } from '@/lib/queries/v6/fund_lens'
import { FundLensTable } from './FundLensTable'

const LENS_LABEL: { key: keyof Pick<FundLensRow, 'v_tech' | 'v_fund' | 'v_cat' | 'v_flow' | 'v_val'>; label: string }[] = [
  { key: 'v_tech', label: 'Technical' },
  { key: 'v_fund', label: 'Fundamental' },
  { key: 'v_cat', label: 'Catalyst' },
  { key: 'v_flow', label: 'Flow' },
  { key: 'v_val', label: 'Valuation' },
]

// The strongest lens for a fund (highest weighted score), for the top-card chip.
function topLens(f: FundLensRow): { label: string; v: number } | null {
  const scored = LENS_LABEL
    .map(l => ({ label: l.label, v: f[l.key] }))
    .filter((x): x is { label: string; v: number } => x.v != null)
  if (scored.length === 0) return null
  return scored.reduce((a, b) => (b.v > a.v ? b : a))
}

function TopCard({ f }: { f: FundLensRow }) {
  const tl = topLens(f)
  return (
    <a href={`/funds/${f.mstar_id}`}
       className="block bg-paper border border-paper-rule rounded-sm p-3 no-underline hover:border-ink-tertiary transition-colors">
      <div className="flex items-baseline justify-between gap-2 mb-0.5">
        <span className="font-sans text-[13px] font-semibold text-ink-primary leading-snug line-clamp-2">{f.name}</span>
        <span className="font-mono text-[15px] font-semibold text-signal-pos shrink-0">
          {f.breadth == null ? '—' : `${(f.breadth * 100).toFixed(0)}%`}
        </span>
      </div>
      <div className="font-sans text-[11px] text-ink-tertiary truncate mb-2">{f.category ?? '—'}</div>
      <div className="flex items-center justify-between gap-1 pt-2 border-t border-paper-rule/60">
        <span className="font-sans text-[10px] text-ink-tertiary uppercase tracking-wider">
          {f.n_leaders} of {f.n_holdings} lead
        </span>
        {tl && <span className="font-mono text-[10px] text-teal">{tl.label} {tl.v.toFixed(0)}</span>}
      </div>
    </a>
  )
}

export async function FundsPageV4() {
  const funds = await getFundLensList()

  const universeCount = funds.length
  const withBreadth = funds.filter(f => (f.breadth ?? 0) >= 0.2).length
  const categoryCount = new Set(funds.map(f => f.category).filter((x): x is string => !!x)).size
  const amcCount = new Set(funds.map(f => f.amc).filter((x): x is string => !!x)).size
  const expenses = funds.map(f => f.expense).filter((x): x is number => x != null)
  const avgExpense = expenses.length ? expenses.reduce((a, b) => a + b, 0) / expenses.length : null

  // top-breadth funds for the cards (rows already arrive ranked by breadth desc).
  const top = funds.filter(f => f.breadth != null).slice(0, 6)

  const strip = [
    { label: 'Equity funds', value: String(universeCount), cls: 'text-ink-primary',
      foot: 'Regular Growth · holdings-weighted roll-up' },
    { label: 'Breadth ≥ 20%', value: String(withBreadth), cls: 'text-signal-pos',
      foot: '≥20% of weight leads ≥2 lenses' },
    { label: 'Categories', value: String(categoryCount), cls: 'text-ink-primary', foot: 'Distinct SEBI categories' },
    { label: 'AMCs', value: String(amcCount), cls: 'text-ink-primary', foot: 'Distinct asset managers' },
    { label: 'Avg expense', value: avgExpense == null ? '—' : `${avgExpense.toFixed(2)}%`,
      cls: 'text-ink-primary font-mono text-[20px]', foot: 'Mean expense ratio across the set' },
  ]

  return (
    <div className="max-w-[1400px] mx-auto">
      {/* Header + leadership-breadth strip */}
      <section className="px-8 py-8 border-b border-paper-rule">
        <div className="font-sans text-[12px] text-ink-tertiary mb-3">
          <a href="/" className="text-teal no-underline hover:underline">Atlas</a> › Funds
        </div>
        <div className="flex items-baseline gap-4 flex-wrap mb-2">
          <h1 className="font-serif text-[44px] font-normal tracking-[-0.011em] text-ink-primary leading-[1.1]">Funds</h1>
          <span className="font-mono text-[12px] text-ink-tertiary">{universeCount} equity funds (Regular Growth) · holdings-weighted lens roll-up</span>
        </div>
        <p className="font-sans text-[15px] text-ink-secondary max-w-[880px]">
          Each fund is a <strong>holdings-weighted roll-up</strong> of the stock atom. The headline is
          <strong> leadership-breadth</strong> — the share of holdings weight that are top-decile leaders
          (top-decile in ≥2 conviction lenses). The fund-specific differentiator, on each detail page, is
          <strong> active-movement</strong>: what the manager is buying and selling month over month. This is a
          transparency view of what each fund holds and how it scores — descriptive, <em>not</em> a forecast of outperformance.
        </p>

        <div className="mt-6 bg-paper-soft border border-paper-rule rounded-sm overflow-hidden grid"
             style={{ gridTemplateColumns: 'repeat(5, 1fr)' }}>
          {strip.map((t, i) => (
            <div key={t.label} className={`px-[18px] py-[14px] ${i < 4 ? 'border-r border-paper-rule' : ''}`}>
              <div className="font-sans text-[9px] tracking-[0.18em] uppercase text-ink-tertiary font-semibold mb-1">{t.label}</div>
              <div className={`font-mono text-[22px] font-medium leading-none ${t.cls}`}>{t.value}</div>
              <div className="font-sans text-[11px] text-ink-tertiary mt-1 leading-snug">{t.foot}</div>
            </div>
          ))}
        </div>
      </section>

      {/* Highest leadership-breadth */}
      {top.length > 0 && (
        <section className="px-8 py-9 border-b border-paper-rule" aria-label="Highest leadership-breadth funds">
          <div className="mb-4">
            <h2 className="font-serif text-[28px] font-normal tracking-tight text-ink-primary">Highest leadership-breadth</h2>
            <p className="font-sans text-[13px] text-ink-tertiary mt-1 max-w-[760px]">
              The funds whose holdings carry the most leader weight right now. Click any for the holdings-weighted lens read, active-movement and look-through.
            </p>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
            {top.map(f => <TopCard key={f.mstar_id} f={f} />)}
          </div>
        </section>
      )}

      {/* The sortable lens table (client: sort + category filter) */}
      <section className="px-8 py-10 border-b border-paper-rule" aria-label="Fund lens table">
        <div className="mb-5">
          <h2 className="font-serif text-[28px] font-normal tracking-tight text-ink-primary">All equity funds</h2>
          <p className="font-sans text-[13px] text-ink-tertiary max-w-[760px] leading-[1.45] mt-1">
            Ranked by leadership-breadth. Every column header sorts; filter by category. The five lens scores are
            holdings-weighted (0–100). Click a row for the full roll-up.
          </p>
        </div>
        <FundLensTable funds={funds} />
      </section>

      <div className="px-8 py-6 font-sans text-[12px] text-ink-tertiary leading-[1.6]">
        Native from <strong className="text-ink-secondary">foundation_staging</strong> — the lens journal looked through
        de_mf_holdings; identity + NAV from Morningstar (de_mf_master / de_mf_nav_daily).
      </div>
    </div>
  )
}
