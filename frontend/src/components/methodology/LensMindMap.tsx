// LensMindMap — the conviction score decomposed into its real lenses and sub-components.
// Every node here is REAL and traceable: the six lenses and their sub-components are the columns
// stored in foundation_staging.atlas_lens_scores_daily (tech_trend, fund_profitability, …); the
// weights are the live values in atlas.atlas_thresholds (lens_weight_* and the flow/catalyst
// sub-weights); the inputs listed under each node are the actual fields the scorers read
// (atlas/lenses/compute/*.py). A top-down decision tree: Composite → 6 lenses → sub-components.

type Leaf = { name: string; inputs: string; weight?: string }
type Lens = {
  key: string
  name: string
  weight: string        // share of the composite (or the context role)
  role: 'scored' | 'context'
  tint: string          // accent colour for the lane
  what: string          // one-line plain-English read
  leaves: Leaf[]
}

// Accent hues chosen to read on both the light and dark themes.
const LENSES: Lens[] = [
  {
    key: 'technical', name: 'Technical', weight: '30%', role: 'scored', tint: '#2D63D8',
    what: 'Price action and momentum versus the market.',
    leaves: [
      { name: 'Trend', inputs: 'EMA 21/50/200 alignment · price vs EMA-200 · RSI-14 · 1-week return' },
      { name: 'Relative Strength', inputs: 'RS vs Nifty 500 (1m·3m·6m·12m) · RS vs own sector' },
      { name: 'Volatility Contraction', inputs: 'ATR-14 as % of price · Bollinger-band squeeze' },
      { name: 'Volume', inputs: '30d / 60d volume ratio · 52-week price position' },
    ],
  },
  {
    key: 'fundamental', name: 'Fundamental', weight: '25%', role: 'scored', tint: '#0C8A56',
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
    key: 'flow', name: 'Flow', weight: '25%', role: 'scored', tint: '#0E8C8C',
    what: 'Who is actually buying — the smart-money footprint.',
    leaves: [
      { name: 'Promoter', weight: '70%', inputs: 'Insider open-market buys/sells · pledge changes · promoter holding %' },
      { name: 'Institutional / Smart Money', weight: '30%', inputs: 'Mutual-fund month-over-month delta · bulk deals · FII/DII shareholding QoQ' },
      { name: 'Accumulation', weight: '25%', inputs: 'Delivery % level & trend · up/down-day asymmetry' },
    ],
  },
  {
    key: 'catalyst', name: 'Catalyst', weight: '20%', role: 'scored', tint: '#B07A09',
    what: 'What just changed — read from exchange filings.',
    leaves: [
      { name: 'Earnings & Momentum', weight: '55%', inputs: 'Credit-rating actions · dividends · order wins · press releases' },
      { name: 'Capital Actions', weight: '30%', inputs: 'Acquisitions · buybacks · bonus / split' },
      { name: 'Governance', weight: '15%', inputs: 'Management & auditor changes · ESOP' },
    ],
  },
  {
    key: 'valuation', name: 'Valuation', weight: '× multiplier', role: 'context', tint: '#7A5AF0',
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
    key: 'policy', name: 'Policy', weight: 'context', role: 'context', tint: '#6B7280',
    what: 'Government tailwind, sector-matched. Shown for context, not scored.',
    leaves: [
      { name: 'Government Tailwind', inputs: 'Match vs 15 policy schemes — PLI Electronics/Pharma/Auto, Defense, Semiconductors, Green Hydrogen, FAME-III EV …' },
    ],
  },
]

function LensColumn({ lens }: { lens: Lens }) {
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
          <span className="font-num text-[15px] font-bold tabular-nums" style={{ color: lens.tint }}>{lens.weight}</span>
        </div>
        <div className="mt-0.5 font-num text-[9px] uppercase tracking-wider" style={{ color: lens.tint }}>
          {lens.role === 'scored' ? 'Scored lens' : 'Context · not in blend'}
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

export function LensMindMap() {
  return (
    <section className="px-8 py-12 border-b border-edge-hair">
      <div className="mb-1 font-num text-[11px] uppercase tracking-[0.2em] text-txt-3">The score, decomposed</div>
      <h2 className="font-display text-[26px] font-bold tracking-tight text-txt-1">What goes into every lens</h2>
      <p className="mt-2 max-w-[760px] font-sans text-[14px] leading-relaxed text-txt-2">
        Every conviction score is built from six lenses, and each lens from its own sub-components — all computed
        per stock, every night, and stored so you can trace any number back to its inputs. Four lenses form the
        blend; Valuation and Policy are context.
      </p>

      {/* root → branches → lenses → sub-components */}
      <div className="mt-8 overflow-x-auto">
        <div className="min-w-[1180px]">
          {/* root node */}
          <div className="flex justify-center">
            <div className="rounded-panel border border-edge-rule bg-surface-panel px-5 py-3 text-center shadow-tile">
              <div className="font-display text-[17px] font-bold text-txt-1">Conviction Composite</div>
              <div className="font-num text-[11px] tabular-nums text-txt-3">0–100, per stock</div>
              <div className="mt-1 font-num text-[11px] tabular-nums text-txt-2">
                0.30·Technical + 0.25·Fundamental + 0.25·Flow + 0.20·Catalyst
              </div>
            </div>
          </div>
          {/* drop from root to the horizontal rail */}
          <div className="mx-auto h-4 w-px bg-edge-rule" />
          {/* horizontal rail spanning the lens columns */}
          <div className="mx-auto h-px bg-edge-rule" style={{ width: 'calc(100% - 105px)' }} />
          {/* lens columns */}
          <div className="flex justify-between gap-3">
            {LENSES.map((lens) => <LensColumn key={lens.key} lens={lens} />)}
          </div>
        </div>
      </div>

      {/* how the lenses combine into a call */}
      <div className="mt-8 grid grid-cols-1 gap-3 md:grid-cols-3">
        <div className="rounded-tile border-l-2 border-brand bg-surface-raised px-3.5 py-3">
          <div className="font-num text-[10px] uppercase tracking-wider text-txt-3">Convergence boost</div>
          <div className="mt-1 font-sans text-[12px] leading-snug text-txt-2">
            When lenses agree (each ≥ 40), the score is boosted: 2 lenses ×1.06 · 3 lenses ×1.10 · 4 lenses ×1.15.
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
            HIGHEST ≥ 70 (3+ lenses) · HIGH ≥ 58 (2+) · MEDIUM ≥ 45 · WATCH ≥ 30 · below that, no call.
          </div>
        </div>
      </div>
    </section>
  )
}
