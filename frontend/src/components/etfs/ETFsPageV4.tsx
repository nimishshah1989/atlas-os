// ETFsPageV4 — lens-first /etfs (behind LENS_V4). All data native atlas_foundation.
// The list is a FUNNEL into the ETF roll-up atom. ETFs are a holdings-weighted roll-up of
// the stock atom (D26/D27): the HEADLINE is LEADERSHIP-BREADTH (% of holdings weight that are
// top-decile leaders in ≥2 conviction lenses), NOT a composite. This is a TRANSPARENCY view —
// what's held, how it scores — explicitly NOT an outperformance predictor.
// Order: 1. leadership-breadth strip + a few top cards · 2. the sortable lens table.
import Link from 'next/link'
import { getEtfLensList, getEtfsAsOf, type EtfLensRow } from '@/lib/queries/etf_lens'
import { EtfLensTable } from './EtfLensTable'
import { Panel } from '@/components/ui/Panel'
import { StatCard, type Tone } from '@/components/ui/StatCard'
import { LensBubbleChart, type BubblePoint } from '@/components/ui/LensBubbleChart'
import { quartileCuts, relativeTone } from '@/lib/bubbleTone'

const cleanEtfCat = (c: string | null): string =>
  (c ?? '—').replace(/^India\s+Fund\s*[-–—]?\s*/i, '').trim() || (c ?? '—')

// Mean of the present holdings-weighted lens scores (0–100), or null if none scored.
function avgLens(e: EtfLensRow): number | null {
  const v = [e.v_tech, e.v_fund, e.v_cat, e.v_flow, e.v_val].filter((x): x is number => x != null)
  return v.length ? v.reduce((a, b) => a + b, 0) / v.length : null
}

const LENS_LABEL: { key: keyof Pick<EtfLensRow, 'v_tech' | 'v_fund' | 'v_cat' | 'v_flow' | 'v_val'>; label: string }[] = [
  { key: 'v_tech', label: 'Technical' },
  { key: 'v_fund', label: 'Fundamental' },
  { key: 'v_cat', label: 'Catalyst' },
  { key: 'v_flow', label: 'Flow' },
  { key: 'v_val', label: 'Valuation' },
]

const isSector = (c: string | null) => !!c && /sector/i.test(c)
const isBroad = (c: string | null) => !!c && /(index|broad|large|nifty|sensex|market)/i.test(c)

// The strongest lens for an ETF (highest weighted score), for the top-card chip.
function topLens(e: EtfLensRow): { label: string; v: number } | null {
  const scored = LENS_LABEL
    .map(l => ({ label: l.label, v: e[l.key] }))
    .filter((x): x is { label: string; v: number } => x.v != null)
  if (scored.length === 0) return null
  return scored.reduce((a, b) => (b.v > a.v ? b : a))
}

function TopCard({ e }: { e: EtfLensRow }) {
  const tl = topLens(e)
  return (
    <Link href={`/etfs/${e.fcode}`}
       className="group/card block rounded-tile border border-edge-hair bg-surface-raised px-3.5 py-3 no-underline shadow-tile transition-colors hover:border-edge-strong">
      <div className="mb-0.5 flex items-baseline justify-between gap-2">
        <span className="line-clamp-2 font-sans text-[13px] font-semibold leading-snug text-txt-1">{e.name}</span>
        <span className="shrink-0 font-num text-[15px] font-semibold tabular-nums text-sig-pos">
          {e.breadth == null ? '—' : `${(e.breadth * 100).toFixed(0)}%`}
        </span>
      </div>
      <div className="mb-2 truncate font-sans text-[11px] text-txt-3">{(e.category ?? '—').replace(/^India\s+Fund\s*[-–—]?\s*/i, '').trim() || '—'}</div>
      <div className="flex items-center justify-between gap-1 border-t border-edge-hair pt-2">
        <span className="font-num text-[10px] uppercase tracking-wider text-txt-3">
          {e.n_leaders} of {e.n_holdings} lead
        </span>
        {tl && <span className="font-num text-[10px] tabular-nums text-brand">{tl.label} {tl.v.toFixed(0)}</span>}
      </div>
    </Link>
  )
}

export async function ETFsPageV4() {
  const [etfs, asOf] = await Promise.all([getEtfLensList(), getEtfsAsOf()])

  const universeCount = etfs.length
  const withBreadth = etfs.filter(e => (e.breadth ?? 0) >= 0.1).length
  const sectorCount = etfs.filter(e => isSector(e.category)).length
  const broadCount = etfs.filter(e => isBroad(e.category)).length
  const expenses = etfs.map(e => e.expense).filter((x): x is number => x != null)
  const avgExpense = expenses.length ? expenses.reduce((a, b) => a + b, 0) / expenses.length : null

  // top-breadth ETFs for the cards (rows already arrive ranked by breadth desc).
  const top = etfs.filter(e => e.breadth != null).slice(0, 6)

  // Bubble landscape: x = leadership-breadth %, y = avg holdings-weighted lens score,
  // size = #holdings (diversification). COLOUR = the avg lens score (quality), so the tint reads
  // as "strong/ok/weak ETF" instead of the breadth bar that painted almost every ETF red. ETFs
  // have no fund-scorecard composite, so the holdings-weighted avg lens score is the quality proxy.
  // Colour by quartile of avg lens WITHIN the shown ETFs (top 25% green, bottom 25% red, middle
  // grey) — an absolute cut painted every ETF red because avg lens clusters ~40–49.
  const [alLo, alHi] = quartileCuts(etfs.map(avgLens).filter((v): v is number => v != null))
  const bubbles: BubblePoint[] = etfs
    .map((e) => {
      const al = avgLens(e)
      if (e.breadth == null || al == null) return null
      const br = e.breadth * 100
      const tone: BubblePoint['tone'] = relativeTone(al, alLo, alHi)
      return {
        id: e.fcode,
        label: e.name,
        x: br,
        y: al,
        size: e.n_holdings || 1,
        tone,
        href: `/etfs/${e.fcode}`,
        sub: `${cleanEtfCat(e.category)} · ${e.n_holdings} holdings · ${e.n_leaders} leaders · lens ${al.toFixed(0)}`,
      } as BubblePoint
    })
    .filter((p): p is BubblePoint => p != null)

  const strip: { label: string; value: string; sub: string; tone: Tone }[] = [
    { label: 'NSE equity ETFs', value: String(universeCount), tone: 'neutral',
      sub: 'Holdings-weighted lens roll-up' },
    { label: 'Breadth ≥ 10%', value: String(withBreadth), tone: 'pos',
      sub: '≥10% of weight leads ≥2 lenses' },
    { label: 'Sector ETFs', value: String(sectorCount), tone: 'neutral', sub: 'Category names a sector' },
    { label: 'Index / broad', value: String(broadCount), tone: 'neutral', sub: 'Index / broad-market mandate' },
    { label: 'Avg expense', value: avgExpense == null ? '—' : `${avgExpense.toFixed(2)}%`,
      tone: 'neutral', sub: 'Mean expense ratio across the set' },
  ]

  return (
    <div className="mx-auto max-w-[1680px] space-y-6 px-6 py-7">
      {/* Header + leadership-breadth strip */}
      <header>
        <nav className="mb-3 font-num text-[11px] text-txt-3" aria-label="Breadcrumb">
          <Link href="/" className="text-brand hover:underline">Atlas</Link> › ETFs
        </nav>
        <div className="mb-2 flex flex-wrap items-baseline gap-4">
          <h1 className="font-display text-[40px] font-bold leading-none tracking-tight text-txt-1">ETFs</h1>
          <span className="font-num text-[12px] text-txt-3">{universeCount} NSE equity ETFs · holdings-weighted lens roll-up</span>
          {asOf && <span className="font-sans text-[11px] text-txt-3">· as of {asOf}</span>}
        </div>
        <p className="max-w-[880px] font-sans text-[14px] leading-[1.5] text-txt-2">
          Each ETF is a <strong className="text-txt-1">holdings-weighted roll-up</strong> of the stock atom. The headline is
          <strong className="text-txt-1"> leadership-breadth</strong> — the share of holdings weight that are top-decile leaders
          (top-decile in ≥2 conviction lenses). This is a transparency view of what each ETF holds and how
          those holdings score on the six lenses — descriptive, <em>not</em> a forecast of outperformance.
        </p>

        <div className="mt-5 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
          {strip.map(t => (
            <StatCard key={t.label} label={t.label} value={t.value} sub={t.sub} tone={t.tone} />
          ))}
        </div>
      </header>

      {/* Highest leadership-breadth */}
      {top.length > 0 && (
        <Panel
          eyebrow="Leader weight"
          title="Highest leadership-breadth"
          info={{ body: 'The ETFs whose holdings carry the most leader weight right now. Click any for the holdings-weighted lens read and look-through.' }}
        >
          <div className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-6">
            {top.map(e => <TopCard key={e.fcode} e={e} />)}
          </div>
        </Panel>
      )}

      {/* Bubble landscape — leadership-breadth vs lens score, sized by holdings */}
      {bubbles.length > 0 && (
        <Panel
          eyebrow="Landscape"
          title="Leadership-breadth vs lens score"
          info={{ body: 'Each bubble is an ETF: x = leadership-breadth (share of weight that are leaders), y = average holdings-weighted lens score, size = number of holdings, COLOUR = avg lens relative to peers (green = top quartile · grey = middle · red = bottom quartile). Top-right = broad leadership. Hover for detail, click to open.' }}
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
        eyebrow="Universe"
        title="All NSE equity ETFs"
        info={{ body: 'Ranked by leadership-breadth. Every column header sorts; filter by category. The five lens scores are holdings-weighted (0–100). Click a row for the full roll-up.' }}
      >
        <EtfLensTable etfs={etfs} />
      </Panel>

      <p className="font-sans text-[12px] leading-[1.6] text-txt-3">
        Native from <strong className="text-txt-2">atlas_foundation</strong> — the lens journal looked through
        de_etf_holdings; identity from Morningstar (de_mf_master).
      </p>
    </div>
  )
}
