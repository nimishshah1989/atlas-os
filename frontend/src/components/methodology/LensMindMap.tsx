// LensMindMap — the conviction score decomposed into its real lenses and sub-components.
// Every node here is REAL and traceable: the six lenses and their sub-components are the columns
// stored in foundation_staging.atlas_lens_scores_daily (tech_trend, fund_profitability, …); the
// lens WEIGHTS, convergence boosts and conviction tiers are read LIVE from atlas_thresholds (passed
// in as props), so the mind-map always matches the engine; the inputs listed under each node are the
// actual fields the scorers read (atlas/lenses/compute/*.py). A top-down tree: Composite → 6 lenses.
import type { LensWeightMap } from '@/lib/v6/sectorScore'
import type { MethodologyThresholds } from '@/lib/queries/v6/methodology'

type Leaf = { name: string; inputs: string; weight?: string }
type Lens = {
  key: keyof LensWeightMap | 'valuation' | 'policy'
  name: string
  tint: string          // accent colour for the lane
  what: string          // one-line plain-English read
  context?: boolean     // valuation/policy are always context (never in the blend)
  leaves: Leaf[]
}

// Accent hues chosen to read on both the light and dark themes. The blend weight per lens is NOT
// hard-coded here — it comes from the live atlas_thresholds weights (props), so a retune in the
// /thresholds panel moves this page too.
const LENSES: Lens[] = [
  {
    key: 'technical', name: 'Technical', tint: '#2D63D8',
    what: 'Price action and momentum versus the market.',
    leaves: [
      { name: 'Trend', inputs: 'EMA 21/50/200 alignment · price vs EMA-200 · RSI-14 · 1-week return' },
      { name: 'Relative Strength', inputs: 'RS vs Nifty 500 (1m·3m·6m·12m) · RS vs own sector' },
      { name: 'Volatility Contraction', inputs: 'ATR-14 as % of price · Bollinger-band squeeze' },
      { name: 'Volume', inputs: '30d / 60d volume ratio · 52-week price position' },
    ],
  },
  {
    key: 'fundamental', name: 'Fundamental', tint: '#0C8A56',
    what: 'Business quality read straight from the financials.',
    leaves: [
      { name: 'Profitability', inputs: 'ROE · ROCE · net margin' },
      { name: 'Margins', inputs: 'Operating margin · net margin' },
      { name: 'Growth', inputs: 'Revenue YoY · EPS YoY' },
      { name: 'Balance Sheet', inputs: 'Debt / equity · current & quick ratio' },
      { name: 'Operating Leverage', inputs: 'Growth × margin expansion × low debt' },
    ],
  },
  {
    key: 'flow', name: 'Flow', tint: '#0E8C8C',
    what: 'Who is actually buying — the smart-money footprint.',
    leaves: [
      { name: 'Promoter', weight: '70%', inputs: 'Insider open-market buys/sells · pledge changes · promoter holding %' },
      { name: 'Institutional / Smart Money', weight: '30%', inputs: 'Mutual-fund month-over-month delta · bulk deals · FII/DII shareholding QoQ' },
      { name: 'Accumulation', weight: '25%', inputs: 'Delivery % level & trend · up/down-day asymmetry' },
    ],
  },
  {
    key: 'catalyst', name: 'Catalyst', tint: '#B07A09',
    what: 'What just changed — read from exchange filings.',
    leaves: [
      { name: 'Earnings & Momentum', weight: '55%', inputs: 'Credit-rating actions · dividends · order wins · press releases' },
      { name: 'Capital Actions', weight: '30%', inputs: 'Acquisitions · buybacks · bonus / split' },
      { name: 'Governance', weight: '15%', inputs: 'Management & auditor changes · ESOP' },
    ],
  },
  {
    key: 'valuation', name: 'Valuation', tint: '#7A5AF0', context: true,
    what: 'Not part of the blend — it tunes the final score up or down.',
    leaves: [
      { name: 'PE vs Sector', inputs: 'PE relative to the sector median' },
      { name: 'Absolute PE', inputs: 'Trailing-twelve-month PE' },
      { name: 'Price-to-Book', inputs: 'P/B' },
      { name: 'EV / EBITDA', inputs: 'Enterprise value / EBITDA' },
      { name: '52-week Position', inputs: 'Where price sits in its 52-week range' },
    ],
  },
  {
    key: 'policy', name: 'Policy', tint: '#6B7280', context: true,
    what: 'Government tailwind, sector-matched. Shown for context, not scored.',
    leaves: [
      { name: 'Government Tailwind', inputs: 'Match vs 15 policy schemes — PLI Electronics/Pharma/Auto, Defense, Semiconductors, Green Hydrogen, FAME-III EV …' },
    ],
  },
]

// Live weight (fraction 0–1) for a lens, 0 for the context lenses.
function lensWeight(key: Lens['key'], w: LensWeightMap): number {
  return key === 'valuation' || key === 'policy' ? 0 : (w[key] ?? 0)
}
// Display label for a lens's blend share, from the live weight.
function weightLabel(lens: Lens, w: LensWeightMap): string {
  if (lens.key === 'valuation') return '× multiplier'
  if (lens.key === 'policy') return 'context'
  const v = lensWeight(lens.key, w)
  return v > 0 ? `${Math.round(v * 100)}%` : '0% · context'
}

function LensColumn({ lens, w }: { lens: Lens; w: LensWeightMap }) {
  const scored = !lens.context && lensWeight(lens.key, w) > 0
  return (
    <div className="flex w-[210px] shrink-0 flex-col">
      {/* connector stub up to the rail */}
      <div className="mx-auto h-4 w-px" style={{ background: lens.tint }} />
      {/* lens trunk card */}
      <div
        className="rounded-tile border bg-surface-panel px-3 py-2.5 shadow-tile"
        style={{ borderColor: lens.tint, borderTopWidth: 3 }}
      >
        <div className="flex items-baseline justify-between gap-2">
          <span className="font-display text-[15px] font-bold text-txt-1">{lens.name}</span>
          <span className="font-num text-[15px] font-bold tabular-nums" style={{ color: lens.tint }}>{weightLabel(lens, w)}</span>
        </div>
        <div className="mt-0.5 font-num text-[9px] uppercase tracking-wider" style={{ color: lens.tint }}>
          {scored ? 'Scored lens' : 'Context · not in blend'}
        </div>
        <div className="mt-1 font-sans text-[11px] leading-snug text-txt-2">{lens.what}</div>
      </div>
      {/* sub-component leaves */}
      <div className="relative mt-2 flex flex-col gap-1.5 pl-3">
        {/* vertical branch line */}
        <div className="absolute bottom-2 left-0 top-0 w-px" style={{ background: `${lens.tint}66` }} />
        {lens.leaves.map((leaf) => (
          <div key={leaf.name} className="relative rounded-tile border border-edge-hair bg-surface-raised px-2.5 py-1.5">
            {/* horizontal tick into the branch line */}
            <div className="absolute -left-3 top-1/2 h-px w-3" style={{ background: `${lens.tint}66` }} />
            <div className="flex items-baseline justify-between gap-1">
              <span className="font-sans text-[11.5px] font-semibold text-txt-1">{leaf.name}</span>
              {leaf.weight && (
                <span className="shrink-0 rounded-full px-1.5 font-num text-[9px] tabular-nums" style={{ background: `${lens.tint}1f`, color: lens.tint }}>{leaf.weight}</span>
              )}
            </div>
            <div className="mt-0.5 font-sans text-[10px] leading-snug text-txt-3">{leaf.inputs}</div>
          </div>
        ))}
      </div>
    </div>
  )
}

// Dynamic root-blend string from the live weights — only the lenses that carry weight.
function blendString(w: LensWeightMap): string {
  const parts = ([
    ['Technical', w.technical], ['Fundamental', w.fundamental], ['Flow', w.flow], ['Catalyst', w.catalyst],
  ] as const).filter(([, x]) => x > 0).map(([n, x]) => `${x.toFixed(2)}·${n}`)
  return parts.length ? parts.join(' + ') : '—'
}

export function LensMindMap({ weights, thresholds }: { weights: LensWeightMap; thresholds: MethodologyThresholds }) {
  const w = weights
  const { convergence: cv, conviction: cn } = thresholds
  const scoredCount = ([w.technical, w.fundamental, w.flow, w.catalyst]).filter((x) => x > 0).length
  return (
    <section className="px-8 py-12 border-b border-edge-hair">
      <div className="mb-1 font-num text-[11px] uppercase tracking-[0.2em] text-txt-3">The score, decomposed</div>
      <h2 className="font-display text-[26px] font-bold tracking-tight text-txt-1">What goes into every lens</h2>
      <p className="mt-2 max-w-[760px] font-sans text-[14px] leading-relaxed text-txt-2">
        Every conviction score is built from six lenses, and each lens from its own sub-components — all computed
        per stock, every night, and stored so you can trace any number back to its inputs. {scoredCount === 2
          ? 'Two lenses form the blend today'
          : `${scoredCount} lenses form the blend today`}; the rest are context. Weights are live from the
        thresholds panel.
      </p>

      {/* root → branches → lenses → sub-components */}
      <div className="mt-8 overflow-x-auto">
        <div className="min-w-[1180px]">
          {/* root node */}
          <div className="flex justify-center">
            <div className="rounded-panel border border-edge-rule bg-surface-panel px-5 py-3 text-center shadow-tile">
              <div className="font-display text-[17px] font-bold text-txt-1">Conviction Composite</div>
              <div className="font-num text-[11px] tabular-nums text-txt-3">0–100, per stock</div>
              <div className="mt-1 font-num text-[11px] tabular-nums text-txt-2">{blendString(w)}</div>
            </div>
          </div>
          {/* drop from root to the horizontal rail */}
          <div className="mx-auto h-4 w-px bg-edge-rule" />
          {/* horizontal rail spanning the lens columns */}
          <div className="mx-auto h-px bg-edge-rule" style={{ width: 'calc(100% - 105px)' }} />
          {/* lens columns */}
          <div className="flex justify-between gap-3">
            {LENSES.map((lens) => <LensColumn key={lens.key} lens={lens} w={w} />)}
          </div>
        </div>
      </div>

      {/* how the lenses combine into a call — live values from atlas_thresholds */}
      <div className="mt-8 grid grid-cols-1 gap-3 md:grid-cols-3">
        <div className="rounded-tile border-l-2 border-brand bg-surface-raised px-3.5 py-3">
          <div className="font-num text-[10px] uppercase tracking-wider text-txt-3">Convergence boost</div>
          <div className="mt-1 font-sans text-[12px] leading-snug text-txt-2">
            When lenses agree (each ≥ {cv.agreeMin}), the score is boosted: 2 lenses ×{cv.boost2.toFixed(2)} ·
            3 lenses ×{cv.boost3.toFixed(2)} · 4 lenses ×{cv.boost4plus.toFixed(2)}.
          </div>
        </div>
        <div className="rounded-tile border-l-2 border-sig-warn bg-surface-raised px-3.5 py-3">
          <div className="font-num text-[10px] uppercase tracking-wider text-txt-3">Valuation multiplier</div>
          <div className="mt-1 font-sans text-[12px] leading-snug text-txt-2">
            Deep value ×1.15 · Cheap ×1.08 · Fair ×1.00 · Expensive ×0.90 · Overvalued ×0.75.
          </div>
        </div>
        <div className="rounded-tile border-l-2 border-sig-pos bg-surface-raised px-3.5 py-3">
          <div className="font-num text-[10px] uppercase tracking-wider text-txt-3">Conviction tier</div>
          <div className="mt-1 font-sans text-[12px] leading-snug text-txt-2">
            HIGHEST ≥ {cn.highestScore} ({cn.highestLayers}+ lenses) · HIGH ≥ {cn.highScore} ({cn.highLayers}+) ·
            MEDIUM ≥ {cn.mediumScore} · WATCH ≥ {cn.watchScore} · below that, no call.
          </div>
        </div>
      </div>
    </section>
  )
}
