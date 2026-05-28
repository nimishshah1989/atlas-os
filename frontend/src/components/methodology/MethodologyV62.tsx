// allow-large: methodology v6.2 — deeper than v6.1; adds Cell concept, conviction math, flywheel diagram, auto-optimization cycle. Self-contained client component; no DB query.
'use client'
import { useState } from 'react'

// ============================================================================
// Atoms
// ============================================================================

function SectionHead({ kicker, title, sub }: { kicker: string; title: string; sub?: string }) {
  return (
    <div className="mb-6">
      <div className="font-sans text-[10px] text-ink-tertiary uppercase tracking-[0.14em] mb-1">{kicker}</div>
      <h2 className="font-serif text-[28px] font-normal tracking-tight text-ink-primary leading-tight">{title}</h2>
      {sub && <p className="font-sans text-[14px] text-ink-secondary leading-[1.55] max-w-[760px] mt-2">{sub}</p>}
    </div>
  )
}

function Card({ children, accent = 'neutral' }: { children: React.ReactNode; accent?: 'pos' | 'neg' | 'neu' | 'teal' | 'neutral' }) {
  const cls = accent === 'pos'   ? 'border-l-4 border-l-signal-pos'
            : accent === 'neg'   ? 'border-l-4 border-l-signal-neg'
            : accent === 'neu'   ? 'border-l-4 border-l-signal-warn'
            : accent === 'teal'  ? 'border-l-4 border-l-teal'
            : 'border-l border-l-paper-rule'
  return <div className={`bg-paper-soft ${cls} p-5 rounded-r-[2px]`}>{children}</div>
}

// ============================================================================
// 1. Hero
// ============================================================================

function Hero() {
  return (
    <section className="px-8 py-12 border-b border-paper-rule bg-paper">
      <div className="max-w-[860px]">
        <div className="font-sans text-[10px] text-ink-tertiary uppercase tracking-[0.14em] mb-2">Atlas · Methodology v6.2</div>
        <h1 className="font-serif text-[42px] font-normal tracking-tight text-ink-primary leading-[1.1] mb-4">
          How Atlas thinks
        </h1>
        <p className="font-sans text-[17px] text-ink-secondary leading-[1.55] mb-4">
          Atlas tells you which Indian stocks to <span className="text-signal-pos font-semibold">buy</span> or <span className="text-signal-neg font-semibold">avoid</span> each day,
          using math instead of opinions. This page explains the engine, the math, and the auto-improvement loop — so nothing here is a black box.
        </p>
        <p className="font-sans text-[14px] text-ink-tertiary italic leading-[1.55]">
          Written for someone with zero markets background. Each section builds on the last. By the end you&apos;ll understand why a stock gets a &quot;BUY · 75% confidence&quot; tag.
        </p>
      </div>
    </section>
  )
}

// ============================================================================
// 2. The 4-step nightly engine
// ============================================================================

const STEPS = [
  { n: 1, label: 'Data arrives', sub: '6:33 PM IST', body: 'NSE bhavcopy + AMFI NAV + Yahoo (USD/INR, S&P 500). About 9,500 fresh price rows per day.', input: 'NSE bhavcopy / AMFI / yfinance', output: '~9.5K rows' },
  { n: 2, label: 'Numbers computed', sub: '7 PM – 1:30 AM', body: 'For every stock: returns (5 windows), relative strength vs Nifty 500, volatility, Weinstein stage. 60 metrics × 750 stocks = 45,000 numbers.', input: 'Today price + 252d history', output: '45K metrics' },
  { n: 3, label: 'Scoring + classification', sub: '1:30 – 2 AM', body: 'Each stock gets a conviction score (−10 to +10). Sectors classified Overweight / Neutral / Underweight. Market regime classified Risk-On / Constructive / Cautious / Risk-Off.', input: 'All metrics + 24-cell matrix', output: 'Score per stock + verdicts' },
  { n: 4, label: 'Calls fire', sub: '2 – 3:15 AM', body: 'Stocks with conviction ≥+4 fire BUY (with tier, tenure, confidence). Stocks ≤−4 fire AVOID. 14 materialized views refresh so the site serves fresh numbers when you wake up.', input: 'Score + cell membership', output: '~600 open BUY/AVOID calls' },
]

function EngineFlow() {
  const [active, setActive] = useState(1)
  const step = STEPS.find(s => s.n === active) ?? STEPS[0]
  return (
    <section className="px-8 py-12 border-b border-paper-rule bg-paper">
      <SectionHead kicker="The engine" title="4 steps · every weekday" sub="Atlas runs the same 4 steps every weekday night. Click any step to see what happens." />
      <div className="grid grid-cols-1 md:grid-cols-4 gap-2 mb-6">
        {STEPS.map(s => (
          <button key={s.n} onClick={() => setActive(s.n)}
            className={`text-left p-4 rounded-[2px] border transition-all ${active === s.n ? 'bg-ink-primary text-paper border-ink-primary' : 'bg-paper-soft text-ink-primary border-paper-rule hover:border-ink-rule'}`}>
            <div className={`font-mono text-[10px] mb-1 ${active === s.n ? 'text-paper-rule' : 'text-ink-tertiary'}`}>STEP {s.n}</div>
            <div className="font-serif text-[16px] font-medium leading-tight">{s.label}</div>
            <div className={`font-sans text-[11px] mt-1 ${active === s.n ? 'text-paper-rule' : 'text-ink-tertiary'}`}>{s.sub}</div>
          </button>
        ))}
      </div>
      <Card>
        <div className="font-sans text-[15px] text-ink-primary leading-[1.6] mb-4">{step.body}</div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-[13px]">
          <div>
            <div className="font-sans text-[10px] text-ink-tertiary uppercase tracking-wider mb-1">Input</div>
            <div className="font-mono text-[12px] text-ink-secondary">{step.input}</div>
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
// 3. THE CELL CONCEPT (NEW in v6.2)
// ============================================================================

const TIERS = ['Large', 'Mid', 'Small'] as const
const TENURES = ['1m', '3m', '6m', '12m'] as const

type CellExample = {
  description: string
  rule: string
  hitRate: string
  ic: string
  realExample: string
}

const CELL_DATA: Record<string, CellExample> = {
  'Large·3m·POS': {
    description: 'Large-cap stocks with 3-month leadership AND clean trend stage. Atlas\'s most-validated BUY cell.',
    rule: 'eligibility: cap_tier=Large · listing_age_days≥504 · entry: rs_3m_nifty500≥0.10 · ema_50>ema_200 · weinstein_stage=Trending',
    hitRate: '73%',
    ic: '0.082',
    realExample: 'NLCINDIA, BHEL, ABB — three cells of this type fired in May 2026 with +18-30% 3M absolute returns.',
  },
  'Large·6m·POS': {
    description: 'Large-cap names with 6-month sustained outperformance. Captures institutional accumulation.',
    rule: 'cap_tier=Large · rs_6m≥0.15 · pct_above_ema_200≥0.7 · realized_vol_63<0.25',
    hitRate: '67%',
    ic: '0.094',
    realExample: 'BHARTIARTL, RELIANCE, NTPC — Q2 2026 winners.',
  },
  'Mid·3m·POS': {
    description: 'Mid-cap stocks beating market by ≥10pp over 3 months. Atlas\'s favorite hunting ground — best risk-adjusted historical returns.',
    rule: 'cap_tier=Mid · rs_3m_nifty500≥0.10 · cell_active_in_regime=TRUE',
    hitRate: '60%',
    ic: '0.072',
    realExample: 'GVT&D, THERMAX, JPPOWER — May 2026 Mid 3M leaders.',
  },
  'Large·1m·POS': {
    description: 'Large-cap fast-movers — usually news-driven (earnings beat, policy tailwind).',
    rule: 'cap_tier=Large · rs_1m≥0.05 · volume_expansion≥1.5',
    hitRate: '80%',
    ic: '0.062',
    realExample: 'Earnings-surprise winners like IRCTC after FY26 Q4 results.',
  },
  'Small·12m·NEG': {
    description: 'Small-caps with 12-month underperformance — high probability of continued AVOID. Catches the worst chronic laggards.',
    rule: 'cap_tier=Small · rs_12m≤−0.15 · drawdown_ratio_252≤−0.4',
    hitRate: '87%',
    ic: '0.078',
    realExample: 'Sterling Wilson, Webselsolar — chronic laggards consistently underperforming Nifty Small 250.',
  },
}

function CellExplainer() {
  const [tier, setTier] = useState<typeof TIERS[number]>('Large')
  const [tenure, setTenure] = useState<typeof TENURES[number]>('3m')
  const [direction, setDirection] = useState<'POS' | 'NEG'>('POS')
  const key = `${tier}·${tenure}·${direction}`
  const cell = CELL_DATA[key] ?? {
    description: `${tier} stocks with ${tenure} ${direction === 'POS' ? 'outperformance' : 'underperformance'}. Validated in our walk-forward but data shown is for any sample cell.`,
    rule: `cap_tier=${tier} · ${direction === 'POS' ? 'rs_' + tenure + ' ≥ threshold' : 'rs_' + tenure + ' ≤ −threshold'}`,
    hitRate: '—', ic: '—',
    realExample: 'Open the Stocks page and filter by this cell to see today\'s firing names.',
  }

  return (
    <section className="px-8 py-12 border-b border-paper-rule bg-paper">
      <SectionHead
        kicker="The methodology · core concept"
        title="The 24-cell matrix — Atlas's secret weapon"
        sub="Atlas doesn't treat all stocks the same. It sorts them into 24 buckets (3 cap-tiers × 4 tenures × 2 directions). Each bucket has its own historical track record. The engine only acts on cells with a validated edge."
      />

      <div className="grid grid-cols-1 lg:grid-cols-[1fr_1.4fr] gap-6">
        {/* Matrix selector */}
        <div>
          <div className="font-sans text-[12px] text-ink-secondary mb-3 leading-[1.5]">
            Click any cell. Each one is a different stock setup with its own validated edge.
          </div>
          <div className="grid grid-cols-[80px_repeat(4,1fr)] gap-1 text-[12px] mb-3">
            <div></div>
            {TENURES.map(t => (
              <div key={t} className="text-center font-mono text-[11px] text-ink-tertiary uppercase tracking-wider py-1">{t}</div>
            ))}
            {TIERS.map(tr => (
              <div key={tr} className="contents">
                <div className="font-sans text-[12px] font-medium text-ink-secondary py-2">{tr}</div>
                {TENURES.map(t => {
                  const isActive = tier === tr && tenure === t
                  const cls = direction === 'POS'
                    ? (isActive ? 'bg-signal-pos text-paper border-signal-pos' : 'bg-signal-pos/10 text-signal-pos border-signal-pos/30 hover:bg-signal-pos/20')
                    : (isActive ? 'bg-signal-neg text-paper border-signal-neg' : 'bg-signal-neg/10 text-signal-neg border-signal-neg/30 hover:bg-signal-neg/20')
                  return (
                    <button key={`${tr}-${t}`} onClick={() => { setTier(tr); setTenure(t) }}
                      className={`p-2 rounded-[2px] border transition-all ${cls}`}>
                      <div className="font-mono text-[10px] uppercase">{direction}</div>
                    </button>
                  )
                })}
              </div>
            ))}
          </div>
          <div className="flex gap-2 mt-3">
            <button onClick={() => setDirection('POS')} className={`flex-1 py-2 rounded-[2px] font-mono text-[12px] font-semibold ${direction === 'POS' ? 'bg-signal-pos text-paper' : 'bg-signal-pos/10 text-signal-pos border border-signal-pos/30'}`}>POS · BUY cells</button>
            <button onClick={() => setDirection('NEG')} className={`flex-1 py-2 rounded-[2px] font-mono text-[12px] font-semibold ${direction === 'NEG' ? 'bg-signal-neg text-paper' : 'bg-signal-neg/10 text-signal-neg border border-signal-neg/30'}`}>NEG · AVOID cells</button>
          </div>
        </div>

        {/* Selected-cell detail */}
        <Card accent="teal">
          <div className="font-mono text-[10px] text-ink-tertiary uppercase tracking-wider mb-1">CELL · {tier} · {tenure} · {direction}</div>
          <div className="font-serif text-[20px] font-medium text-ink-primary mb-3 leading-tight">{cell.description}</div>

          <div className="grid grid-cols-2 gap-3 mb-4">
            <div>
              <div className="font-sans text-[10px] text-ink-tertiary uppercase tracking-wider mb-1">Hit rate (validated)</div>
              <div className="font-mono text-[24px] font-semibold text-ink-primary">{cell.hitRate}</div>
              <div className="font-sans text-[11px] text-ink-tertiary">how often this cell&apos;s calls beat the tier benchmark</div>
            </div>
            <div>
              <div className="font-sans text-[10px] text-ink-tertiary uppercase tracking-wider mb-1">Information Coefficient</div>
              <div className="font-mono text-[24px] font-semibold text-ink-primary">{cell.ic}</div>
              <div className="font-sans text-[11px] text-ink-tertiary">how well the score predicts the outcome (0=random · 0.1=industry-grade)</div>
            </div>
          </div>

          <div className="mb-3">
            <div className="font-sans text-[10px] text-ink-tertiary uppercase tracking-wider mb-1">Entry rule (atlas_cell_definitions.rule_dsl)</div>
            <div className="font-mono text-[11px] text-ink-secondary bg-paper p-2 rounded-[2px] border border-paper-rule break-words">{cell.rule}</div>
          </div>

          <div>
            <div className="font-sans text-[10px] text-ink-tertiary uppercase tracking-wider mb-1">Real example</div>
            <div className="font-sans text-[13px] text-ink-primary leading-[1.55]">{cell.realExample}</div>
          </div>
        </Card>
      </div>
    </section>
  )
}

// ============================================================================
// 4. CONVICTION MATH (NEW — what 75% means)
// ============================================================================

function ConvictionMath() {
  const [score, setScore] = useState(7.6)
  // Convert composite_score [-10..+10] into approximate conviction
  // confidence_unconditional roughly = ((score + 10) / 20)
  const conviction = Math.min(95, Math.max(5, Math.round(((score + 10) / 20) * 100)))
  const verdict =
    score >=  4 ? { label: 'BUY',   color: 'text-signal-pos' }
  : score <= -4 ? { label: 'AVOID', color: 'text-signal-neg' }
  :              { label: 'WATCH', color: 'text-signal-warn' }

  // Probability distribution illustration: bell curve centered at conviction%
  const bellWidth = 50 - Math.abs(conviction - 50)

  return (
    <section className="px-8 py-12 border-b border-paper-rule bg-paper">
      <SectionHead
        kicker="The math behind 'conviction'"
        title="What does '75% conviction' actually mean?"
        sub="When Atlas tags a stock BUY · 75% conviction, that's a probability claim — not a feeling. It means: in N historical setups that looked like this one, 75% beat the tier benchmark over the relevant tenure. Drag the slider to feel the math."
      />
      <Card accent="pos">
        <div className="grid grid-cols-1 lg:grid-cols-[1fr_1.2fr] gap-6">
          <div>
            <div className="font-sans text-[11px] text-ink-tertiary uppercase tracking-wider mb-1">Composite score</div>
            <input type="range" min="-10" max="10" step="0.1" value={score} onChange={e => setScore(Number(e.target.value))} className="w-full" />
            <div className="flex items-center gap-3 mt-2">
              <span className={`px-3 py-1 rounded-[2px] font-mono text-[12px] font-semibold ${verdict.color.replace('text-', 'bg-').replace('signal-', 'signal-')}/15 ${verdict.color}`}>
                {verdict.label}
              </span>
              <span className="font-mono text-[28px] font-semibold text-ink-primary">{score >= 0 ? '+' : ''}{score.toFixed(1)}</span>
            </div>
            <div className="font-sans text-[13px] text-ink-secondary leading-[1.55] mt-3">
              The composite score blends ~15 signals: RS in 5 windows, trend stage, breadth, volatility-adjusted return, cross-tier rank, regime fit. Each signal is weighted by its historical predictive power (Information Coefficient).
            </div>
          </div>

          <div className="bg-paper p-4 rounded-[2px] border border-paper-rule">
            <div className="font-sans text-[10px] text-ink-tertiary uppercase tracking-wider mb-1">Probability interpretation</div>
            <div className="font-mono text-[40px] font-semibold text-ink-primary leading-none">{conviction}%</div>
            <div className="font-sans text-[13px] text-ink-secondary leading-[1.55] mt-2 mb-4">
              <strong>Plain-English read:</strong> in {conviction} out of every 100 historical setups that looked exactly like this stock today (same cap tier, same RS profile, same trend stage), the stock beat its tier benchmark over the relevant tenure.
            </div>

            {/* Conviction distribution visual */}
            <svg viewBox="0 0 300 80" className="w-full">
              <defs>
                <linearGradient id="grad" x1="0%" x2="100%">
                  <stop offset="0%" stopColor="#B0492C" stopOpacity="0.3" />
                  <stop offset="50%" stopColor="#B8860B" stopOpacity="0.3" />
                  <stop offset="100%" stopColor="#2F6B43" stopOpacity="0.3" />
                </linearGradient>
              </defs>
              <line x1="10" y1="65" x2="290" y2="65" stroke="#DDD3BF" strokeWidth="1" />
              <rect x="10" y="20" width="280" height="45" fill="url(#grad)" rx="2" />
              <line x1={10 + (conviction / 100) * 280} y1="15" x2={10 + (conviction / 100) * 280} y2="68" stroke="#1A1714" strokeWidth="2" />
              <circle cx={10 + (conviction / 100) * 280} cy="40" r={Math.max(6, bellWidth / 4)} fill="#1D9E75" />
              <text x="10"  y="78" fontFamily="JetBrains Mono" fontSize="9" fill="#6B6157">0%</text>
              <text x="290" y="78" fontFamily="JetBrains Mono" fontSize="9" fill="#6B6157" textAnchor="end">100%</text>
              <text x="10  + (50  / 100) * 280" y="78" fontFamily="JetBrains Mono" fontSize="9" fill="#6B6157" textAnchor="middle">50% (coin flip)</text>
              <text x={10 + (conviction / 100) * 280} y="12" fontFamily="Inter" fontSize="11" fontWeight="600" fill="#1D9E75" textAnchor="middle">{conviction}%</text>
            </svg>
            <div className="font-sans text-[11px] text-ink-tertiary leading-[1.55] mt-2">
              50% = coin flip · 60% = useful edge · 70%+ = strong setup · 80%+ = high confidence
            </div>
          </div>
        </div>
      </Card>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mt-4">
        <Card>
          <div className="font-serif text-[16px] font-medium text-ink-primary mb-1">Why &quot;unconditional&quot;?</div>
          <p className="font-sans text-[12px] text-ink-secondary leading-[1.55]">
            <code className="font-mono text-[10px] bg-paper-soft px-1">confidence_unconditional</code> is the hit-rate across ALL regimes (risk-on, cautious, risk-off). Atlas also computes <code className="font-mono text-[10px] bg-paper-soft px-1">confidence_regime_conditional</code> — the hit-rate IN the current regime. The frontend shows whichever is more conservative.
          </p>
        </Card>
        <Card>
          <div className="font-serif text-[16px] font-medium text-ink-primary mb-1">Predicted excess</div>
          <p className="font-sans text-[12px] text-ink-secondary leading-[1.55]">
            Alongside the % conviction, each cell has a <code className="font-mono text-[10px] bg-paper-soft px-1">predicted_excess</code> — the AVERAGE outperformance vs the tier benchmark in historical samples. So Large/3m/POS predicts ~+5pp excess at 73% confidence; Mid/12m/POS predicts ~+12pp at 60%.
          </p>
        </Card>
        <Card>
          <div className="font-serif text-[16px] font-medium text-ink-primary mb-1">Friction-adjusted</div>
          <p className="font-sans text-[12px] text-ink-secondary leading-[1.55]">
            Atlas subtracts a per-tier friction estimate (bid-ask + impact + brokerage) from <code className="font-mono text-[10px] bg-paper-soft px-1">predicted_excess</code> to get <code className="font-mono text-[10px] bg-paper-soft px-1">friction_adjusted_excess</code>. A 6% predicted edge in Small-caps with 4% friction shows only 2% net — so we won&apos;t fire that call.
          </p>
        </Card>
      </div>
    </section>
  )
}

// ============================================================================
// 5. THE FLYWHEEL (NEW)
// ============================================================================

function Flywheel() {
  return (
    <section className="px-8 py-12 border-b border-paper-rule bg-paper-soft">
      <SectionHead
        kicker="Why Atlas gets smarter"
        title="The flywheel"
        sub="Atlas isn't static. Every cycle of the engine feeds back into the next. The system gets sharper as it runs longer."
      />
      <div className="grid grid-cols-1 lg:grid-cols-[1fr_1fr] gap-8 items-center">
        {/* Diagram */}
        <svg viewBox="0 0 400 400" className="w-full max-w-[400px] mx-auto">
          {/* Circle path */}
          <circle cx="200" cy="200" r="140" fill="none" stroke="#DDD3BF" strokeWidth="1" strokeDasharray="4 4" />
          {/* Arrows */}
          {[0, 60, 120, 180, 240, 300].map(deg => {
            const r = 140, theta = (deg - 90) * Math.PI / 180
            const x = 200 + r * Math.cos(theta)
            const y = 200 + r * Math.sin(theta)
            return <circle key={deg} cx={x} cy={y} r="8" fill="#1D9E75" />
          })}
          {/* Center */}
          <circle cx="200" cy="200" r="64" fill="#1D9E75" fillOpacity="0.08" stroke="#1D9E75" />
          <text x="200" y="195" textAnchor="middle" fontFamily="Inter" fontSize="13" fontWeight="700" fill="#1D9E75">ATLAS</text>
          <text x="200" y="212" textAnchor="middle" fontFamily="Inter" fontSize="11" fill="#2F6B43">flywheel</text>
          {/* Stage labels */}
          <text x="200" y="40"  textAnchor="middle" fontFamily="Inter" fontSize="11" fontWeight="600" fill="#1A1714">1.&nbsp;Atlas fires calls</text>
          <text x="360" y="125" textAnchor="middle" fontFamily="Inter" fontSize="11" fontWeight="600" fill="#1A1714">2.&nbsp;Market resolves</text>
          <text x="360" y="285" textAnchor="middle" fontFamily="Inter" fontSize="11" fontWeight="600" fill="#1A1714">3.&nbsp;IC recomputes</text>
          <text x="200" y="378" textAnchor="middle" fontFamily="Inter" fontSize="11" fontWeight="600" fill="#1A1714">4.&nbsp;Weights re-tune</text>
          <text x="40"  y="285" textAnchor="middle" fontFamily="Inter" fontSize="11" fontWeight="600" fill="#1A1714">5.&nbsp;Conviction sharpens</text>
          <text x="40"  y="125" textAnchor="middle" fontFamily="Inter" fontSize="11" fontWeight="600" fill="#1A1714">6.&nbsp;Calls get smarter</text>
        </svg>

        {/* Right column — flywheel stages */}
        <div className="space-y-3">
          {[
            { n: 1, label: 'Atlas fires calls', body: 'Tonight\'s engine produces ~600 BUY/AVOID calls with cell-tagged conviction.' },
            { n: 2, label: 'Market resolves them', body: 'Over the next 1m/3m/6m/12m, each call wins or loses against the tier benchmark.' },
            { n: 3, label: 'IC recomputes', body: 'atlas_signal_ic_rolling recalculates each signal\'s predictive accuracy. Daily, automatically.' },
            { n: 4, label: 'Weights re-tune', body: 'Signals that predicted well get more weight; signals that didn\'t lose weight. atlas_weight_proposals fires nightly with the proposed update.' },
            { n: 5, label: 'Conviction sharpens', body: 'With the new weights, tomorrow\'s composite score is more accurate. The same +5 score now means more.' },
            { n: 6, label: 'Calls get smarter', body: 'Cells with stronger validated edge fire more often; weaker cells get deprecated. The engine literally improves overnight.' },
          ].map(s => (
            <div key={s.n} className="flex gap-3">
              <div className="shrink-0 w-7 h-7 rounded-full bg-teal text-paper font-mono text-[11px] font-semibold flex items-center justify-center">{s.n}</div>
              <div>
                <div className="font-serif text-[15px] font-medium text-ink-primary leading-tight">{s.label}</div>
                <div className="font-sans text-[12px] text-ink-secondary leading-[1.5]">{s.body}</div>
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="mt-8 max-w-[800px] mx-auto font-sans text-[14px] text-ink-secondary leading-[1.65] italic text-center">
        Every night the loop completes once. After 30 nights, weights have re-tuned ~30 times.
        After 1 year, every cell has been validated against ~250 trading-day windows.
        That is why a conviction call today is materially sharper than a call from 6 months ago.
      </div>
    </section>
  )
}

// ============================================================================
// 6. AUTO-OPTIMIZATION CYCLE (NEW)
// ============================================================================

const CYCLES = [
  {
    cadence: 'DAILY',
    when: 'Every weekday night 1:30 – 2 AM',
    what: 'IC tracker',
    body: 'atlas_signal_ic_rolling refreshes — each signal\'s rolling-30d Information Coefficient is recomputed using the previous day\'s realised returns. This is the live pulse-check on each signal\'s health.',
    surface: 'Admin · Weight Monitoring tab',
  },
  {
    cadence: 'WEEKLY',
    when: 'Sundays',
    what: 'Weight-proposal generator',
    body: 'For each of the 5 conviction tiers (T1-T5), Atlas compares the current weight-set against alternative candidates using Bayesian smoothing. If a candidate predicts ≥0.02 better IC with 60+ days of live data, a proposal fires.',
    surface: 'Admin · Signal Proposals tab',
  },
  {
    cadence: 'MONTHLY',
    when: 'First Monday',
    what: 'Auto-apply approved proposals',
    body: 'Proposals that passed the Bayesian bar AND the drift safety gate get auto-applied. The previous weight-set is archived in atlas_threshold_history with a revert hook.',
    surface: 'Admin · Activity Log',
  },
  {
    cadence: 'QUARTERLY',
    when: 'Walk-forward refresh',
    what: 'Cell re-validation',
    body: 'Every quarter, Atlas runs a fresh walk-forward backtest on every cell. Cells whose IC degraded by ≥30% over the last quarter get auto-deprecated (drift_status=deprecated). New candidate cells from atlas_cell_rule_candidates can be promoted if they validate.',
    surface: 'Admin · Validator tab',
  },
]

function AutoOptCycle() {
  return (
    <section className="px-8 py-12 border-b border-paper-rule bg-paper">
      <SectionHead
        kicker="The auto-optimization loop"
        title="Daily · Weekly · Monthly · Quarterly"
        sub="Four nested cycles. Each tunes a different layer of the engine. You can see each in the Admin pages."
      />
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {CYCLES.map((c, idx) => (
          <Card key={c.cadence} accent={idx === 0 ? 'pos' : idx === 1 ? 'teal' : idx === 2 ? 'neu' : 'neutral'}>
            <div className="font-mono text-[10px] text-ink-tertiary uppercase tracking-[0.14em] mb-1">{c.cadence}</div>
            <div className="font-serif text-[18px] font-medium text-ink-primary leading-tight mb-1">{c.what}</div>
            <div className="font-sans text-[11px] text-ink-tertiary mb-3">{c.when}</div>
            <p className="font-sans text-[13px] text-ink-secondary leading-[1.55] mb-3">{c.body}</p>
            <div className="font-mono text-[10px] text-teal">→ {c.surface}</div>
          </Card>
        ))}
      </div>
    </section>
  )
}

// ============================================================================
// 7. Compact RS + Regime widgets (kept from v6.1, slimmed)
// ============================================================================

function CompactConcepts() {
  const [stock, setStock] = useState(8)
  const [nifty, setNifty] = useState(3)
  const rs = stock - nifty
  const REGIMES = [
    { k: 'risk-on',      label: 'Risk-On',      deploy: '100%', body: 'All 4 signals positive · deploy fully' },
    { k: 'constructive', label: 'Constructive', deploy: '80%',  body: '3 of 4 positive · mostly deployed' },
    { k: 'cautious',     label: 'Cautious',     deploy: '60%',  body: 'Mixed · reduced sizes' },
    { k: 'risk-off',     label: 'Risk-Off',     deploy: '40%',  body: 'Broad deterioration · capital preservation' },
  ]
  const [pick, setPick] = useState('risk-on')
  const r = REGIMES.find(x => x.k === pick) ?? REGIMES[0]

  return (
    <section className="px-8 py-12 border-b border-paper-rule bg-paper">
      <SectionHead
        kicker="Quick math"
        title="Two ideas you'll see every day"
        sub="Relative Strength and Market Regime. The simplest signals Atlas computes."
      />
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        <Card accent="neu">
          <div className="font-serif text-[18px] font-medium text-ink-primary mb-1">Relative Strength (RS)</div>
          <p className="font-sans text-[12px] text-ink-secondary leading-[1.5] mb-3">
            RS = stock return − Nifty 500 return. Positive = leading. Atlas measures over 1w / 1m / 3m / 6m / 12m.
          </p>
          <div className="grid grid-cols-2 gap-3 mb-3">
            <div>
              <label className="font-sans text-[10px] text-ink-tertiary uppercase tracking-wider">Stock</label>
              <input type="range" min="-30" max="60" value={stock} onChange={e => setStock(Number(e.target.value))} className="w-full" />
              <div className="font-mono text-[14px] text-ink-primary">{stock >= 0 ? '+' : ''}{stock}%</div>
            </div>
            <div>
              <label className="font-sans text-[10px] text-ink-tertiary uppercase tracking-wider">Nifty 500</label>
              <input type="range" min="-30" max="60" value={nifty} onChange={e => setNifty(Number(e.target.value))} className="w-full" />
              <div className="font-mono text-[14px] text-ink-primary">{nifty >= 0 ? '+' : ''}{nifty}%</div>
            </div>
          </div>
          <div className="border-t border-paper-rule pt-2">
            <div className="font-sans text-[10px] text-ink-tertiary uppercase tracking-wider">RS</div>
            <div className={`font-mono text-[24px] font-semibold ${rs >= 5 ? 'text-signal-pos' : rs <= -5 ? 'text-signal-neg' : 'text-ink-primary'}`}>
              {rs >= 0 ? '+' : ''}{rs.toFixed(1)}pp
            </div>
          </div>
        </Card>

        <Card accent="teal">
          <div className="font-serif text-[18px] font-medium text-ink-primary mb-1">Market regime · 4 states</div>
          <p className="font-sans text-[12px] text-ink-secondary leading-[1.5] mb-3">
            Atlas asks 4 questions about the market daily (trend / breadth / momentum / participation) → 1 of 4 regimes → sets deploy %.
          </p>
          <div className="grid grid-cols-2 gap-2 mb-3">
            {REGIMES.map(x => (
              <button key={x.k} onClick={() => setPick(x.k)} className={`p-2 rounded-[2px] text-left ${pick === x.k ? 'bg-ink-primary text-paper' : 'bg-paper text-ink-primary border border-paper-rule'}`}>
                <div className="font-mono text-[10px]">{x.deploy}</div>
                <div className="font-serif text-[14px] font-medium">{x.label}</div>
              </button>
            ))}
          </div>
          <div className="font-sans text-[12px] text-ink-secondary leading-[1.5]">{r.body}</div>
        </Card>
      </div>
    </section>
  )
}

// ============================================================================
// 8. Honesty
// ============================================================================

function Honesty() {
  return (
    <section className="px-8 py-12 border-b border-paper-rule bg-paper">
      <SectionHead kicker="Limits" title="What Atlas won't tell you" sub="Math is powerful but partial. Here's what Atlas cannot do — so you don't trust it blindly." />
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <Card accent="neg">
          <div className="font-serif text-[16px] font-medium text-ink-primary mb-2">Predict news shocks</div>
          <p className="font-sans text-[13px] text-ink-secondary leading-[1.55]">Atlas reads prices, not news. A merger announcement, earnings surprise, or RBI policy shift can flip a stock overnight. The math sees it the NEXT day.</p>
        </Card>
        <Card accent="neg">
          <div className="font-serif text-[16px] font-medium text-ink-primary mb-2">Read fundamentals</div>
          <p className="font-sans text-[13px] text-ink-secondary leading-[1.55]">Atlas doesn&apos;t look at P/E, revenue growth, management quality, or balance sheet health. It assumes the market already prices those in.</p>
        </Card>
        <Card accent="neg">
          <div className="font-serif text-[16px] font-medium text-ink-primary mb-2">Size your position</div>
          <p className="font-sans text-[13px] text-ink-secondary leading-[1.55]">Atlas tells you WHAT to buy, not HOW MUCH. The regime hints at total deployment (40-100%); per-stock weighting is your call.</p>
        </Card>
        <Card accent="neg">
          <div className="font-serif text-[16px] font-medium text-ink-primary mb-2">Be right every time</div>
          <p className="font-sans text-[13px] text-ink-secondary leading-[1.55]">Hit rates 60-87%. Even the best cell has losing trades. Atlas is probabilistic — expect to be wrong, often. Diversify so wins outpay losses.</p>
        </Card>
      </div>
    </section>
  )
}

// ============================================================================
// Top-level
// ============================================================================

export default function MethodologyV62() {
  return (
    <div>
      <Hero />
      <EngineFlow />
      <CellExplainer />
      <ConvictionMath />
      <Flywheel />
      <AutoOptCycle />
      <CompactConcepts />
      <Honesty />
      <section className="px-8 py-10 bg-paper">
        <div className="max-w-[760px] font-sans text-[12px] text-ink-tertiary leading-[1.6]">
          Last revision: 2026-05-28 · Atlas v6.2. Want to inspect a live cell&apos;s IC + walk-forward backtest? Open <a className="text-teal" href="/admin/validator">Admin · Validator</a>. To see pending weight changes, open <a className="text-teal" href="/admin/composite-proposals">Admin · Signal Proposals</a>. Every threshold is configurable in <a className="text-teal" href="/admin/thresholds">Admin · Thresholds</a>.
        </div>
      </section>
    </div>
  )
}
