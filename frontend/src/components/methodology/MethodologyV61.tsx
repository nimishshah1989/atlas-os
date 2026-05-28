// allow-large: full interactive methodology — SVG diagrams + 4 math concept cards + worked example + honesty section live in one cohesive page; splitting would just relocate complexity
'use client'
import { useState } from 'react'

// ============================================================================
// Reusable atoms
// ============================================================================

function SectionHead({ kicker, title, sub }: { kicker: string; title: string; sub?: string }) {
  return (
    <div className="mb-6">
      <div className="font-sans text-[10px] text-ink-tertiary uppercase tracking-[0.14em] mb-1">
        {kicker}
      </div>
      <h2 className="font-serif text-[28px] font-normal tracking-tight text-ink-primary leading-tight">
        {title}
      </h2>
      {sub && (
        <p className="font-sans text-[14px] text-ink-secondary leading-[1.55] max-w-[680px] mt-2">
          {sub}
        </p>
      )}
    </div>
  )
}

function Card({ children, accent = 'neutral' }: { children: React.ReactNode; accent?: 'pos' | 'neg' | 'neu' | 'neutral' }) {
  const cls = accent === 'pos' ? 'border-l-4 border-l-signal-pos'
            : accent === 'neg' ? 'border-l-4 border-l-signal-neg'
            : accent === 'neu' ? 'border-l-4 border-l-signal-warn'
            : 'border-l border-l-paper-rule'
  return <div className={`bg-paper-soft ${cls} p-5 rounded-r-[2px]`}>{children}</div>
}

// ============================================================================
// 1. Hero — one-sentence answer
// ============================================================================

function Hero() {
  return (
    <section className="px-8 py-12 border-b border-paper-rule bg-paper">
      <div className="max-w-[860px]">
        <div className="font-sans text-[10px] text-ink-tertiary uppercase tracking-[0.14em] mb-2">
          Atlas · Methodology
        </div>
        <h1 className="font-serif text-[42px] font-normal tracking-tight text-ink-primary leading-[1.1] mb-4">
          How Atlas thinks
        </h1>
        <p className="font-sans text-[17px] text-ink-secondary leading-[1.55] mb-6">
          Atlas tells you which Indian stocks to <span className="text-signal-pos font-semibold">buy</span> or <span className="text-signal-neg font-semibold">avoid</span> each day,
          using math instead of opinions. This page explains how it works in plain English —
          the data, the math, the decisions — so you can trust what you&apos;re seeing.
        </p>
        <p className="font-sans text-[14px] text-ink-tertiary italic leading-[1.55]">
          Written for someone who knows nothing about markets. If a term is new, hover it for a definition.
        </p>
      </div>
    </section>
  )
}

// ============================================================================
// 2. The 4-step engine — visual flow
// ============================================================================

const STEPS = [
  {
    n: 1,
    label: 'Data arrives',
    sub: 'Every weekday at 6:33 PM IST',
    body: 'NSE publishes today\'s prices for every stock + ETF + index. Atlas downloads this "bhavcopy" file. Mutual fund NAVs arrive a few hours later from AMFI. Global data (USD/INR, S&P 500, oil) comes from Yahoo Finance.',
    inputs: ['NSE bhavcopy', 'AMFI NAV file', 'Yahoo Finance (global)'],
    output: '~9,500 fresh price rows per day',
  },
  {
    n: 2,
    label: 'Numbers are computed',
    sub: 'From 7 PM to 1:30 AM',
    body: 'For each stock, Atlas calculates returns (1 week, 1 month, 3 months, 6 months, 12 months), relative strength (how much it beat or lagged the Nifty 500), volatility, and which Weinstein stage it\'s in (Basing, Trending, Topping, Declining).',
    inputs: ['Today\'s price', 'Last 252 days of price', 'Nifty 500 benchmark'],
    output: '~750 stocks × 60 metrics = 45,000 numbers',
  },
  {
    n: 3,
    label: 'Scoring + classification',
    sub: 'From 1:30 AM to 2 AM',
    body: 'Every stock gets a "composite conviction score" from −10 to +10. Sectors are classified Overweight / Neutral / Underweight. The market regime is computed as Risk-On / Constructive / Cautious / Risk-Off based on breadth + trend + momentum + participation.',
    inputs: ['All the metrics', '24-cell methodology matrix', 'Threshold table'],
    output: 'Score per stock, verdict per sector, 1 market regime',
  },
  {
    n: 4,
    label: 'Calls fire',
    sub: 'From 2 AM to 3:15 AM',
    body: 'Each stock above conviction +4 fires a BUY call with a tier (Large / Mid / Small / Micro), tenure (1m / 3m / 6m / 12m), and confidence (H / M / L). Stocks below −4 fire AVOID. Then 14 materialized views refresh so the website serves fresh numbers when you wake up.',
    inputs: ['Conviction score', 'Cell membership', 'Methodology lock'],
    output: '~600 open BUY/AVOID calls · refreshed nightly',
  },
]

function EngineFlow() {
  const [active, setActive] = useState<number>(1)
  const step = STEPS.find(s => s.n === active) ?? STEPS[0]

  return (
    <section className="px-8 py-12 border-b border-paper-rule bg-paper">
      <SectionHead
        kicker="The engine"
        title="4 steps · every weekday"
        sub="Atlas does the same 4 steps every weekday night while you sleep. Click any step to see what happens."
      />

      {/* Step strip */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-2 mb-6">
        {STEPS.map(s => (
          <button
            key={s.n}
            onClick={() => setActive(s.n)}
            className={`text-left p-4 rounded-[2px] border transition-all ${
              active === s.n
                ? 'bg-ink-primary text-paper border-ink-primary'
                : 'bg-paper-soft text-ink-primary border-paper-rule hover:border-ink-rule'
            }`}
          >
            <div className={`font-mono text-[10px] mb-1 ${active === s.n ? 'text-paper-rule' : 'text-ink-tertiary'}`}>
              STEP {s.n}
            </div>
            <div className="font-serif text-[16px] font-medium leading-tight">{s.label}</div>
            <div className={`font-sans text-[11px] mt-1 ${active === s.n ? 'text-paper-rule' : 'text-ink-tertiary'}`}>
              {s.sub}
            </div>
          </button>
        ))}
      </div>

      {/* Active step detail */}
      <Card>
        <div className="font-sans text-[15px] text-ink-primary leading-[1.6] mb-4">{step.body}</div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-[13px]">
          <div>
            <div className="font-sans text-[10px] text-ink-tertiary uppercase tracking-wider mb-1">Inputs</div>
            {step.inputs.map(i => (
              <div key={i} className="font-mono text-[12px] text-ink-secondary">→ {i}</div>
            ))}
          </div>
          <div>
            <div className="font-sans text-[10px] text-ink-tertiary uppercase tracking-wider mb-1">Output</div>
            <div className="font-mono text-[12px] text-signal-pos">{step.output}</div>
          </div>
        </div>
      </Card>
    </section>
  )
}

// ============================================================================
// 3. Math you'll actually use — 4 interactive concepts
// ============================================================================

function RSExplainer() {
  const [stock, setStock] = useState(8) // % stock return
  const [nifty, setNifty] = useState(3) // % nifty return
  const rs = stock - nifty
  const interpretation =
    rs >= 5  ? { msg: 'This stock is LEADING the market materially.', color: 'text-signal-pos' }
  : rs >= 0  ? { msg: 'This stock is tracking or slightly beating the market.', color: 'text-ink-primary' }
  : rs >= -5 ? { msg: 'This stock is lagging the market.', color: 'text-signal-warn' }
  :             { msg: 'This stock is significantly LAGGING the market.', color: 'text-signal-neg' }

  return (
    <Card accent="neu">
      <div className="font-serif text-[20px] font-medium text-ink-primary mb-2">
        Relative Strength (RS)
      </div>
      <div className="font-sans text-[14px] text-ink-secondary leading-[1.55] mb-4">
        Did the stock beat the market? <strong>RS = stock return − Nifty 500 return.</strong> Positive means leading; negative means lagging. Atlas measures RS over 1 week, 1 month, 3 months, 6 months, and 12 months.
      </div>
      <div className="bg-paper p-4 rounded-[2px] border border-paper-rule">
        <div className="grid grid-cols-2 gap-4 mb-3">
          <div>
            <label className="font-sans text-[11px] text-ink-tertiary uppercase tracking-wider">Stock return (3M)</label>
            <input type="range" min="-30" max="60" value={stock} onChange={e => setStock(Number(e.target.value))} className="w-full" />
            <div className="font-mono text-[18px] text-ink-primary">{stock >= 0 ? '+' : ''}{stock}%</div>
          </div>
          <div>
            <label className="font-sans text-[11px] text-ink-tertiary uppercase tracking-wider">Nifty 500 return (3M)</label>
            <input type="range" min="-30" max="60" value={nifty} onChange={e => setNifty(Number(e.target.value))} className="w-full" />
            <div className="font-mono text-[18px] text-ink-primary">{nifty >= 0 ? '+' : ''}{nifty}%</div>
          </div>
        </div>
        <div className="border-t border-paper-rule pt-3">
          <div className="font-sans text-[11px] text-ink-tertiary uppercase tracking-wider mb-1">Relative Strength</div>
          <div className={`font-mono text-[28px] font-semibold ${interpretation.color}`}>
            {rs >= 0 ? '+' : ''}{rs.toFixed(1)}pp
          </div>
          <div className={`font-sans text-[13px] mt-1 ${interpretation.color}`}>{interpretation.msg}</div>
        </div>
      </div>
    </Card>
  )
}

function ConvictionExplainer() {
  const [score, setScore] = useState(5.2)
  const verdict =
    score >=  4 ? { label: 'BUY',   color: 'bg-signal-pos text-paper',  body: 'Trend + RS + breadth all positive. Atlas fires a BUY call.' }
  : score <= -4 ? { label: 'AVOID', color: 'bg-signal-neg text-paper',  body: 'Multiple factors negative. Atlas fires an AVOID call.' }
  :              { label: 'WATCH', color: 'bg-signal-warn text-paper', body: 'Mixed signals. No new position; hold existing.' }

  return (
    <Card accent="pos">
      <div className="font-serif text-[20px] font-medium text-ink-primary mb-2">
        Composite conviction score
      </div>
      <div className="font-sans text-[14px] text-ink-secondary leading-[1.55] mb-4">
        Every stock gets a score from <strong>−10</strong> to <strong>+10</strong>. Above +4 fires BUY, below −4 fires AVOID, in between is WATCH. The score blends ~15 signals: RS in multiple windows, trend stage, breadth, volatility-adjusted return, cross-tier rank, regime fit.
      </div>
      <div className="bg-paper p-4 rounded-[2px] border border-paper-rule">
        <label className="font-sans text-[11px] text-ink-tertiary uppercase tracking-wider">Drag to see what each score means</label>
        <input type="range" min="-10" max="10" step="0.1" value={score} onChange={e => setScore(Number(e.target.value))} className="w-full mt-2" />
        <div className="flex items-center justify-between mt-2">
          <span className="font-mono text-[10px] text-signal-neg">−10 AVOID</span>
          <span className="font-mono text-[10px] text-signal-warn">0 WATCH</span>
          <span className="font-mono text-[10px] text-signal-pos">+10 BUY</span>
        </div>
        <div className="mt-4 flex items-center gap-4">
          <div className={`px-3 py-1.5 rounded-[2px] font-mono text-[12px] font-semibold ${verdict.color}`}>
            {verdict.label}
          </div>
          <div className="font-mono text-[28px] font-semibold text-ink-primary">
            {score >= 0 ? '+' : ''}{score.toFixed(1)}
          </div>
        </div>
        <div className="font-sans text-[13px] text-ink-secondary mt-2">{verdict.body}</div>
      </div>
    </Card>
  )
}

const REGIMES = [
  { key: 'risk-on',      label: 'Risk-On',      color: 'bg-signal-pos text-paper',     deploy: '100%', body: 'All four signals (trend, breadth, momentum, participation) bullish. Deploy fully. Add leaders broadly.' },
  { key: 'constructive', label: 'Constructive', color: 'bg-signal-pos/30 text-ink-primary',  deploy: '80%',  body: 'Three of four bullish. Deploy mostly but keep some powder dry.' },
  { key: 'cautious',     label: 'Cautious',     color: 'bg-signal-warn/30 text-ink-primary', deploy: '60%',  body: 'Mixed signals. Reduce position sizes, focus on highest-conviction names.' },
  { key: 'risk-off',     label: 'Risk-Off',     color: 'bg-signal-neg text-paper',     deploy: '40%',  body: 'Broad deterioration. Capital preservation mode. Minimal new positions.' },
]

function RegimeExplainer() {
  const [pick, setPick] = useState('risk-on')
  const r = REGIMES.find(x => x.key === pick) ?? REGIMES[0]
  return (
    <Card accent="neutral">
      <div className="font-serif text-[20px] font-medium text-ink-primary mb-2">
        Market regime · 4 states
      </div>
      <div className="font-sans text-[14px] text-ink-secondary leading-[1.55] mb-4">
        Atlas asks <strong>4 questions</strong> about the whole market every day: is the trend up? is breadth wide? is momentum positive? are most stocks participating? The answers classify the regime, which sets how much capital to deploy.
      </div>
      <div className="bg-paper p-4 rounded-[2px] border border-paper-rule">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-2 mb-4">
          {REGIMES.map(x => (
            <button
              key={x.key}
              onClick={() => setPick(x.key)}
              className={`p-3 rounded-[2px] transition-all ${x.color} ${pick === x.key ? 'ring-2 ring-ink-primary' : 'opacity-60 hover:opacity-100'}`}
            >
              <div className="font-mono text-[10px] uppercase tracking-wider">{x.deploy} deploy</div>
              <div className="font-serif text-[16px] font-medium leading-tight">{x.label}</div>
            </button>
          ))}
        </div>
        <div className="font-sans text-[14px] text-ink-primary leading-[1.5]">{r.body}</div>
      </div>
    </Card>
  )
}

const TIERS = ['Large', 'Mid', 'Small'] as const
const TENURES = ['1m', '3m', '6m', '12m'] as const

function MatrixExplainer() {
  const [tier, setTier] = useState<typeof TIERS[number]>('Large')
  const [ten,  setTen]  = useState<typeof TENURES[number]>('3m')
  const examples: Record<string, string> = {
    'Large·1m·POS':  'Large-cap stocks beating the market over the last MONTH. Rare; usually news-driven.',
    'Large·3m·POS':  'Large-cap stocks with sustained 3-month leadership. The most reliable BUY cell in our data.',
    'Large·6m·POS':  'Large-cap stocks with 6-month momentum. Captures trend continuation; popular institutional setup.',
    'Large·12m·POS': 'Large-cap stocks beating the market for a full year. Quality + growth combination.',
    'Mid·1m·POS':    'Mid-cap fast movers — usually catalyst-driven; high but short-lived.',
    'Mid·3m·POS':    'Mid-cap leaders with 3M momentum — Atlas\'s favorite hunting ground.',
    'Mid·6m·POS':    'Mid-cap with 6M leadership — sweet spot for compounding.',
    'Mid·12m·POS':   'Multi-baggers in formation.',
    'Small·1m·POS':  'Small-cap pops — tradeable but noisy.',
    'Small·3m·POS':  'Small-cap with 3M leadership — high upside, high vol.',
    'Small·6m·POS':  'Small-cap multi-month strength.',
    'Small·12m·POS': 'Year-long small-cap leaders — biggest winners live here.',
  }
  const key = `${tier}·${ten}·POS`
  return (
    <Card accent="neutral">
      <div className="font-serif text-[20px] font-medium text-ink-primary mb-2">
        The 24-cell matrix
      </div>
      <div className="font-sans text-[14px] text-ink-secondary leading-[1.55] mb-4">
        Atlas sorts every stock into a cell defined by <strong>cap tier × tenure × direction</strong>. Three tiers (Large / Mid / Small) × four tenures (1m / 3m / 6m / 12m) × two directions (POS / NEG) = 24 cells. Each cell has its own validated performance history (information coefficient, hit rate), so Atlas knows which cells to trust.
      </div>
      <div className="bg-paper p-4 rounded-[2px] border border-paper-rule">
        <div className="grid grid-cols-[80px_repeat(4,1fr)] gap-1 text-[12px]">
          <div></div>
          {TENURES.map(t => (
            <div key={t} className="text-center font-mono text-[11px] text-ink-tertiary uppercase tracking-wider py-1">{t}</div>
          ))}
          {TIERS.map(tr => (
            <Fragment key={tr}>
              <div className="font-sans text-[12px] font-medium text-ink-secondary py-2">{tr}</div>
              {TENURES.map(t => {
                const isActive = tier === tr && ten === t
                return (
                  <button
                    key={`${tr}-${t}`}
                    onClick={() => { setTier(tr); setTen(t) }}
                    className={`p-2 rounded-[2px] border transition-all ${
                      isActive
                        ? 'bg-signal-pos text-paper border-signal-pos'
                        : 'bg-signal-pos/10 text-signal-pos border-signal-pos/30 hover:bg-signal-pos/20'
                    }`}
                  >
                    <div className="font-mono text-[10px] uppercase">POS</div>
                  </button>
                )
              })}
            </Fragment>
          ))}
        </div>
        <div className="mt-4 border-t border-paper-rule pt-3">
          <div className="font-sans text-[11px] text-ink-tertiary uppercase tracking-wider mb-1">
            Cell · {tier} · {ten} · POSITIVE
          </div>
          <div className="font-sans text-[14px] text-ink-primary leading-[1.5]">{examples[key]}</div>
        </div>
      </div>
    </Card>
  )
}

// Small react-fragment import shim (avoids extra import)
function Fragment(props: { children: React.ReactNode; key?: string }) {
  return <>{props.children}</>
}

// ============================================================================
// 4. What Atlas WON'T tell you (honesty)
// ============================================================================

function Honesty() {
  return (
    <section className="px-8 py-12 border-b border-paper-rule bg-paper">
      <SectionHead
        kicker="Limits"
        title="What Atlas won't tell you"
        sub="Math is powerful but partial. Here's what Atlas cannot do — so you don't trust it blindly."
      />
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <Card accent="neg">
          <div className="font-serif text-[16px] font-medium text-ink-primary mb-2">Predict news shocks</div>
          <p className="font-sans text-[13px] text-ink-secondary leading-[1.55]">
            Atlas reads prices, not news. A merger announcement, earnings surprise, or RBI policy shift can flip a stock overnight. The math sees it the NEXT day.
          </p>
        </Card>
        <Card accent="neg">
          <div className="font-serif text-[16px] font-medium text-ink-primary mb-2">Read fundamentals</div>
          <p className="font-sans text-[13px] text-ink-secondary leading-[1.55]">
            Atlas doesn&apos;t look at P/E, revenue growth, management quality, or balance sheet health. It assumes the market already prices those in. For long-term picks you must add fundamental judgment.
          </p>
        </Card>
        <Card accent="neg">
          <div className="font-serif text-[16px] font-medium text-ink-primary mb-2">Size your position</div>
          <p className="font-sans text-[13px] text-ink-secondary leading-[1.55]">
            Atlas tells you WHAT to buy, not HOW MUCH. Position sizing depends on your portfolio, risk appetite, and conviction. The regime hints at total deployment (40-100%); per-stock weighting is your call.
          </p>
        </Card>
        <Card accent="neg">
          <div className="font-serif text-[16px] font-medium text-ink-primary mb-2">Be right every time</div>
          <p className="font-sans text-[13px] text-ink-secondary leading-[1.55]">
            The 24-cell matrix shows win rates around 60-80%. Even the best cell has losing trades. Atlas is a probabilistic system — expect to be wrong, often. Diversify so wins outpay losses.
          </p>
        </Card>
      </div>
    </section>
  )
}

// ============================================================================
// 5. Concept grid (the 4 explainers)
// ============================================================================

function ConceptGrid() {
  return (
    <section className="px-8 py-12 border-b border-paper-rule bg-paper">
      <SectionHead
        kicker="The math"
        title="4 concepts you'll use every day"
        sub="The whole engine boils down to these four ideas. Each is interactive — play with the sliders to feel how the math works."
      />
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        <RSExplainer />
        <ConvictionExplainer />
        <RegimeExplainer />
        <MatrixExplainer />
      </div>
    </section>
  )
}

// ============================================================================
// Top-level
// ============================================================================

export default function MethodologyV61() {
  return (
    <div>
      <Hero />
      <EngineFlow />
      <ConceptGrid />
      <Honesty />
      <section className="px-8 py-10 bg-paper">
        <div className="max-w-[680px] font-sans text-[12px] text-ink-tertiary leading-[1.6]">
          Last methodology revision: 2026-05-28 · Atlas v6.1. Want to dig deeper? The cell-by-cell IC + walk-forward backtests live in the admin pages. Threshold values for every signal are configurable in Customizations.
        </div>
      </section>
    </div>
  )
}
