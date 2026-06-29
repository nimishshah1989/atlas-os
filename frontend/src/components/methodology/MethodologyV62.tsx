'use client'
// Atlas methodology — describes the REAL scoring engine only. Every claim here maps to live code:
// the six lenses + sub-components are columns in atlas_lens_scores_daily (atlas/lenses/compute/*.py),
// the weights are atlas_thresholds values, the roll-ups are the sector/fund/ETF lens queries. No
// fabricated hit rates, no aspirational "24-cell matrix" / conviction-% / auto-optimization claims.
import { useState } from 'react'
import { LensMindMap } from './LensMindMap'

// ── atoms ──────────────────────────────────────────────────────────────────
function SectionHead({ kicker, title, sub }: { kicker: string; title: string; sub?: string }) {
  return (
    <div className="mb-6">
      <div className="font-num text-[10px] text-txt-3 uppercase tracking-[0.14em] mb-1">{kicker}</div>
      <h2 className="font-display text-[28px] font-semibold tracking-tight text-txt-1 leading-tight">{title}</h2>
      {sub && <p className="font-sans text-[14px] text-txt-2 leading-[1.55] max-w-[820px] mt-2">{sub}</p>}
    </div>
  )
}

function Card({ children, accent = 'neutral' }: { children: React.ReactNode; accent?: 'pos' | 'neg' | 'neu' | 'teal' | 'neutral' }) {
  const cls = accent === 'pos' ? 'border-l-4 border-l-sig-pos'
            : accent === 'neg' ? 'border-l-4 border-l-sig-neg'
            : accent === 'neu' ? 'border-l-4 border-l-sig-warn'
            : accent === 'teal' ? 'border-l-4 border-l-brand'
            : 'border-l border-l-edge-rule'
  return <div className={`bg-surface-raised ${cls} p-5 rounded-r-tile`}>{children}</div>
}

// ── 1. hero ────────────────────────────────────────────────────────────────
function Hero() {
  return (
    <section className="px-8 py-12 border-b border-edge-hair bg-surface-panel">
      <div className="max-w-[880px]">
        <div className="font-num text-[10px] text-txt-3 uppercase tracking-[0.14em] mb-2">Atlas · Methodology</div>
        <h1 className="font-display text-[42px] font-semibold tracking-tight text-txt-1 leading-[1.1] mb-4">
          How every score is built
        </h1>
        <p className="font-sans text-[17px] text-txt-2 leading-[1.55] mb-4">
          Atlas scores every stock in the Nifty 500 each night across <span className="font-semibold text-txt-1">six lenses</span>,
          blends four of them into a single <span className="font-semibold text-txt-1">0–100 conviction score</span>, and rolls that same
          read up to sectors, funds and ETFs. It is a glass box: every number traces back to the inputs it came from.
        </p>
        <p className="font-sans text-[14px] text-txt-3 leading-[1.55]">
          This page shows exactly what goes into each lens and how the lenses combine. Nothing here is hidden, and nothing is invented —
          if an input is missing for a stock, that lens is scored on what is present and the rest re-normalises, rather than filling the gap.
        </p>
      </div>
    </section>
  )
}

// ── 2. the nightly engine (accurate, qualitative — no fabricated counts) ─────
const STEPS = [
  {
    n: 1, label: 'Data comes in', sub: 'every weekday night',
    body: 'Fresh inputs land for the whole universe: NSE prices, volume and delivery; quarterly & annual financials plus ready ratios; exchange filings (announcements); insider deals, bulk deals and shareholding; and the latest monthly mutual-fund holdings.',
    input: 'NSE · financials · filings · holdings', output: 'latest inputs, point-in-time',
  },
  {
    n: 2, label: 'Metrics computed', sub: 'per stock',
    body: 'For each stock Atlas derives the raw signals each lens needs — EMAs, RSI, ATR and relative strength vs the Nifty 500 and its sector; ROE/ROCE, margins, growth and leverage; delivery and flow trends; and the signal read of recent filings.',
    input: 'today + history', output: 'raw signals per stock',
  },
  {
    n: 3, label: 'Lenses → conviction', sub: 'scoring',
    body: 'Each of the six lenses is scored 0–100 from its sub-components. Four are blended — 0.30 Technical + 0.25 Fundamental + 0.25 Flow + 0.20 Catalyst — with a boost when lenses agree and a valuation multiplier, giving a 0–100 composite and a conviction tier. Valuation and Policy are context, not part of the blend.',
    input: 'signals + thresholds', output: '0–100 composite + tier',
  },
  {
    n: 4, label: 'Rolled up & served', sub: 'surfaces',
    body: 'The stock score is the atom. It rolls up free-float-weighted to sectors and holdings-weighted to funds and ETFs, so a fund’s lens read is literally its holdings’ scores weighted by position size. Results are materialised so the site is fresh each morning.',
    input: 'stock scores + weights', output: 'sector / fund / ETF scores',
  },
]

function EngineFlow() {
  const [active, setActive] = useState(1)
  const step = STEPS.find((s) => s.n === active) ?? STEPS[0]
  return (
    <section className="px-8 py-12 border-b border-edge-hair bg-surface-panel">
      <SectionHead kicker="The engine" title="What runs every night" sub="The same pipeline runs every weekday night. Click a step to see what happens." />
      <div className="grid grid-cols-1 md:grid-cols-4 gap-2 mb-6">
        {STEPS.map((s) => (
          <button key={s.n} onClick={() => setActive(s.n)}
            className={`text-left p-4 rounded-tile border transition-all ${active === s.n ? 'bg-txt-1 text-surface-panel border-txt-1' : 'bg-surface-raised text-txt-1 border-edge-hair hover:border-edge-strong'}`}>
            <div className={`font-num text-[10px] mb-1 ${active === s.n ? 'text-surface-panel/70' : 'text-txt-3'}`}>STEP {s.n}</div>
            <div className="font-display text-[16px] font-medium leading-tight">{s.label}</div>
            <div className={`font-sans text-[11px] mt-1 ${active === s.n ? 'text-surface-panel/70' : 'text-txt-3'}`}>{s.sub}</div>
          </button>
        ))}
      </div>
      <Card>
        <div className="font-sans text-[15px] text-txt-1 leading-[1.6] mb-4">{step.body}</div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-[13px]">
          <div>
            <div className="font-num text-[10px] text-txt-3 uppercase tracking-wider mb-1">In</div>
            <div className="font-num text-[12px] text-txt-2">{step.input}</div>
          </div>
          <div>
            <div className="font-num text-[10px] text-txt-3 uppercase tracking-wider mb-1">Out</div>
            <div className="font-num text-[12px] text-sig-pos">{step.output}</div>
          </div>
        </div>
      </Card>
    </section>
  )
}

// ── 4. roll-ups: the stock atom becomes sector / fund / ETF scores ───────────
function Rollups() {
  const items = [
    { title: 'Sectors', accent: 'teal' as const, body: 'A sector score is the free-float-weighted average of its constituents’ lens scores. Bigger companies move it more — the same four-lens blend, one level up.' },
    { title: 'Funds & ETFs', accent: 'pos' as const, body: 'A fund’s lens read is the holdings-weighted average of what it actually owns. Its Technical score is its holdings’ Technical scores weighted by position size — fully traceable to the names inside.' },
    { title: 'Same scale everywhere', accent: 'neutral' as const, body: 'Stock, sector, fund and ETF all sit on the same 0–100 lens scale and the same composite blend, so a number means the same thing wherever you see it.' },
  ]
  return (
    <section className="px-8 py-12 border-b border-edge-hair bg-surface-panel">
      <SectionHead kicker="One atom, everywhere" title="How stocks roll up to sectors, funds and ETFs"
        sub="There is one scoring engine. Everything above a single stock is a weighted roll-up of the same lens scores — no separate model." />
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {items.map((i) => (
          <Card key={i.title} accent={i.accent}>
            <div className="font-display text-[16px] font-medium text-txt-1 mb-2">{i.title}</div>
            <p className="font-sans text-[13px] text-txt-2 leading-[1.55]">{i.body}</p>
          </Card>
        ))}
      </div>
    </section>
  )
}

// ── 5. honesty (accurate limits) ─────────────────────────────────────────────
function Honesty() {
  const cards = [
    { title: 'A read, not a promise', body: 'The score describes what is strong right now across the lenses. It is a transparency view of the evidence, not a forecast that a stock will go up.' },
    { title: 'Data lags reality', body: 'NAVs run a day or three behind, fund and ETF holdings carry SEBI’s ~30-day disclosure lag, and filings are as-reported. Scores reflect the latest available, not real-time.' },
    { title: 'Missing data degrades, never faked', body: 'If a lens input is absent, that lens is scored only on what is present and the composite re-normalises. Atlas never substitutes a fake neutral to hide a gap.' },
    { title: 'It does not size positions', body: 'Atlas ranks and scores. How much to hold, and your own risk limits, are your call.' },
  ]
  return (
    <section className="px-8 py-12 border-b border-edge-hair bg-surface-panel">
      <SectionHead kicker="Limits" title="What the score is — and isn’t" sub="So you read it for what it is." />
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {cards.map((c) => (
          <Card key={c.title} accent="neg">
            <div className="font-display text-[16px] font-medium text-txt-1 mb-2">{c.title}</div>
            <p className="font-sans text-[13px] text-txt-2 leading-[1.55]">{c.body}</p>
          </Card>
        ))}
      </div>
    </section>
  )
}

export function MethodologyV62() {
  return (
    <div>
      <Hero />
      <EngineFlow />
      <LensMindMap />
      <Rollups />
      <Honesty />
      <section className="px-8 py-10 bg-surface-panel">
        <div className="max-w-[820px] font-sans text-[12px] text-txt-3 leading-[1.6]">
          Every weight and threshold on this page is configurable and lives in <a className="text-brand" href="/thresholds">the thresholds control panel</a>. The lenses, sub-components and weights shown are read from the live scoring engine and <span className="font-num">atlas_thresholds</span>.
        </div>
      </section>
    </div>
  )
}

export default MethodologyV62
