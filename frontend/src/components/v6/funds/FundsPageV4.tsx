// FundsPageV4 — lens-first /funds. All data native foundation_staging.
// The list is a FUNNEL into the fund roll-up atom. Funds are a holdings-weighted roll-up of
// the stock atom (D26/D27): the headline strip is LEADERSHIP-BREADTH, and the score/rank is a
// DERIVED composite of the same holdings-weighted lenses (fundScore.ts) — the same blend used for
// sectors and stocks, not a standalone scorecard. This is a TRANSPARENCY view — what's held, how it
// scores — explicitly NOT an outperformance predictor. The fund-specific differentiator (on each
// detail page) is ACTIVE-MOVEMENT: month-over-month holdings deltas.
// Order: 1. leadership-breadth strip + a few top cards · 2. the sortable lens table.
import { getFundLensList, type FundLensRow } from '@/lib/queries/v6/fund_lens'
import { getLensWeights } from '@/lib/queries/v6/lens_weights'
import { getFundRankHistory } from '@/lib/queries/v6/fund_rank_history'
import { getFundRsMatrix, getFundHoldingsEma } from '@/lib/queries/v6/fund_metrics'
import { FundLensTable } from './FundLensTable'
import { Panel } from '@/components/v4/ui/Panel'
import { StatCard, type Tone } from '@/components/v4/ui/StatCard'
import { LensBubbleChart, type BubblePoint } from '@/components/v4/ui/LensBubbleChart'
import { quartileCuts, relativeTone } from '@/lib/v6/bubbleTone'

// Strip Morningstar's redundant "India Fund " category prefix for display (filtering uses raw value).
const cleanCat = (c: string | null): string =>
  (c ?? '—').replace(/^India\s+Fund\s*[-–—]?\s*/i, '').trim() || (c ?? '—')

// Mean of the present holdings-weighted lens scores (0–100), or null if none scored.
function avgFundLens(f: FundLensRow): number | null {
  const v = [f.v_tech, f.v_fund, f.v_cat, f.v_flow, f.v_val].filter((x): x is number => x != null)
  return v.length ? v.reduce((a, b) => a + b, 0) / v.length : null
}

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
       className="block rounded-tile border border-edge-hair bg-surface-panel p-3.5 shadow-tile no-underline transition-colors hover:border-edge-strong">
      <div className="mb-0.5 flex items-baseline justify-between gap-2">
        <span className="line-clamp-2 font-sans text-[13px] font-semibold leading-snug text-txt-1">{f.name}</span>
        <span className="shrink-0 font-num text-[15px] font-semibold tabular-nums text-sig-pos">
          {f.breadth == null ? '—' : `${(f.breadth * 100).toFixed(0)}%`}
        </span>
      </div>
      <div className="mb-2 truncate font-sans text-[11px] text-txt-3">{cleanCat(f.category)}</div>
      <div className="flex items-center justify-between gap-1 border-t border-edge-hair pt-2">
        <span className="font-sans text-[10px] uppercase tracking-wider text-txt-3">
          {f.n_leaders} of {f.n_holdings} lead
        </span>
        {tl && <span className="font-num text-[10px] tabular-nums text-brand">{tl.label} {tl.v.toFixed(0)}</span>}
      </div>
    </a>
  )
}

export async function FundsPageV4() {
  const [funds, weights, historyMap, rsMap, emaMap] = await Promise.all([
    getFundLensList(),
    getLensWeights(),
    getFundRankHistory(),
    getFundRsMatrix(),
    getFundHoldingsEma(),
  ])
  // Maps → plain objects so they serialise across the server→client boundary into FundLensTable.
  const history = Object.fromEntries(historyMap)
  const rs = Object.fromEntries(rsMap)
  const ema = Object.fromEntries(emaMap)

  const universeCount = funds.length
  const withBreadth = funds.filter(f => (f.breadth ?? 0) >= 0.2).length
  const categoryCount = new Set(funds.map(f => f.category).filter((x): x is string => !!x)).size
  const amcCount = new Set(funds.map(f => f.amc).filter((x): x is string => !!x)).size
  const expenses = funds.map(f => f.expense).filter((x): x is number => x != null)
  const avgExpense = expenses.length ? expenses.reduce((a, b) => a + b, 0) / expenses.length : null

  // top-breadth funds for the cards (rows already arrive ranked by breadth desc).
  const top = funds.filter(f => f.breadth != null).slice(0, 6)

  // Bubble landscape: x = leadership-breadth %, y = avg holdings-weighted lens score,
  // size = #holdings (diversification). COLOUR = the scorecard quality score (composite) so the
  // tint reads as "good/ok/weak fund", not the harsh breadth bar that turned ~85% of funds red.
  // Funds without a scorecard composite are neutral (grey), never a fake colour. Real values only.
  // Colour bubbles by quartile of the fund score WITHIN the shown set, so the colour shows relative
  // quality (top 25% green, bottom 25% red, middle grey) instead of an absolute cut that — given the
  // composite clusters ~42–55 — painted every fund red with zero green.
  const [scoreLo, scoreHi] = quartileCuts(funds.map((f) => f.composite).filter((v): v is number => v != null))
  const bubbles: BubblePoint[] = funds
    .map((f) => {
      const al = avgFundLens(f)
      if (f.breadth == null || al == null) return null
      const br = f.breadth * 100
      const tone: BubblePoint['tone'] = relativeTone(f.composite, scoreLo, scoreHi)
      return {
        id: f.mstar_id,
        label: f.name,
        x: br,
        y: al,
        size: f.n_holdings || 1,
        tone,
        href: `/funds/${f.mstar_id}`,
        sub: `${cleanCat(f.category)} · ${f.n_holdings} holdings · ${f.composite != null ? `score ${f.composite.toFixed(0)} · rank ${f.cat_rank}/${f.cat_size}` : 'unscored'}`,
      } as BubblePoint
    })
    .filter((p): p is BubblePoint => p != null)

  const strip: { label: string; value: string; tone: Tone; sub: string }[] = [
    { label: 'Equity funds', value: String(universeCount), tone: 'neutral', sub: 'Regular Growth · holdings-weighted roll-up' },
    { label: 'Breadth ≥ 20%', value: String(withBreadth), tone: 'pos', sub: '≥20% of weight leads ≥2 lenses' },
    { label: 'Categories', value: String(categoryCount), tone: 'neutral', sub: 'Distinct SEBI categories' },
    { label: 'AMCs', value: String(amcCount), tone: 'neutral', sub: 'Distinct asset managers' },
    { label: 'Avg expense', value: avgExpense == null ? '—' : `${avgExpense.toFixed(2)}%`, tone: 'neutral', sub: 'Mean expense ratio across the set' },
  ]

  return (
    <div className="mx-auto max-w-[1680px] space-y-6 px-6 py-7">
      {/* Header + leadership-breadth strip */}
      <header>
        <div className="mb-3 font-sans text-[12px] text-txt-3">
          <a href="/" className="text-brand no-underline hover:underline">Atlas</a> › Funds
        </div>
        <div className="mb-2 flex flex-wrap items-baseline gap-4">
          <h1 className="font-display text-[32px] font-bold tracking-tight text-txt-1">Funds</h1>
          <span className="font-num text-[12px] tabular-nums text-txt-3">{universeCount} equity funds (Regular Growth) · holdings-weighted lens roll-up</span>
        </div>
        <p className="max-w-[880px] font-sans text-[15px] text-txt-2">
          Each fund is a <strong>holdings-weighted roll-up</strong> of the stock atom. The headline is
          <strong> leadership-breadth</strong> — the share of holdings weight that are top-decile leaders
          (top-decile in ≥2 conviction lenses). The fund-specific differentiator, on each detail page, is
          <strong> active-movement</strong>: what the manager is buying and selling month over month. This is a
          transparency view of what each fund holds and how it scores — descriptive, <em>not</em> a forecast of outperformance.
        </p>

        <div className="mt-6 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
          {strip.map(t => (
            <StatCard key={t.label} label={t.label} value={t.value} sub={t.sub} tone={t.tone} />
          ))}
        </div>
      </header>

      {/* Highest leadership-breadth */}
      {top.length > 0 && (
        <Panel
          eyebrow="Leaders"
          title="Highest leadership-breadth"
          info={{
            title: 'Highest leadership-breadth',
            body: 'The funds whose holdings carry the most leader weight right now. Click any for the holdings-weighted lens read, active-movement and look-through.',
          }}
        >
          <div className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-6">
            {top.map(f => <TopCard key={f.mstar_id} f={f} />)}
          </div>
        </Panel>
      )}

      {/* Bubble landscape — leadership-breadth vs lens score, sized by holdings */}
      {bubbles.length > 0 && (
        <Panel
          eyebrow="Landscape"
          title="Leadership-breadth vs lens score"
          info={{ body: 'Each bubble is a fund: x = leadership-breadth (share of weight that are leaders), y = average holdings-weighted lens score, size = number of holdings, COLOUR = fund score relative to peers (green = top quartile · grey = middle · red = bottom quartile · grey if unscored). Top-right = broad leadership. Hover for detail, click to open.' }}
          bodyClassName="px-2 py-2"
        >
          <LensBubbleChart
            points={bubbles}
            xLabel="Leadership-breadth (%)"
            yLabel="Avg lens score (0–100)"
            sizeLabel="# holdings"
            xFmt={(v) => `${v.toFixed(0)}%`}
            yFmt={(v) => v.toFixed(0)}
          />
        </Panel>
      )}

      {/* The sortable lens table (client: sort + category filter) */}
      <Panel
        eyebrow="Screener"
        title="All equity funds"
        info={{
          title: 'All equity funds',
          body: 'Ranked by leadership-breadth. Every column header sorts; filter by category. The five lens scores are holdings-weighted (0–100). Click a row for the full roll-up.',
        }}
      >
        <FundLensTable funds={funds} weights={weights} history={history} rs={rs} ema={ema} />
      </Panel>

      <div className="font-sans text-[12px] leading-[1.6] text-txt-3">
        Native from <strong className="text-txt-2">foundation_staging</strong> — the lens journal looked through
        de_mf_holdings; identity + NAV from Morningstar (de_mf_master / de_mf_nav_daily).
      </div>
    </div>
  )
}
