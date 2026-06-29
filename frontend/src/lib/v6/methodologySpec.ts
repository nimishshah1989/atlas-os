// The Atlas methodology, as a plain-English tree for the Admin → Methodology tab.
// Structural nodes are authored; leaf metrics reference glossary keys (term) so the wording matches
// the column info-icons exactly. This reflects the CURRENT six-lens / decile / composite model and
// its roll-ups to sector / ETF / fund. Weights are the live atlas_thresholds values; sub-components
// are the columns stored in atlas_lens_scores_daily.
import type { MethoNode } from '@/components/v6/admin/MethodologyTree'

// helper: a leaf that pulls its text from the glossary
const m = (term: string): MethoNode => ({ id: term, title: '', term })

export const METHODOLOGY: MethoNode[] = [
  {
    id: 'score',
    title: 'The conviction score (one stock)',
    plain: 'Every stock gets a 0–100 conviction score. It is a weighted blend of four lenses, boosted when the lenses agree and adjusted for how expensive the stock is.',
    formula: 'composite = 0.30·Technical + 0.25·Fundamental + 0.25·Flow + 0.20·Catalyst (each a 0–100 lens score), × convergence boost (≥2 lenses agree), × valuation multiplier',
    children: [
      {
        id: 'technical', title: 'Technical', weight: '0.30',
        plain: 'Is the price trend healthy and is the stock leading the market? Sum of four sub-components.',
        formula: 'Technical score = Trend + Relative strength + Volatility contraction + Volume (points)',
        children: [
          { id: 'tech_trend', title: 'Trend', plain: 'Where price sits versus its moving averages and 1-year VWAP — is it in a clean uptrend?', children: [m('vwap'), m('ema_stack'), m('dist_ema'), m('rsi')] },
          { id: 'tech_rs', title: 'Relative strength', plain: 'Is the stock beating the market and its own sector?', children: [m('rs'), m('rs_sector'), m('pos_52w')] },
          { id: 'tech_volc', title: 'Volatility contraction', plain: 'Is volatility coiling — often a setup before a sharp move?', children: [m('vol_contraction'), m('atr')] },
          { id: 'tech_vol', title: 'Volume', plain: 'Is there heavier-than-usual participation behind the move?', children: [m('volume_ratio')] },
        ],
      },
      {
        id: 'fundamental', title: 'Fundamental', weight: '0.25',
        plain: 'Is the business actually good — profitable, growing, not over-leveraged? Sum of five sub-components.',
        formula: 'Fundamental score = Profitability + Margin + Growth + Balance sheet + Operating leverage (points)',
        children: [
          { id: 'fund_prof', title: 'Profitability', plain: 'How efficiently the company turns capital into profit.', children: [m('roe'), m('roce')] },
          { id: 'fund_marg', title: 'Margin', plain: 'How much of each rupee of revenue becomes profit.', children: [m('op_margin'), m('net_margin'), m('ebitda_margin')] },
          { id: 'fund_grow', title: 'Growth', plain: 'Is the top and bottom line growing year over year?', children: [m('rev_growth'), m('eps_growth')] },
          { id: 'fund_bs', title: 'Balance sheet', plain: 'Is leverage safe?', children: [m('debt_equity')] },
          { id: 'fund_olev', title: 'Operating leverage', plain: 'Is growth turning into margin expansion without piling on debt?' },
        ],
      },
      {
        id: 'flow', title: 'Flow', weight: '0.25',
        plain: 'Is informed money accumulating the stock? A weighted average of ownership and delivery signals (weights apply over the signals actually present).',
        children: [
          { id: 'flow_prom', title: 'Promoter', weight: '0.70', plain: 'Promoter (founder) ownership and insider open-market activity — rising stake is a positive signal.', children: [m('promoter')] },
          { id: 'flow_smart', title: 'Institutional / smart money', weight: '0.30', plain: 'Mutual-fund month-over-month delta, bulk deals and FII/DII shareholding shifts.', children: [m('smart_money')] },
          { id: 'flow_acc', title: 'Accumulation (delivery)', weight: '0.25', plain: 'Real ownership change, not intraday churn.', children: [m('delivery'), m('delivery_asym')] },
        ],
      },
      {
        id: 'catalyst', title: 'Catalyst', weight: '0.20',
        plain: 'Are there real events — order wins, results, capital actions — moving the stock? A weighted read of exchange filings, decayed by recency.',
        formula: 'Catalyst score = 0.55·Earnings & momentum + 0.30·Capital actions + 0.15·Governance',
        children: [
          { id: 'cat_earn', title: 'Earnings & momentum', weight: '0.55', plain: 'Results, guidance, credit-rating actions, dividends, order wins, press releases.' },
          { id: 'cat_cap', title: 'Capital actions', weight: '0.30', plain: 'Acquisitions, buybacks, bonus / split.' },
          { id: 'cat_gov', title: 'Governance', weight: '0.15', plain: 'Management & auditor changes, ESOP — lower weight, but scored.' },
        ],
      },
      {
        id: 'valuation', title: 'Valuation', weight: '0 (context)',
        plain: 'How expensive the stock is. NOT scored into conviction — it tunes the multiplier and is shown for context.',
        children: [m('pe'), m('pb'), m('ev_ebitda')],
      },
      {
        id: 'policy', title: 'Policy', weight: '0 (context)',
        plain: 'Government / sector policy, shown as a Red / Amber / Green sector alert — context for why, not scored into conviction.',
      },
    ],
  },
  {
    id: 'decile',
    title: 'From score to decile',
    plain: 'A raw 0–100 lens score only means something versus peers. Each lens score is ranked into deciles 1–10 WITHIN the stock’s own size cohort, so a small-cap competes only with small-caps.',
    formula: 'decile = ntile(10) over (cap cohort) ordered by the lens score — D10 = top 10%, D1 = bottom 10%',
    children: [
      m('cap_tier'),
      m('decile'),
      m('strength'),
      m('lead'),
      m('conviction_tier'),
    ],
  },
  {
    id: 'sector',
    title: 'Rolling up to a sector',
    plain: 'A sector’s read is its constituent stocks, grouped into four decile bands (D10 / D8–9 / D5–7 / D1–4). The decile distribution IS the composition; the headline conviction is the average constituent decile, and relative strength is measured on the sector INDEX.',
    formula: 'Conviction = mean(constituent strength). RS = sector-index return − Nifty return (per window). Breadth = share of constituents above each EMA.',
    children: [
      m('strength'),
      m('rs'),
      m('breadth_ema'),
      m('top_decile'),
      m('leadership_dist'),
      m('dispersion'),
    ],
  },
  {
    id: 'etf_fund',
    title: 'Rolling up to an ETF / fund',
    plain: 'An ETF or fund is its holdings, weighted by position size. Each lens score is the holdings-weighted average of the underlying stocks; leadership-breadth is the share of weight sitting in multi-factor leaders.',
    formula: 'weighted lens = Σ (holding weight × holding lens score) ÷ Σ weight. Leadership-breadth = weight in names that are top-decile in ≥2 lenses ÷ total weight.',
    children: [
      m('weighted_lens'),
      m('leadership_breadth'),
      m('leaders_count'),
      m('holdings_count'),
    ],
  },
  {
    id: 'fund_rank',
    title: 'Ranking funds in a category',
    plain: 'A fund is scored on the SAME lens composite as a stock or sector — applied to its holdings-weighted lens scores — then ranked against the other funds in its SEBI category. No separate scorecard model; the rank is as fresh as the holdings and the stock scores it rolls up from.',
    formula: 'Fund score = 0.30·Technical + 0.25·Fundamental + 0.25·Flow + 0.20·Catalyst over the holdings-weighted lens vector (0–100). Category rank = position by that score within the fund’s SEBI category (ties broken by leadership-breadth).',
    children: [
      m('fund_score'),
      m('cat_rank'),
      m('expense'),
    ],
  },
]
