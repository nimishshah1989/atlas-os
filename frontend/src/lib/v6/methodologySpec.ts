// The Atlas methodology, as a plain-English tree for the public Methodology page.
// Structural nodes are authored; leaf metrics reference glossary keys (term) so the wording matches
// the column info-icons exactly. This reflects the CURRENT lens / decile / composite model and its
// roll-ups to sector / ETF / fund. The top-level lens WEIGHTS are injected LIVE from
// atlas_thresholds (buildMethodology(weights)); each sub-component now carries its REAL scoring
// formula (point bands + thresholds), mirroring the live scorers in atlas/lenses/compute/*.py —
// Technical (each sub 0–25), Fundamental (each 0–20), Flow (0.70/0.30/0.25 over promoter/smart/
// accumulation), Catalyst (0.55/0.30/0.15, recency-decayed), Valuation (renorm → zone multiplier).
// These point values are the current scorer constants/defaults (tunable in atlas_thresholds).
// Sub-components are the columns stored in atlas_lens_scores_daily.
import type { MethoNode } from '@/components/v6/admin/MethodologyTree'
import type { LensWeightMap } from '@/lib/v6/sectorScore'

// helper: a leaf that pulls its text from the glossary
const m = (term: string): MethoNode => ({ id: term, title: '', term })

const fmt = (w: number) => w.toFixed(2)
const pct = (w: number) => `${Math.round(w * 100)}%`

// The composite formula string from the live weights — only the lenses that actually carry weight.
function compositeFormula(w: LensWeightMap): string {
  const parts = ([
    ['Technical', w.technical], ['Fundamental', w.fundamental], ['Flow', w.flow], ['Catalyst', w.catalyst],
  ] as const).filter(([, x]) => x > 0).map(([name, x]) => `${fmt(x)}·${name}`)
  const blend = parts.length ? parts.join(' + ') : '—'
  return `composite = ${blend} (each a 0–100 lens score), renormalised over the lenses present, × convergence boost (≥2 lenses agree), × valuation multiplier`
}

// Weight chip for a scored lens: live fraction + the % share, or "context" when weight 0.
const chip = (w: number) => (w > 0 ? `${fmt(w)} · ${pct(w)}` : '0 · context')

// Build the methodology tree with LIVE lens weights from atlas_thresholds.
export function buildMethodology(w: LensWeightMap): MethoNode[] {
  return [
    {
      id: 'score',
      title: 'The conviction score (one stock)',
      plain: 'Every stock gets a 0–100 conviction score. It is a weighted blend of the scored lenses (weights live from the thresholds panel), boosted when the lenses agree and adjusted for how expensive the stock is.',
      formula: compositeFormula(w),
      children: [
        {
          id: 'technical', title: 'Technical', weight: chip(w.technical),
          plain: 'Is the price trend healthy and is the stock leading the market? Four sub-scores, each 0–25.',
          formula: 'Technical (0–100) = mean of the present sub-scores × 4 (each sub is 0–25, so all four present → 0–100; missing inputs renormalise).',
          children: [
            { id: 'tech_trend', title: 'Trend', weight: '0–25', plain: 'Where price sits versus its moving averages and momentum — is it in a clean uptrend?',
              formula: 'EMA stack 21>50>200 → +10 (partial +6); price vs EMA-200 >+5% → +5 (>0 → +3, >−5% → +1); 1-week slope >+2% → +5 (>0 → +3, flat → +1); RSI 50–70 → +5 (30–50 → +3, >70 → +2, <30 → +1). Capped at 25.',
              children: [m('vwap'), m('ema_stack'), m('dist_ema'), m('rsi')] },
            { id: 'tech_rs', title: 'Relative strength', weight: '0–25', plain: 'Is the stock beating the market and its own sector?',
              formula: 'RS = stock trailing return − benchmark return (pp), horizon-blended 3m·0.40 + 1m·0.30 + 6m·0.20 + 12m·0.10; the Nifty-500 RS and the sector-index RS are averaged 50/50. Points: ≥+15pp → 25, ≥+8pp → 20, ≥+2pp → 15, ≥−8pp → 10, ≥−15pp → 5, else 0.',
              children: [m('rs'), m('rs_sector'), m('pos_52w')] },
            { id: 'tech_volc', title: 'Volatility contraction', weight: '0–25', plain: 'Is volatility coiling — often a setup before a sharp move?',
              formula: 'ATR% = ATR(14) ÷ price: <2% → 25, <3% → 20, <4% → 15, <6% → 10, else 5. Bollinger bonus: +5 if band width < 0.10 (capped at 25). Tighter = higher.',
              children: [m('vol_contraction'), m('atr')] },
            { id: 'tech_vol', title: 'Volume', weight: '0–25', plain: 'Is there heavier-than-usual participation behind the move?',
              formula: 'Relative volume (today ÷ 30-day avg) >2× → +10 (>1.2× → +7, >0.8× → +5, else +2); volume trend (60-day ÷ 30-day avg) >1.2 → +8 (>1.0 → +5, <0.8 → +2, else +3); 52-week position ≥80% → +7 (≥20% → +5, else +3). Capped at 25.',
              children: [m('volume_ratio')] },
          ],
        },
        {
          id: 'fundamental', title: 'Fundamental', weight: chip(w.fundamental),
          plain: 'Is the business actually good — profitable, growing, not over-leveraged? Five sub-scores, each 0–20.',
          formula: 'Fundamental (0–100) = Σ present sub-scores × 100 ÷ (20 × count) — each sub is 0–20; absent inputs renormalise, never imputed.',
          children: [
            { id: 'fund_prof', title: 'Profitability', weight: '0–20', plain: 'How efficiently the company turns capital into profit.',
              formula: 'ROE ≥20% → 11 (≥15 → 9, ≥12 → 7, ≥8 → 4, else 2) + a 0–1 continuous ROE premium; ROCE ≥20% → +7 (≥15 → +5, ≥12 → +3, ≥8 → +2, else +1); net margin ≥15% → +2 (≥8 → +1). Capped at 20.',
              children: [m('roe'), m('roce')] },
            { id: 'fund_marg', title: 'Margin', weight: '0–20', plain: 'How much of each rupee of revenue becomes profit.',
              formula: 'Operating margin >20% → 14 (>15 → 11, >10 → 8, >5 → 5, else 2); net margin >15% → +6 (>10 → +4, >5 → +2). Capped at 20.',
              children: [m('op_margin'), m('net_margin'), m('ebitda_margin')] },
            { id: 'fund_grow', title: 'Growth', weight: '0–20', plain: 'Is the top and bottom line growing year over year?',
              formula: 'Revenue YoY >25% → 12 (>15 → 9, >8 → 6, >0 → 3); EPS YoY >30% → +8 (>15 → +6, >5 → +4, >0 → +2). Capped at 20.',
              children: [m('rev_growth'), m('eps_growth')] },
            { id: 'fund_bs', title: 'Balance sheet', weight: '0–20', plain: 'Is leverage safe?',
              formula: 'D/E net-cash or <0.3 → 10 (<0.5 → 8, <1.0 → 6, <1.5 → 4, else 2); current ratio >2 → +5 (>1.5 → +4, >1 → +3, else +1); quick ratio >1.5 → +5 (>1 → +4, >0.5 → +2, else +1). Capped at 20.',
              children: [m('debt_equity')] },
            { id: 'fund_olev', title: 'Operating leverage', weight: '0–20', plain: 'Is growth turning into margin expansion without piling on debt?',
              formula: 'Revenue growth >15% AND operating margin >15% AND low D/E (net-cash or <0.5) → 20; high growth + one of those → 15; growth >8% + one → 10; any positive growth → 5; declining → 0.' },
          ],
        },
        {
          id: 'flow', title: 'Flow', weight: chip(w.flow),
          plain: 'Is informed money accumulating the stock? A weighted average of three ownership / delivery sub-scores, renormalised over the signals actually present.',
          formula: 'Flow (0–100) = (0.70·Promoter + 0.30·Smart-money + 0.25·Accumulation) ÷ Σ present weights.',
          children: [
            { id: 'flow_prom', title: 'Promoter', weight: '0.70', plain: 'Promoter (founder) holding level and insider open-market activity — rising stake / buying is positive.',
              formula: 'Holding-level base: ≥70% → 30, ≥55 → 22, ≥40 → 15, ≥25 → 8, >0 → 3. Plus insider deals: open-market buy +9, creeping-acquisition +7, warrant +7, pledge-decrease +6, preferential +3, ESOP +2; open-market sell −5, pledge-increase −8 (size/repeat amplifiers, per-type caps). 0–100.',
              children: [m('promoter')] },
            { id: 'flow_smart', title: 'Institutional / smart money', weight: '0.30', plain: 'Mutual-fund month-over-month delta, bulk deals and institutional shareholding shifts.',
              formula: 'Raw −10…+15 rescaled to 0–100 (0 → 50): matched mutual-fund MoM weight Δ (×scale, clamped −10…+12, the main signal) + bulk deals (superstar new entry +10 / exit −8, institutional buy +5 / sell −5) + QoQ institutional (100−promoter) change +6 / +3 / −4.',
              children: [m('smart_money')] },
            { id: 'flow_acc', title: 'Accumulation (delivery)', weight: '0.25', plain: 'Real ownership change settling into demat, not intraday churn.',
              formula: 'Base 50: delivery 30-day avg ≥60% → +8 (≤25% → −8); trend (30-day ÷ 60-day avg) ≥+12% → +20 (≥+5 → +10, ≤−12 → −20, ≤−5 → −10); up/down-day asymmetry ≥+8 → +15 (≥+3 → +8, ≤−8 → −15, ≤−3 → −8). 0–100; None below the liquidity floor.',
              children: [m('delivery'), m('delivery_asym')] },
          ],
        },
        {
          id: 'catalyst', title: 'Catalyst', weight: chip(w.catalyst),
          plain: 'Are there real events — order wins, results, capital actions — moving the stock? A weighted read of exchange filings, decayed by recency.',
          formula: 'Each filing scored, × recency multiplier (≤90 days ×1.0, ≤180 ×0.8, ≤365 ×0.5, older ×0.3), summed into three buckets (each clamped 0–100). Catalyst (0–100) = 0.55·Earnings + 0.30·Capital + 0.15·Governance.',
          children: [
            { id: 'cat_earn', title: 'Earnings & momentum', weight: '0.55', plain: 'Results, guidance, credit-rating actions, order wins, press releases.',
              formula: 'Credit-rating upgrade +15 (reaffirm +5, downgrade −10, watch −5); order award/LoA +12, bagging/secures +11, order received +10; press — order win +10, partnership/MoU +8, expansion/capacity +8, patent +6, litigation −3, adverse −5.' },
            { id: 'cat_cap', title: 'Capital actions', weight: '0.30', plain: 'Acquisitions, buybacks, dividends, bonus / split.',
              formula: 'Acquisition strategic/100%/majority +12 (subsidiary/JV +8, stake +8); buyback +10; dividend special/interim +10 (final +5); bonus +5; split +3.' },
            { id: 'cat_gov', title: 'Governance', weight: '0.15', plain: 'Management & auditor changes, ESOP — lower weight, but scored.',
              formula: 'Auditor mid-term/casual change −12 (rotation −2); management exit CEO/CFO/MD −8 (director −4); appointment CEO/CFO/MD +5 (KMP +3); ESOP +2.' },
          ],
        },
        {
          id: 'valuation', title: 'Valuation', weight: '0 · context',
          plain: 'How expensive the stock is. NOT scored into conviction — instead it maps to a zone that tunes the composite multiplier, and is shown for context.',
          formula: 'Valuation (0–100) = Σ present dimensions ÷ Σ their max × 100, over: PE vs sector (0–25, continuous — cheaper than the sector median scores higher), absolute PE (0–25: <8 → 25, <15 → 18, <25 → 10, <40 → 3, else 0), P/B (0–15: <1 → 15, <2 → 10, <4 → 5, <6 → 2), EV/EBITDA (0–20: <6 → 20, <10 → 14, <15 → 8, <20 → 3), 52-week position (0–15: cheaper-in-range scores higher). Zone → multiplier: ≥75 Deep Value ×1.15, ≥55 Cheap ×1.08, ≥35 Fair ×1.00, ≥20 Expensive ×0.90, else Overvalued ×0.75.',
          children: [m('pe'), m('pb'), m('ev_ebitda')],
        },
        {
          id: 'policy', title: 'Policy', weight: '0 · context',
          plain: 'Government / sector policy, shown as a Red / Amber / Green sector alert — context for why, not scored into conviction.',
        },
      ],
    },
    {
      id: 'decile',
      title: 'From score to decile',
      plain: 'A raw 0–100 lens score only means something versus peers. Each lens score is ranked into deciles 1–10 WITHIN the stock’s own size cohort, so a small-cap competes only with small-caps.',
      formula: 'decile = ntile(10) over (cap cohort) ordered by the lens score — D10 = top 10%, D1 = bottom 10%',
      children: [m('cap_tier'), m('decile'), m('strength'), m('lead'), m('conviction_tier')],
    },
    {
      id: 'sector',
      title: 'Rolling up to a sector',
      plain: 'A sector’s read is its constituent stocks, grouped into four decile bands (D10 / D8–9 / D5–7 / D1–4). The decile distribution IS the composition; the headline conviction is the average constituent decile, and relative strength is measured on the sector INDEX.',
      formula: 'Conviction = mean(constituent strength). RS = sector-index return − Nifty return (per window). Breadth = share of constituents above each EMA.',
      children: [m('strength'), m('rs'), m('breadth_ema'), m('top_decile'), m('leadership_dist'), m('dispersion')],
    },
    {
      id: 'etf_fund',
      title: 'Rolling up to an ETF / fund',
      plain: 'An ETF or fund is its holdings, weighted by position size. Each lens score is the holdings-weighted average of the underlying stocks; leadership-breadth is the share of weight sitting in multi-factor leaders.',
      formula: 'weighted lens = Σ (holding weight × holding lens score) ÷ Σ weight. Leadership-breadth = weight in names that are top-decile in ≥2 lenses ÷ total weight.',
      children: [m('weighted_lens'), m('leadership_breadth'), m('leaders_count'), m('holdings_count')],
    },
    {
      id: 'fund_rank',
      title: 'Ranking funds in a category',
      plain: 'A fund is scored on the SAME lens composite as a stock or sector — applied to its holdings-weighted lens scores — then ranked against the other funds in its SEBI category. No separate scorecard model; the rank is as fresh as the holdings and the stock scores it rolls up from. A daily rank history is kept so you can see a fund climb or slip within its category over time.',
      formula: 'Fund score = the live lens blend over the holdings-weighted lens vector (0–100). Category rank = position by that score within the fund’s SEBI category (ties broken by leadership-breadth). Percentile tag = where that rank sits in the category (Top 10/20/50% · Bottom 50%).',
      children: [m('fund_score'), m('cat_rank'), m('rank_trend'), m('expense')],
    },
  ]
}
