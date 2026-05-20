// allow-large: comprehensive methodology guide — 6 tab sections covering the v2 decision
// engine (layered targets, policy rails, 6-step flow), states, regime, sectors (hybrid
// classifier), conviction/IC, and admin. Single cohesive document; splitting by tab would
// spread one conceptual unit across 6 files with no reuse benefit.
'use client'
import { useState } from 'react'
import Link from 'next/link'

type Tab = 'overview' | 'states' | 'regime' | 'sectors' | 'conviction' | 'admin'

const TABS: { key: Tab; label: string }[] = [
  { key: 'overview',   label: 'Overview' },
  { key: 'states',     label: 'Stock States' },
  { key: 'regime',     label: 'Market Regime' },
  { key: 'sectors',    label: 'Sectors & RRG' },
  { key: 'conviction', label: 'Conviction & IC' },
  { key: 'admin',      label: 'Admin Guide' },
]

function Callout({ children, color = 'teal' }: { children: React.ReactNode; color?: 'teal' | 'warn' | 'neg' }) {
  const border = color === 'teal' ? 'border-teal' : color === 'warn' ? 'border-signal-warn' : 'border-signal-neg'
  return (
    <div className={`border-l-2 ${border} bg-paper-rule/20 pl-4 py-3 my-4 text-sm font-sans text-ink-secondary leading-relaxed`}>
      {children}
    </div>
  )
}

function SectionHead({ id, children }: { id: string; children: React.ReactNode }) {
  return (
    <h2 id={id} className="font-serif text-lg text-ink-primary mb-3 mt-8 pb-2 border-b border-paper-rule first:mt-0">
      {children}
    </h2>
  )
}

function SubHead({ children }: { children: React.ReactNode }) {
  return <h3 className="font-sans text-[11px] font-semibold uppercase tracking-wider text-ink-tertiary mb-2 mt-5">{children}</h3>
}

function P({ children }: { children: React.ReactNode }) {
  return <p className="font-sans text-sm text-ink-secondary leading-relaxed mb-3">{children}</p>
}

type BadgeColor = string
function StateBadge({ label, bg, text }: { label: string; bg: BadgeColor; text: BadgeColor }) {
  return (
    <span className="inline-flex items-center px-2 py-0.5 rounded-sm font-sans text-[10px] font-semibold"
      style={{ background: bg, color: text }}>{label}</span>
  )
}

function StateRow({ state, bg, text, meaning, when }: { state: string; bg: string; text: string; meaning: string; when: string }) {
  return (
    <tr className="border-b border-paper-rule/40 align-top">
      <td className="px-3 py-2 shrink-0">
        <StateBadge label={state} bg={bg} text={text} />
      </td>
      <td className="px-3 py-2 font-sans text-[11px] text-ink-primary font-medium">{meaning}</td>
      <td className="px-3 py-2 font-sans text-[11px] text-ink-secondary">{when}</td>
    </tr>
  )
}

function StateTable({ children }: { children: React.ReactNode }) {
  return (
    <div className="overflow-x-auto border border-paper-rule rounded-sm mb-5">
      <table className="w-full">
        <thead>
          <tr className="border-b border-paper-rule bg-paper-rule/10">
            <th className="text-left px-3 py-2 font-sans text-[10px] uppercase tracking-wider text-ink-tertiary w-32">State</th>
            <th className="text-left px-3 py-2 font-sans text-[10px] uppercase tracking-wider text-ink-tertiary">What it means</th>
            <th className="text-left px-3 py-2 font-sans text-[10px] uppercase tracking-wider text-ink-tertiary">Triggers when…</th>
          </tr>
        </thead>
        <tbody>{children}</tbody>
      </table>
    </div>
  )
}

// ─── Tab content ──────────────────────────────────────────────────────────────

function TabOverview() {
  return (
    <div>
      <SectionHead id="decision-engine">The v2 decision engine</SectionHead>
      <P>Atlas v2 is a systematic decision engine for Indian equity portfolios. Every night it classifies the full ~1,000-stock universe, aggregates stock states into sector and market views, and — critically — intersects those views with a fund manager&apos;s per-portfolio mandate (the Policy) to produce recommendations that are specific to how a given desk runs money.</P>
      <P>The engine does not fire generic signals. It produces a layered answer to three questions: <em>what is the market environment?</em> (regime) → <em>which sectors should I hold and how much?</em> (rotation targets) → <em>which instruments fill those targets?</em> (bottom-up picks filtered by Policy).</P>

      <SectionHead id="layered-targets">Layered targets — the unit of action</SectionHead>
      <P>Every recommendation has two layers:</P>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mb-4">
        {[
          { title: 'Sector targets — the WHAT', desc: 'Set at the regime + rotation layer. Example: "be 12% Banking." Sized by engine signal strength and capped by the Policy\'s max-per-sector rule. The rotation engine ranks sectors cross-sectionally; the Policy caps the ceiling.' },
          { title: 'Instrument picks — the WHICH', desc: 'The stocks, ETFs, or funds that fill a sector target. Ranked by within-state conviction and filtered to the Policy\'s entry rules. An ETF book sees sector ETFs; a direct-equity book sees stocks.' },
        ].map(p => (
          <div key={p.title} className="border border-paper-rule rounded-sm p-4">
            <div className="font-sans text-[11px] font-semibold text-ink-primary mb-1">{p.title}</div>
            <div className="font-sans text-xs text-ink-secondary leading-relaxed">{p.desc}</div>
          </div>
        ))}
      </div>

      <SectionHead id="policy-rails">Policy rails — the spine of every recommendation</SectionHead>
      <P>Every recommendation is the intersection of two things:</P>
      <div className="border border-paper-rule rounded-sm p-4 mb-4 bg-paper-rule/10">
        <div className="font-mono text-sm text-ink-primary text-center">
          recommendation = engine_signal ∩ policy_constraint
        </div>
      </div>
      <P>The <strong>engine signal</strong> is the IC-validated Weinstein state output — the same data for every portfolio. The <strong>Policy</strong> is the fund manager&apos;s mandate, configured per-portfolio. Same engine, different Policy → different recommendations. A retiree book tightens stops and lowers the small-cap ceiling vs the house default. A focused book caps total names at 20.</P>
      <P>Policy fields govern: deployment (cash floor, regime-cap respect), concentration (per-stock / per-sector / small-cap ceilings, min/max holdings count), entry rules (which Weinstein states qualify to buy, minimum conviction and RS rank), exit rules (hard stop %, state-triggered exit, trailing stop), instrument universe (direct equity / ETF / fund / mixed), benchmark, and rebalance cadence.</P>
      <Callout color="teal">
        <strong>Every flow step reads the Policy.</strong> Step 2 reads sector caps. Step 3 reads entry rules and instrument universe. Step 5 reads sizing caps. Step 6 reads exit rules. The Policy is the thread that makes the engine actionable for a specific book.
      </Callout>

      <SectionHead id="six-step-flow">The 6-step decision flow</SectionHead>
      <P>A continuous decision loop. Each step passes context to the next — the active portfolio, its Policy, the regime deployment cap, and the sector target gap.</P>
      <ol className="space-y-3 ml-2 mb-4 list-decimal list-outside pl-4">
        {([
          ['Step 1 — Regime', '/', 'The market environment verdict. One sentence: e.g. "Cautious — deploy 40%. Add only Leader/Strong names in leading sectors. Trim Stage 3→4 holdings." Backed by the 4-signal scorecard (Trend / Breadth / Momentum / Participation) and the full breadth panel (VIX, A/D, McClellan, Net NH-NL). The deployment cap carries forward.'],
          ['Step 2 — Sector rotation', '/sectors', 'Sectors ranked by bottom-up stage breadth. For the active portfolio, each sector row shows current exposure vs policy-capped target: "Banking: now 8% · engine strong · policy cap 15% → target 12% · fill +4%." This is where sector targets are set. The chosen sector + target gap carry forward.'],
          ['Step 3 — Fill the target', '/sectors/[name]', 'The sector\'s instruments ranked by within-state conviction, filtered to the Policy\'s entry rules. Instrument type shown = the Policy\'s instrument universe. Suggested weights respect the max-per-stock cap. Candidate instruments carry forward.'],
          ['Step 4 — Conviction check', '/stocks/[symbol]', 'The IC-validated evidence page. Every token is a link — sector chip → sector page, "N peers in this state" → peer list. Ends with the Act affordance. Act or pass carries forward.'],
          ['Step 5 — Act', '/portfolios/[id]', '"Add to book" produces a proposed portfolio change (not a raw trade ticket). Position size is pre-filled from target gap ∩ max-per-stock ∩ regime deployment cap. A policy-compliance check runs before the change is accepted.'],
          ['Step 6 — Deterioration loop', '/portfolios/[id]', 'Holdings that hit a Policy exit rule (hard stop, state exit) auto-surface on the portfolio page. Each → click → stock detail → confirm trim. The portfolio page is both the destination of steps 1–5 and the origin of the trim flow.'],
        ] as [string, string, string][]).map(([step, href, desc]) => (
          <li key={step} className="font-sans text-sm text-ink-secondary leading-relaxed">
            <Link href={href} className="font-semibold text-teal hover:underline">{step}</Link>
            {' — '}{desc}
          </li>
        ))}
      </ol>

      <SectionHead id="scorecard">The 4-signal bottom-up scorecard</SectionHead>
      <P>The regime page leads with a scorecard built bottom-up from individual stock Weinstein states. It answers: <em>how healthy is the breadth of the market right now?</em></P>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mb-4">
        {[
          { signal: 'Trend', desc: '% of the classified universe in Stage 2 (mark-up). The primary measure of structural health. Thin Stage-2 breadth = even a Risk-On regime is narrow-led.' },
          { signal: 'Breadth', desc: 'Moving-average participation — % of universe above their 50-day EMA. Feeds the regime classifier directly. Below 40% = broad deterioration.' },
          { signal: 'Momentum', desc: 'Stage-2 inflow rate — how many stocks entered Stage 2 in the past week vs exited. Positive = broadening; negative = narrowing.' },
          { signal: 'Participation', desc: 'Leadership concentration — how many stocks account for 80% of positive RS. A market where 10 stocks do all the work is structurally fragile even if the index is up.' },
        ].map(p => (
          <div key={p.signal} className="border border-paper-rule rounded-sm p-4">
            <div className="font-sans text-[11px] font-semibold text-ink-primary mb-1">{p.signal}</div>
            <div className="font-sans text-xs text-ink-secondary leading-relaxed">{p.desc}</div>
          </div>
        ))}
      </div>

      <SectionHead id="pillars">The measurement layers — where to go next</SectionHead>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mb-4">
        {[
          { title: 'Weinstein State Engine', desc: 'Every stock is classified daily into Stage 1 (base) / 2A–2C (mark-up) / 3 (top) / 4 (decline) or Uninvestable. Sector and fund views aggregate bottom-up from these stock states.', tab: 'states' },
          { title: 'Market Regime', desc: 'One number per day: Risk-On / Constructive / Cautious / Risk-Off. Drives the deployment multiplier. Backed by the 4-signal scorecard plus the full breadth panel.', tab: 'regime' },
          { title: 'Sector Rotation + Hybrid Classifier', desc: 'Sectors ranked cross-sectionally daily. An absolute floor keeps the top label honest in a thin market. RRG quadrant shows rotation momentum.', tab: 'sectors' },
          { title: 'Conviction Score + IC Optimization', desc: '0–100 composite of 11 signals, weighted by rolling IC per liquidity tier. Nightly proposal loop + FM approval + auto-revert guard.', tab: 'conviction' },
        ].map(p => (
          <div key={p.title} className="border border-paper-rule rounded-sm p-4">
            <div className="font-sans text-[11px] font-semibold text-ink-primary mb-1">{p.title}</div>
            <div className="font-sans text-xs text-ink-secondary leading-relaxed">{p.desc}</div>
          </div>
        ))}
      </div>

      <Callout color="teal">
        <strong>Important framing:</strong> Atlas uses words like "Leader," "Stage 2," and "Overweight" to describe price behaviour and relative rank — not business quality. A Stage-4 stock can be a world-class company in a temporary downtrend. An Overweight sector is the least-bad in the current field, not necessarily strong in absolute terms. The engine describes where the market is; the Policy defines what you do about it.
      </Callout>
    </div>
  )
}

function TabStates() {
  return (
    <div>
      <P>Every stock in the universe gets four states computed nightly. They are independent — a stock can be a Leader (strong RS) with High Risk (extended and volatile), for example. Read all four together for the full picture.</P>

      <SectionHead id="rs">RS State — relative strength rank</SectionHead>
      <P>RS State answers: <em>how is this stock performing relative to the universe, across three timeframes?</em> The three timeframes are 1-week, 1-month, and 3-month percentile rank within the full ~1,000-stock universe.</P>
      <P><strong>Top quintile</strong> = rank ≥ 80th percentile. <strong>Bottom quintile</strong> = rank ≤ 20th percentile. The Weinstein Gate additionally requires the stock to be above its 30-week SMA (i.e., in a long-term uptrend).</P>
      <StateTable>
        <StateRow state="Leader"        bg="#e8f4ec" text="#2F6B43" meaning="All three timeframes in the top quintile — AND above 30-week SMA." when="1W ≥ 80th AND 1M ≥ 80th AND 3M ≥ 80th AND Weinstein gate pass" />
        <StateRow state="Strong"        bg="#e0f5ef" text="#1D9E75" meaning="1-month and 3-month in top quintile but 1-week has faded slightly. Still a healthy intermediate-term trend." when="1M ≥ 80th AND 3M ≥ 80th AND 1W < 80th AND Weinstein gate pass" />
        <StateRow state="Consolidating" bg="#f5f0e8" text="#B8860B" meaning="3-month was strong but both 1W and 1M have dropped out of the top quintile. The trend is pausing — watch whether it resumes or breaks." when="3M ≥ 80th AND 1W < 80th AND 1M < 80th AND Weinstein gate pass" />
        <StateRow state="Emerging"      bg="#e8eef5" text="#25394A" meaning="A fresh breakout from a base: strong last week and month, but the 3-month window was NOT in the top quintile. The stock is just turning the corner." when="1W ≥ 80th AND 1M ≥ 80th AND 3M < 80th AND Stage-1 base AND Weinstein gate" />
        <StateRow state="Average"       bg="#f5f5f5" text="#5a5a5a" meaning="None of the above conditions met. Middle of the pack. Also forced here if Risk State = Below Trend (conjunction rule)." when="No quintile conditions fire. Or: risk_state = Below Trend (override)." />
        <StateRow state="Weak"          bg="#fdf0ee" text="#B0492C" meaning="At least one timeframe in the bottom quintile — below-average RS on at least one window." when="1W ≤ 20th OR 1M ≤ 20th OR 3M ≤ 20th" />
        <StateRow state="Laggard"       bg="#fce8e4" text="#8B2E1A" meaning="All three timeframes in the bottom quintile. Persistent underperformance — the worst RS bucket." when="1W ≤ 20th AND 1M ≤ 20th AND 3M ≤ 20th (checked first; wins over Weak)" />
      </StateTable>
      <Callout color="teal">
        <strong>The conjunction rule:</strong> When Risk State = <strong>Below Trend</strong> (price below 200-EMA), RS State is forced to "Average" regardless of percentile rank. A stock below its long-term trend cannot be called a Leader even if recent relative performance looks good — the trend signal overrides the rank.
      </Callout>
      <SubHead>Suspended states (override all four axes)</SubHead>
      <P>Three suspension labels override all four state axes when data quality gates fail:</P>
      <ul className="space-y-1 mb-4 ml-2 font-sans text-xs text-ink-secondary">
        <li><strong>INSUFFICIENT_HISTORY</strong> — less than 252 trading days of data. Too new to classify reliably.</li>
        <li><strong>ILLIQUID</strong> — average daily traded value below the liquidity gate. Price signals are noisy.</li>
        <li><strong>DISLOCATION_SUSPENDED</strong> — market-wide dislocation event active (extreme fear/vol spike). All states paused.</li>
      </ul>

      <SectionHead id="momentum">Momentum State — direction of the trend</SectionHead>
      <P>Momentum answers: <em>is the trend accelerating or decelerating?</em> It uses the 10-day EMA ratio (EMA-10 ÷ 200-day SMA) and 20-day EMA ratio, plus whether the short-term EMA is making new highs or lows.</P>
      <P>EMA ratio {'>'}  1.0 = EMA is above the long-term SMA = price is in an uptrend. A ratio near 1.0 means price is flat relative to the long-term average. The comparison of EMA-10 vs EMA-20 tells you whether short-term momentum is outrunning medium-term momentum.</P>
      <StateTable>
        <StateRow state="Accelerating"  bg="#e8f4ec" text="#2F6B43" meaning="Both short and medium EMAs above 1.0, short above medium, AND EMA-10 just made a 20-day high. Full-strength uptrend picking up speed." when="EMA-10 ratio > 1, EMA-10 > EMA-20, EMA-10 at 20-day high" />
        <StateRow state="Improving"     bg="#e0f5ef" text="#1D9E75" meaning="Both EMAs above 1.0, short above medium, but not at a new high. A healthy uptrend without necessarily having just accelerated." when="EMA-10 ratio > 1, EMA-10 > EMA-20 (not at 20-day high)" />
        <StateRow state="Flat"          bg="#f5f5f5" text="#5a5a5a" meaning="EMAs hugging 1.0 or the two EMAs converging toward each other. No directional conviction. Usually a pause or topping/bottoming signal." when="EMA-10 ratio near 1.0 (±2%) OR EMA-10 and EMA-20 within 1% of each other" />
        <StateRow state="Deteriorating" bg="#fdf0ee" text="#B0492C" meaning="Both EMAs below 1.0, short below medium. Downtrend, but not at extremes." when="EMA-10 ratio < 1, EMA-10 < EMA-20 (not at 20-day low)" />
        <StateRow state="Collapsing"    bg="#fce8e4" text="#8B2E1A" meaning="Both EMAs below 1.0, short below medium, AND EMA-10 just made a 20-day low. Downtrend is accelerating — highest urgency signal." when="EMA-10 ratio < 1, EMA-10 < EMA-20, EMA-10 at 20-day low" />
      </StateTable>

      <SectionHead id="risk">Risk State — how stretched is the stock?</SectionHead>
      <P>Risk State answers: <em>is the stock overbought/oversold relative to its long-term trend, and is volatility elevated?</em> It uses two inputs: extension_pct (how far above/below the 200-EMA the price is) and vol_ratio_63 (63-day realized volatility divided by its own historical median).</P>
      <StateTable>
        <StateRow state="Below Trend"   bg="#e8eef5" text="#25394A" meaning="Price is BELOW the 200-day EMA. The long-term trend is down. This overrides RS State to Average (see above). Not a severity ranking — it is a structural classification." when="extension_pct < 0 (price below 200-EMA). Checked first — wins over all other conditions." />
        <StateRow state="High"          bg="#fce8e4" text="#8B2E1A" meaning="Highly extended above trend OR realized vol is very high vs history. A stock in High Risk has moved a lot — upside may be limited and downside swift." when="extension > high threshold OR vol_ratio_63 > high threshold" />
        <StateRow state="Elevated"      bg="#fdf0ee" text="#B0492C" meaning="Moderately above trend or moderately elevated vol. The stock has some stretch — not extreme but worth noting." when="extension OR vol_ratio in moderate range" />
        <StateRow state="Normal"        bg="#f5f5f5" text="#5a5a5a" meaning="Close to trend, normal volatility. The most common state for healthy trending stocks." when="Within normal extension and vol ratio bands" />
        <StateRow state="Low"           bg="#e8f4ec" text="#2F6B43" meaning="Tight to trend, below-normal volatility. Often seen during bases and consolidations — coiled spring potential." when="extension ≤ low-max AND vol_ratio ≤ low-max" />
      </StateTable>

      <SectionHead id="volume">Volume State — who is doing the trading?</SectionHead>
      <P>Volume State answers: <em>is volume consistent with buying pressure (accumulation) or selling pressure (distribution)?</em> It uses two inputs: volume_expansion (today's volume relative to 20-day average) and effort_ratio_63 (price move per unit of volume — high effort = buyers controlling price).</P>
      <StateTable>
        <StateRow state="Accumulation"        bg="#e8f4ec" text="#2F6B43" meaning="High volume AND high effort ratio. Institutional buying: a lot of stock is changing hands with price moving decisively upward." when="volume_expansion ≥ threshold AND effort_ratio ≥ threshold" />
        <StateRow state="Steady-Buying"       bg="#e0f5ef" text="#1D9E75" meaning="Moderate volume expansion with decent effort. Demand is present but not urgent. Typically seen in healthy trending stocks between breakouts." when="moderate expansion AND effort above baseline" />
        <StateRow state="Neutral"             bg="#f5f5f5" text="#5a5a5a" meaning="No strong pattern in either direction. Default state." when="No distribution or accumulation conditions met" />
        <StateRow state="Distribution"        bg="#fdf0ee" text="#B0492C" meaning="Low effort ratio — price is not moving proportionally to volume. Sellers are absorbing demand without allowing price to rise, or price is falling on volume." when="effort_ratio ≤ distribution threshold" />
        <StateRow state="Heavy Distribution"  bg="#fce8e4" text="#8B2E1A" meaning="Very low effort AND expanding volume. Aggressive liquidation — large sellers are active and the stock is struggling to hold. Highest urgency warning." when="effort_ratio ≤ heavy-dist threshold AND volume_expansion ≥ 1.0" />
      </StateTable>
    </div>
  )
}

function TabRegime() {
  return (
    <div>
      <P>The market regime is a single daily classification that answers one question: <em>how favourable is the broad market environment for deploying capital?</em> It drives the deployment multiplier — a scaling factor for position sizing.</P>

      <SectionHead id="regimes">The four regimes</SectionHead>
      <div className="space-y-3 mb-6">
        {[
          { label: 'Risk-On', mult: '1.0×', bg: '#e8f4ec', text: '#2F6B43', desc: 'Nifty 500 above EMA-200, majority of stocks above their 50-day EMAs, VIX subdued. Full deployment. All sectors potentially active.', triggers: 'Nifty500 > EMA-200 AND pct_above_ema_50 above threshold AND VIX below risk-on maximum' },
          { label: 'Constructive', mult: '0.7×', bg: '#f0f8f4', text: '#2F6B43', desc: 'Broad market healthy but breadth less convincing — fewer stocks participating. Reduce new positions slightly, favour highest-conviction names.', triggers: 'Nifty500 > EMA-200 AND pct_above_ema_50 in moderate range AND VIX below constructive maximum' },
          { label: 'Cautious', mult: '0.4×', bg: '#fdf8ee', text: '#B8860B', desc: 'Market near its trend line OR breadth deteriorating OR VIX elevated. Cut deployment significantly. Protect existing winners. Raise cash.', triggers: 'Nifty500 near EMA-200 (within band) OR breadth weakening trend OR VIX in cautious range' },
          { label: 'Risk-Off', mult: '0.0×', bg: '#fce8e4', text: '#8B2E1A', desc: 'Nifty 500 below EMA-200, breadth collapsed, VIX high. Capital preservation only. No new longs. Let existing positions run their stops.', triggers: 'Nifty500 < EMA-200 AND pct_above_ema_50 below threshold AND VIX above cautious maximum' },
        ].map(r => (
          <div key={r.label} className="border border-paper-rule rounded-sm p-4">
            <div className="flex items-baseline gap-3 mb-1.5">
              <span className="inline-flex items-center px-2.5 py-0.5 rounded-sm font-sans text-[11px] font-bold" style={{ background: r.bg, color: r.text }}>{r.label}</span>
              <span className="font-mono text-sm font-semibold text-ink-primary">Deploy {r.mult}</span>
            </div>
            <p className="font-sans text-xs text-ink-secondary leading-relaxed mb-1">{r.desc}</p>
            <p className="font-sans text-[10px] text-ink-tertiary italic">{r.triggers}</p>
          </div>
        ))}
      </div>
      <Callout color="warn">
        <strong>Constructive is not a separate stage in Atlas UI.</strong> The Intelligence dashboard groups it with Risk-On as "green." In the underlying data it carries a 0.7× multiplier so position sizing is still dialled back slightly. Check the actual multiplier in the regime hero card.
      </Callout>

      <SectionHead id="breadth">What each breadth indicator means</SectionHead>
      <P>The regime card shows six breadth metrics. Here is what each one tells you:</P>
      <div className="space-y-3 mb-4">
        {[
          { metric: 'Deploy %', desc: 'The deployment multiplier as a percentage (e.g. 100% = Risk-On, 40% = Cautious). This is the single most actionable number on the whole dashboard.' },
          { metric: 'VIX', desc: 'India VIX — the 30-day implied volatility of the Nifty 50. Below ~15: calm market. 15–20: moderate uncertainty. Above 20: fear is elevated. Above 25: potential dislocation. Note: VIX missing or stale does not trigger Risk-Off on its own — it only acts as a confirming gate.' },
          { metric: 'Above EMA-50', desc: 'Percentage of Nifty 500 stocks trading above their 50-day exponential moving average. This is the primary breadth signal: above 60% = broad participation. Below 40% = narrow leadership, warning. Below 30% = broad deterioration.' },
          { metric: 'A/D Ratio', desc: 'Advance-Decline Ratio: advancing stocks ÷ declining stocks on that day. Above 1.5 = strongly positive day. Below 0.7 = broadly negative. The McClellan Oscillator is the smoothed, cumulative version of this.' },
          { metric: 'McClellan', desc: 'The McClellan Oscillator is a 19/39-day EMA of the daily advance-decline difference. Positive = more stocks advancing than declining on a smoothed basis (breadth improving). Negative = deteriorating. Readings above +100 or below -100 are extreme.' },
          { metric: 'Net NH-NL', desc: 'Net New 52-week Highs minus New 52-week Lows over the past 252 trading days. Strongly positive = bull market expansion. Near zero in a rising index = narrowing leadership (unhealthy). Negative = broad bear market.' },
        ].map(b => (
          <div key={b.metric} className="flex gap-3 text-sm">
            <span className="font-mono text-[11px] font-semibold text-teal shrink-0 pt-0.5 w-28">{b.metric}</span>
            <span className="font-sans text-[11px] text-ink-secondary leading-relaxed">{b.desc}</span>
          </div>
        ))}
      </div>

      <SectionHead id="dislocation">Market dislocation override</SectionHead>
      <P>When extreme conditions are detected (VIX spike, Nifty circuit-breaker day, or manual override), Atlas enters dislocation mode. All four stock states are suspended — replaced with DISLOCATION_SUSPENDED — and the deployment multiplier is forced to 0.0×. This prevents the system from generating conviction signals during intraday chaos.</P>
    </div>
  )
}

function TabSectors() {
  return (
    <div>
      <P>The Sectors page gives you a top-down view of capital rotation across 11 NIFTY sectors. Three frameworks run together: the <strong>RRG Quadrant</strong> (rotation position), the <strong>Hybrid Sector Classifier</strong> (actionability label), and the <strong>Weinstein stage breadth</strong> (bottom-up stock states). Use all three together.</P>

      <SectionHead id="rrg">RRG — Relative Rotation Graph</SectionHead>
      <P>The RRG places each sector on a 2×2 grid based on two axes: <strong>RS Level</strong> (is the sector stronger or weaker than median?) and <strong>RS Velocity</strong> (is that relative strength improving or declining?). The typical rotation path is clockwise: Leading → Weakening → Lagging → Improving → Leading.</P>
      <div className="grid grid-cols-2 gap-2 mb-4 text-xs">
        {[
          { quad: 'Leading',   corner: 'Top-Right',    bg: '#e8f4ec', text: '#2F6B43', desc: 'Above-median RS, and RS is still improving. The best sectors to hold. Institutions are accumulating.' },
          { quad: 'Weakening', corner: 'Top-Left',     bg: '#fdf8ee', text: '#B8860B', desc: 'Above-median RS, but RS is starting to roll over. Profit-taking may begin. Review exposures.' },
          { quad: 'Lagging',   corner: 'Bottom-Left',  bg: '#fce8e4', text: '#8B2E1A', desc: 'Below-median RS and RS is falling. The worst sectors. Avoid or underweight.' },
          { quad: 'Improving', corner: 'Bottom-Right', bg: '#e0f5ef', text: '#1D9E75', desc: 'Below-median RS, but RS is turning up. Early rotation signal — potential entry for tactical positioning.' },
        ].map(q => (
          <div key={q.quad} className="border border-paper-rule rounded-sm p-3" style={{ background: q.bg + '60' }}>
            <div className="flex items-baseline gap-2 mb-1">
              <span className="font-sans text-[10px] font-bold" style={{ color: q.text }}>{q.quad}</span>
              <span className="font-sans text-[9px] text-ink-tertiary">{q.corner}</span>
            </div>
            <p className="font-sans text-[10px] text-ink-secondary leading-relaxed">{q.desc}</p>
          </div>
        ))}
      </div>
      <P><strong>How the quadrant is assigned:</strong> RS Level uses cross-sectional PERCENT_RANK of the sector&apos;s bottom-up 3M RS score across all 11 sectors. RS Velocity is the 4-week rate-of-change of that RS score. Median RS = 50th percentile. Velocity ≥ 0 = improving.</P>
      <Callout color="teal">
        <strong>Reading rotation:</strong> Watch for sectors crossing quadrant boundaries, not just their current position. A sector that was Lagging last month and is now Improving is more interesting than one that has been Leading for 6 months. The Atlas Sector page shows the current date&apos;s snapshot; for history, look at the trend in the RS level and velocity columns.
      </Callout>

      <SectionHead id="hybrid-classifier">Hybrid rank + absolute floor — the sector classifier</SectionHead>
      <P>The sector label (Overweight / Neutral / Underweight / Avoid) is assigned by a <strong>hybrid rank + absolute floor</strong> model. It has two parts that work together:</P>
      <SubHead>Part 1 — Daily cross-sectional rank</SubHead>
      <P>Every day, all sectors are scored on a composite built from bottom-up signals: <code className="font-mono text-[10px] bg-paper-rule/30 px-1">pct_stage_2</code> (share of constituents in mark-up), <code className="font-mono text-[10px] bg-paper-rule/30 px-1">mean_within_state_rank</code> (conviction of those constituents), and sector RS. Sectors are then ranked against each other and assigned a label by percentile band:</P>
      <div className="space-y-2 mb-4 mt-3">
        {[
          { s: 'Overweight',  band: 'Top quintile (≥ 80th pct)', c: '#e8f4ec', tc: '#2F6B43', d: 'The relatively strongest sectors. Tilt towards these vs benchmark — subject to the absolute floor (see below).' },
          { s: 'Neutral',     band: '50th–80th pct',             c: '#f5f5f5', tc: '#5a5a5a', d: 'Middle-ground. Maintain current allocation; no strong directional signal.' },
          { s: 'Underweight', band: '20th–50th pct',             c: '#fdf0ee', tc: '#B0492C', d: 'Below-median strength. Reduce allocation vs benchmark.' },
          { s: 'Avoid',       band: 'Bottom quintile (< 20th)',  c: '#fce8e4', tc: '#8B2E1A', d: 'The relatively weakest sectors. Minimum allocation. Not necessarily down in absolute terms — it is the weakest of the available options today.' },
        ].map(s => (
          <div key={s.s} className="flex gap-3 items-start text-xs p-2 rounded-sm border border-paper-rule">
            <div className="shrink-0 w-28">
              <span className="inline-flex items-center px-2 py-0.5 rounded-sm font-sans text-[10px] font-bold" style={{ background: s.c, color: s.tc }}>{s.s}</span>
              <div className="font-mono text-[9px] text-ink-tertiary mt-0.5">{s.band}</div>
            </div>
            <span className="font-sans text-[11px] text-ink-secondary leading-relaxed">{s.d}</span>
          </div>
        ))}
      </div>
      <P>Because the assignment is relative, the classifier always produces a spread — it can never collapse to one constant label regardless of market conditions.</P>
      <SubHead>Part 2 — Absolute floor (keeps the top label honest)</SubHead>
      <P>A sector may <em>hold</em> the Overweight label only if its absolute breadth clears a minimum bar — a floor on <code className="font-mono text-[10px] bg-paper-rule/30 px-1">pct_stage_2</code> calibrated from historical distribution. If the relative-best sector fails the floor, its label caps at Neutral. The ranking is still visible, but the label stays honest.</P>
      <Callout color="warn">
        <strong>In a genuine thin-breadth market</strong>, you may see no Overweight sectors — only Neutral at best. That is the floor doing its job: it prevents a falsely reassuring label when even the &ldquo;best&rdquo; sector has very thin Stage-2 breadth. The regime&apos;s deployment multiplier governs overall capital deployment; the sector labels govern where within that capital to tilt.
      </Callout>

      <SectionHead id="weinstein-aggregation">Weinstein stage breadth — the bottom-up truth</SectionHead>
      <P>Every sector metric is derived bottom-up from the individual stock Weinstein states (see the <strong>Stock States</strong> tab). The key aggregated metrics per sector:</P>
      <ul className="space-y-1.5 mb-4 ml-2 font-sans text-xs text-ink-secondary">
        <li><strong>pct_stage_2</strong> — share of sector constituents classified Stage 2A / 2B / 2C (the mark-up / uptrend zone). The primary health signal for a sector.</li>
        <li><strong>pct_stage_3 / pct_stage_4</strong> — share in distribution / decline. Rising pct_stage_4 is the first warning of a sector breaking down.</li>
        <li><strong>mean_within_state_rank</strong> — average conviction score of Stage-2 stocks in the sector. A sector can have high pct_stage_2 with low conviction (breadth without quality) or the reverse.</li>
        <li><strong>Participation %</strong> — share of stocks with positive RS, ranked cross-sectorally (not an absolute threshold). A sector with 20% participation can still be the highest-participation sector available.</li>
      </ul>

      <SectionHead id="fund-classifier">Fund classifier — the same hybrid model</SectionHead>
      <P>The fund recommendation label (Recommended / Hold / Reduce / Exit) uses the same hybrid rank + absolute floor approach applied to mutual funds and ETFs. Each fund is scored on: NAV state (the fund&apos;s own price trend), holdings quality (share of AUM in strong-state stocks), and fund RS vs benchmark. Funds are ranked cross-sectionally and assigned labels by percentile band, with an absolute floor that prevents Recommended unless the fund clears a minimum holdings-quality bar.</P>
      <P>Inside the decision flow, funds/ETFs compete on the same bottom-up Weinstein states as their underlying stocks. The verdict label is shown alongside the rank, but the <em>ranking</em> within a sector target is bottom-up — it reflects holdings quality, not the fund manager&apos;s marketing.</P>

      <SectionHead id="sector-reading">How to read the Sectors page</SectionHead>
      <P>The Sectors page has two views: an <strong>RRG scatter plot</strong> (position in the rotation cycle) and a <strong>sector table</strong> (all metrics at a glance). Click any sector row to enter the Sector Deep Dive, which shows the individual stocks within that sector ranked by conviction.</P>
      <P>Key columns in the sector table:</P>
      <ul className="space-y-1.5 mb-4 ml-2 font-sans text-xs text-ink-secondary">
        <li><strong>RS Level</strong> — bottom-up median 3M RS of all stocks in the sector vs Nifty 500</li>
        <li><strong>RS Velocity</strong> — 4-week change in RS Level. Positive = sector gaining ground. Negative = losing.</li>
        <li><strong>pct Stage 2</strong> — share of sector stocks in the mark-up zone. The primary health signal; feeds the hybrid classifier.</li>
        <li><strong>Sector State</strong> — Overweight / Neutral / Underweight / Avoid. Always relative; always a spread. The absolute floor prevents the top label when breadth is genuinely poor.</li>
        <li><strong>RRG Quadrant</strong> — Leading / Improving / Weakening / Lagging</li>
      </ul>
    </div>
  )
}

function TabConviction({ activeSets }: { activeSets: { tier: string; predicted_ic: string | null }[] }) {
  const TIER_LABEL: Record<string, string> = {
    tier_1_megacap: 'T1 · Mega-cap (Nifty 50)',
    tier_2_largecap: 'T2 · Large-cap (51–150)',
    tier_3_uppermid: 'T3 · Upper mid-cap (151–300)',
    tier_4_lowermid: 'T4 · Lower mid-cap (301–500)',
    tier_5_smallcap: 'T5 · Small-cap (501–1000)',
  }
  function fmtIc(v: string | null) {
    if (!v) return '—'
    const n = parseFloat(v)
    return `${n >= 0 ? '+' : ''}${n.toFixed(4)}`
  }
  function icLabel(v: string | null) {
    if (!v) return { l: 'Descriptive', c: 'text-ink-tertiary' }
    const n = Math.abs(parseFloat(v))
    if (n >= 0.05) return { l: '★ Industry-grade', c: 'text-teal' }
    return { l: 'Baseline', c: 'text-ink-secondary' }
  }

  return (
    <div>
      <P>Conviction is a single score from 0 to 100 attached to every stock in the top ~1,000 by liquidity. It answers: <em>how aligned are all of this stock's quantitative signals right now?</em> It is a composite of eleven independent signals, weighted by how well each signal has predicted future returns.</P>

      <SectionHead id="signals">The eleven signals</SectionHead>
      <div className="overflow-x-auto border border-paper-rule rounded-sm mb-5">
        <table className="w-full font-sans text-xs">
          <thead>
            <tr className="border-b border-paper-rule bg-paper-rule/10">
              <th className="text-left px-3 py-2 font-semibold text-[10px] uppercase tracking-wider text-ink-tertiary">Signal</th>
              <th className="text-left px-3 py-2 font-semibold text-[10px] uppercase tracking-wider text-ink-tertiary">What it measures</th>
              <th className="text-left px-3 py-2 font-semibold text-[10px] uppercase tracking-wider text-ink-tertiary">Interpretation</th>
            </tr>
          </thead>
          <tbody>
            {[
              ['rs_pctile_3m', '3-month RS percentile', 'Where the stock ranks vs the full universe over 3 months. The primary momentum signal.'],
              ['ret_6m', '6-month return', 'Absolute price return over the prior 6 months. Captures intermediate-term momentum.'],
              ['ret_12m_minus_1m', '12-month return ex last month', 'Classic momentum: 12-month return skipping the most recent month (avoids mean-reversion noise).'],
              ['slope_30w', '30-week price slope', 'Direction and steepness of the 30-week (Weinstein) trend. Positive = uptrend. Captures long-term price trajectory.'],
              ['dist_from_ema', 'Distance from 200-day EMA', 'How far price is from its long-term anchor. Extreme distance can signal overbought/oversold.'],
              ['vol_ratio_63', '63-day realized vol ratio', 'Current 63-day vol divided by trailing-year median vol. High ratio = elevated risk environment.'],
              ['effort_ratio_63', '63-day effort ratio', 'Price move per unit of volume. Measures whether volume is productive (buying) or unproductive (selling into strength).'],
              ['realized_vol_63', '63-day realized volatility', 'Absolute volatility level. Lower vol = tighter trend. Used as a risk-adjustment factor.'],
              ['max_drawdown_63', '63-day maximum drawdown', 'How much the stock fell from peak within the window. Large drawdowns reduce conviction.'],
              ['ema_ratio', 'EMA-10 / 200d SMA ratio', 'Short-term trend vs long-term trend. Above 1.0 = in uptrend. The Momentum State driver.'],
              ['atr_ratio', 'ATR ratio', 'Average True Range vs price. A measure of volatility-adjusted momentum. Lower ATR in an uptrend = orderly advance.'],
            ].map(([sig, what, interp]) => (
              <tr key={sig} className="border-b border-paper-rule/40 align-top">
                <td className="px-3 py-2 font-mono text-[10px] text-teal">{sig}</td>
                <td className="px-3 py-2 text-ink-primary">{what}</td>
                <td className="px-3 py-2 text-ink-secondary">{interp}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <SectionHead id="ic">What is IC (Information Coefficient)?</SectionHead>
      <P>IC is the rank-correlation between a signal's value today and the actual realized return 21 trading days later. It is the honest answer to: <em>does this signal actually predict anything?</em></P>
      <div className="border border-paper-rule rounded-sm overflow-hidden mb-4">
        {[
          { val: 'IC = 0.00', meaning: 'The signal is no better than a coin flip. Weight = 0 in the composite.' },
          { val: 'IC = 0.03', meaning: 'Weak. Slightly better than random. Included but down-weighted. "Baseline" tier.' },
          { val: 'IC = 0.05', meaning: 'Industry-grade. Right ~52% of the time — that 2% edge compounds to real money over 500+ bets a year. Highest weight.' },
          { val: 'IC = 0.10', meaning: 'Excellent. Right ~55% of the time. Very rare in practice for any single signal.' },
          { val: 'IC negative', meaning: 'The signal predicts the OPPOSITE direction. Atlas flips the signal (multiplies by -1) so it still contributes positively to conviction.' },
        ].map((row, i) => (
          <div key={i} className={`flex gap-4 px-4 py-2.5 ${i < 4 ? 'border-b border-paper-rule/40' : ''}`}>
            <span className="font-mono text-[11px] font-semibold text-ink-primary shrink-0 w-20">{row.val}</span>
            <span className="font-sans text-[11px] text-ink-secondary leading-relaxed">{row.meaning}</span>
          </div>
        ))}
      </div>
      <Callout color="teal">
        A single signal with IC = 0.05 means it correctly identifies the top performers 52% of the time. Over 500 independent bets per year, that 2% edge — compounded, diversified, risk-managed — is the entire basis of systematic active management. You are not looking for signals that are always right; you are looking for signals that are right slightly more often than chance, consistently.
      </Callout>

      <SectionHead id="tiers">Liquidity Tiers — why one weight set is wrong</SectionHead>
      <P>The signals that predict Nifty 50 mega-caps behave differently from the signals that predict mid-cap breakouts. So Atlas splits the ~1,000-stock universe into five tiers by 20-day average daily traded value (ADTV) and computes a <strong>separate weight set per tier</strong>. Current active weights and their IC:</P>
      {activeSets.length > 0 ? (
        <div className="overflow-x-auto border border-paper-rule rounded-sm mb-5">
          <table className="w-full font-sans text-xs">
            <thead>
              <tr className="border-b border-paper-rule bg-paper-rule/10">
                <th className="text-left px-3 py-2 font-semibold text-[10px] uppercase tracking-wider text-ink-tertiary">Tier</th>
                <th className="text-right px-3 py-2 font-semibold text-[10px] uppercase tracking-wider text-ink-tertiary">Predicted IC</th>
                <th className="text-left px-3 py-2 font-semibold text-[10px] uppercase tracking-wider text-ink-tertiary">Confidence</th>
              </tr>
            </thead>
            <tbody>
              {activeSets.map(s => {
                const { l, c } = icLabel(s.predicted_ic)
                return (
                  <tr key={s.tier} className="border-b border-paper-rule/40">
                    <td className="px-3 py-2 text-ink-primary">{TIER_LABEL[s.tier] ?? s.tier}</td>
                    <td className="px-3 py-2 text-right font-mono tabular-nums text-ink-primary">{fmtIc(s.predicted_ic)}</td>
                    <td className={`px-3 py-2 font-semibold ${c}`}>{l}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="font-sans text-xs text-ink-tertiary mb-4">No active weight sets loaded yet.</p>
      )}
      <P>A conviction score of 80 in a Tier 1 (industry-grade) weight set is more meaningful than 80 in a Tier 4 (baseline) set. The UI shows tier badges on every conviction number — do not compare conviction across tiers without checking the badge.</P>

      <SectionHead id="optimization">The nightly optimization loop</SectionHead>
      <P>Weights are not static. Every night Atlas runs:</P>
      <ol className="space-y-2 ml-4 mb-4 list-decimal list-outside font-sans text-sm text-ink-secondary leading-relaxed">
        <li><strong>Measure IC</strong> — recompute rolling 90-day IC per signal per tier. Write to atlas_signal_ic_rolling.</li>
        <li><strong>Propose</strong> — if measured IC differs materially from current weights (max Δ ≥ 0.05), generate a candidate weight set. Push to <Link href="/admin/composite-proposals" className="text-teal hover:underline">Signal Proposals</Link>.</li>
        <li><strong>Approve + blend</strong> — FM approves. New active weight = <strong>0.85 × current + 0.15 × proposed</strong>. The 15% Bayesian blend captures most of the predicted lift while keeping the live composite stable.</li>
        <li><strong>Monitor + auto-revert</strong> — realized IC is tracked nightly post-approval. If realized stays below 50% of predicted for 60 consecutive days, the system auto-reverts. See <Link href="/admin/weight-performance" className="text-teal hover:underline">Weight Performance</Link>.</li>
      </ol>

      <SectionHead id="cts">CTS Timing Engine — stage + entry signals</SectionHead>
      <P>SP09 adds a Weinstein-inspired timing layer on top of the conviction composite. Every stock gets a <strong>Stage</strong> classification plus optional entry/exit signals. The stage tells you WHERE the stock is in its price cycle.</P>
      <div className="space-y-2 mb-4">
        {[
          { s: 'Stage 1 / 1B', c: '#e8eef5', tc: '#25394A', d: 'Basing / Stage 1 Base. Price is flat near the 30-week SMA, below the 200-EMA or just crossing above it. Accumulation phase. Wait for breakout confirmation.' },
          { s: 'Stage 2',       c: '#e8f4ec', tc: '#2F6B43', d: 'Mark-up. Price above 30-week SMA, SMA rising. The optimal holding zone. Most PPC signals fire here.' },
          { s: 'Stage 3',       c: '#fdf8ee', tc: '#B8860B', d: 'Distribution / topping. SMA flattening. Upside limited. Begin reducing exposure. NPC signals may appear.' },
          { s: 'Stage 4',       c: '#fce8e4', tc: '#8B2E1A', d: 'Mark-down. Price below 30-week SMA, SMA declining. Avoid or short. NPC signals fire here.' },
        ].map(r => (
          <div key={r.s} className="flex gap-3 p-3 border border-paper-rule rounded-sm items-start">
            <span className="inline-flex items-center px-2 py-0.5 rounded-sm font-sans text-[10px] font-bold shrink-0" style={{ background: r.c, color: r.tc }}>{r.s}</span>
            <span className="font-sans text-[11px] text-ink-secondary leading-relaxed">{r.d}</span>
          </div>
        ))}
      </div>
      <SubHead>The three CTS signals</SubHead>
      <div className="space-y-2 mb-4 font-sans text-xs">
        {[
          { sig: 'PPC — Pocket Pivot (constructive)', color: 'text-signal-pos', d: 'A bullish volume event in Stage 2: today\'s up-day volume exceeds the highest down-day volume of the prior 10 days. The stock is in a strong RS percentile (≥60th cross-sector), within 15% of its 52-bar high, and the close is in the upper half of the day\'s range. PPC = institutions are accumulating aggressively.' },
          { sig: 'NPC — Negative Pocket Pivot (distribution)', color: 'text-signal-neg', d: 'The mirror of PPC in Stage 3 or 4: down-day volume exceeds the highest up-day volume of the prior 10 days, with weak RS (≤40th percentile). NPC = institutional distribution is underway.' },
          { sig: 'Contraction', color: 'text-signal-warn', d: 'A tight, low-volume range: the daily price range is the narrowest in the prior N bars AND the bar range is contracting. Typically precedes a breakout in either direction. Combine with RS and stage to determine direction bias.' },
        ].map(s => (
          <div key={s.sig} className="p-3 border border-paper-rule rounded-sm">
            <div className={`font-semibold text-[11px] mb-1 ${s.color}`}>{s.sig}</div>
            <div className="text-ink-secondary leading-relaxed">{s.d}</div>
          </div>
        ))}
      </div>
      <P>CTS signals appear as a badge row on each stock's deep-dive page. A blank CTS section means the stock did not trigger any signal on the most recent trading day.</P>
    </div>
  )
}

function TabAdmin() {
  return (
    <div>
      <P>The Admin section has four pages. Each serves a specific role in the oversight and tuning of the Atlas system. None of these actions affect calculations retroactively — they only change forward behaviour.</P>

      <SectionHead id="proposals">Signal Proposals — <Link href="/admin/composite-proposals" className="text-teal hover:underline">composite-proposals</Link></SectionHead>
      <P>When Atlas's nightly IC measurement detects a material drift (any signal weight needing to shift by more than 0.05), it generates a candidate weight set and writes it here for FM review.</P>
      <SubHead>What you see on this page</SubHead>
      <ul className="space-y-2 mb-4 ml-2 font-sans text-xs text-ink-secondary">
        <li><strong>Tier</strong> — which liquidity tier this proposal is for</li>
        <li><strong>Predicted IC</strong> — the IC the new weights are expected to achieve, based on the training window</li>
        <li><strong>Current IC</strong> — the IC of the currently live weight set</li>
        <li><strong>Max Δ Weight</strong> — the largest single-signal weight change in the proposal. A number above 0.10 is a significant structural shift.</li>
        <li><strong>Signal breakdown</strong> — a table of all 11 signals, their current weight, and proposed new weight</li>
      </ul>
      <SubHead>The three actions</SubHead>
      <div className="space-y-2 mb-4 font-sans text-xs">
        {[
          { a: 'Approve', c: 'text-signal-pos', d: 'Blends the proposal in at 15% weight: new_active = 0.85 × current + 0.15 × proposed. Conviction scores will shift slightly on tomorrow\'s run. The system then starts tracking realized IC against the prediction.' },
          { a: 'Reject', c: 'text-signal-neg', d: 'Marks this proposal dead. The nightly loop will likely generate a new proposal the following night if the IC gap still exceeds the threshold. Rejecting is appropriate when you believe the recent data window is distorted (e.g. an event-driven outlier period).' },
          { a: 'Snooze', c: 'text-signal-warn', d: 'Defers reconsideration until a specific date. Use this when you want to let a market event pass before deciding. The proposal appears in a "Snoozed" queue and re-activates on the chosen date.' },
        ].map(a => (
          <div key={a.a} className="flex gap-3 p-3 border border-paper-rule rounded-sm">
            <span className={`font-bold shrink-0 w-14 ${a.c}`}>{a.a}</span>
            <span className="text-ink-secondary leading-relaxed">{a.d}</span>
          </div>
        ))}
      </div>
      <Callout color="teal">
        The FM <strong>never sets weights directly</strong>. The system always proposes; the FM approves, rejects, or snoozes. Every action is logged in atlas_weight_proposals with reviewer, notes, and timestamp — the complete SEBI-auditable trail.
      </Callout>

      <SectionHead id="weight-perf">Weight Performance — <Link href="/admin/weight-performance" className="text-teal hover:underline">weight-performance</Link></SectionHead>
      <P>This page shows the live track record of every approved weight set: how the predicted IC at approval time compares to the realized IC measured nightly against actual market moves.</P>
      <ul className="space-y-2 mb-4 ml-2 font-sans text-xs text-ink-secondary">
        <li><strong>Realized IC (trailing)</strong> — measured daily over the prior 21-day forward window. Watch for consistent negative or near-zero realized IC.</li>
        <li><strong>Predicted vs Realized chart</strong> — the orange band is the predicted IC at approval. The line is the daily realized IC. When the line stays below 50% of the band for 60 consecutive days, auto-revert fires.</li>
        <li><strong>Hit Rate</strong> — % of days on which the top-quintile conviction stocks (by tier) outperformed the tier-median return. The hit rate needs 60+ days of data to stabilize.</li>
        <li><strong>Auto-revert status</strong> — shows the consecutive-days-below-threshold counter. When it hits 60, the previous weight set is automatically reinstated and a rejection event is written to the proposals log.</li>
      </ul>

      <SectionHead id="validator">Data Validator — <Link href="/admin/validator" className="text-teal hover:underline">validator</Link></SectionHead>
      <P>The Data Validator is a nightly automated audit agent that checks every data point on the frontend against its backend source. It runs pre-milestone, post-nightly-compute, and on-demand. Findings are classified into six types:</P>
      <div className="space-y-1.5 mb-4 font-sans text-xs">
        {[
          { cls: 'Gap', d: 'A value that should exist does not. Missing rows in a time series, missing sector assignments, NULL where a non-NULL is expected.' },
          { cls: 'Inconsistency', d: 'Two data points that should agree do not. E.g. the regime state shown in the frontend does not match the backend DB value.' },
          { cls: 'Calculation Error', d: 'A derived value that does not match the expected formula output. E.g. conviction scores recomputed outside the system do not match stored values.' },
          { cls: 'Accuracy Error', d: 'A value that is out of bounds for its domain. E.g. a percentile outside [0,1], a volatility of 0% when history exists.' },
          { cls: 'Insensible Value', d: 'Technically valid but logically suspicious. E.g. a stock with Laggard RS state but conviction score > 80.' },
          { cls: 'Incomplete Data', d: 'A page or component missing required columns or time range. E.g. a fund page showing only 3 months of NAV history when 3 years exist.' },
        ].map(c => (
          <div key={c.cls} className="flex gap-3 p-2.5 border border-paper-rule rounded-sm">
            <span className="font-semibold text-signal-warn shrink-0 w-28">{c.cls}</span>
            <span className="text-ink-secondary leading-relaxed">{c.d}</span>
          </div>
        ))}
      </div>

      <SectionHead id="policies">Policies — <Link href="/admin/policies" className="text-teal hover:underline">policies</Link></SectionHead>
      <P>Decision policies govern how conviction scores translate into portfolio actions. Policies are rules like "if conviction drops below X for a position we hold, flag for review" or "maximum 15% sector concentration." The Policies page lets you view and adjust these rules.</P>
      <P>Policies are applied in the simulation engine and in the portfolio page's decision overlay. Changing a policy takes effect on the next nightly compute — it does not retroactively change historical portfolio snapshots.</P>

      <SectionHead id="thresholds">Thresholds — tunable at runtime</SectionHead>
      <P>All state-classification cutoffs (the RS percentile quintiles, vol ratio bands, EMA convergence bands, etc.) are stored in the <code className="font-mono text-[10px] bg-paper-rule/30 px-1">atlas_thresholds</code> table and loaded at compute time. You never need to redeploy code to adjust a threshold — change the DB row, and the next nightly run picks it up.</P>
      <P>A <code className="font-mono text-[10px] bg-paper-rule/30 px-1">atlas_threshold_history</code> table captures every change with the previous value, new value, and timestamp. When a threshold change causes unexpected behaviour in state distributions, the history table shows you exactly when the change happened.</P>
      <Callout color="warn">
        <strong>Be conservative with threshold changes.</strong> The state distributions are designed to be stable — roughly 10–15% of stocks in each RS bucket. If you widen the top quintile to 30%, you inflate the Leader bucket and the conviction model's predictions become less reliable. Change one threshold at a time and watch the next morning's distribution before changing another.
      </Callout>
    </div>
  )
}

// ─── Main export ──────────────────────────────────────────────────────────────

export function MethodologyTabs({ activeSets }: { activeSets: { tier: string; predicted_ic: string | null }[] }) {
  const [tab, setTab] = useState<Tab>('overview')

  return (
    <div>
      {/* Tab bar */}
      <div className="flex flex-wrap gap-1 mb-6 pb-4 border-b border-paper-rule">
        {TABS.map(t => (
          <button key={t.key} onClick={() => setTab(t.key)}
            className={`px-3 py-1.5 rounded-sm font-sans text-[12px] font-medium transition-colors ${
              tab === t.key ? 'bg-ink-primary text-paper' : 'text-ink-secondary hover:text-ink-primary hover:bg-paper-rule/30'
            }`}>
            {t.label}
          </button>
        ))}
      </div>

      {/* Tab content */}
      {tab === 'overview'   && <TabOverview />}
      {tab === 'states'     && <TabStates />}
      {tab === 'regime'     && <TabRegime />}
      {tab === 'sectors'    && <TabSectors />}
      {tab === 'conviction' && <TabConviction activeSets={activeSets} />}
      {tab === 'admin'      && <TabAdmin />}
    </div>
  )
}
