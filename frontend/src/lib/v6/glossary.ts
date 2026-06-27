// Central glossary for the eye-icon explainers (TermInfo). One definition per term,
// reused everywhere the term surfaces (derivation tree leaves, lens reads, tables).
// Keep definitions plain-English + one-line "why it matters" where useful — these are
// for a fund manager glancing, not a textbook.

export type GlossaryEntry = { title: string; body: string }

export const GLOSSARY: Record<string, GlossaryEntry> = {
  // ── technical ──
  vwap: {
    title: 'VWAP distance (1-year)',
    body: 'How far price sits from its 1-year Volume-Weighted Average Price (the average price paid, weighted by volume). Price tends to revert toward VWAP, so a large gap flags stretch — below VWAP can be a value re-entry, far above can be over-extension.',
  },
  ema_stack: {
    title: 'EMA trend stack',
    body: 'Whether the 21-, 50- and 200-day exponential moving averages are stacked in trend order. 21>50>200 = a clean uptrend (each shorter average above the longer); 21<50<200 = a downtrend. Mixed = no clear trend.',
  },
  dist_ema: {
    title: 'Price vs EMA',
    body: 'Percent distance between the current price and that exponential moving average. Positive = price above the average (trend support below); negative = price below it.',
  },
  rsi: {
    title: 'RSI(14)',
    body: 'Relative Strength Index over 14 days — momentum on a 0–100 scale. ~70+ is overbought (stretched up), ~30− oversold (stretched down), ~50 neutral.',
  },
  rs: {
    title: 'Relative strength (RS)',
    body: "The stock's return minus the benchmark's over the same window (in percentage points). Positive = it's beating the market; this is leadership vs the index, not absolute return.",
  },
  rs_state: {
    title: 'RS state',
    body: 'A label for the stock’s relative-strength trend vs the market — Leader / Strong / Emerging / Consolidating / Weak / Laggard — read from its RS level and slope, not a single window.',
  },
  baseline: {
    title: 'Baseline',
    body: 'The index a stock’s relative strength is measured against: Nifty 50 (large-cap anchor), Nifty 500 (broad market), or its own sector index.',
  },
  vol_contraction: {
    title: 'Volatility contraction (Bollinger width)',
    body: 'How tight the Bollinger Bands are (band width ÷ price). A low/contracting value means volatility is coiling — often a setup that precedes a sharp move once it expands.',
  },
  atr: {
    title: 'ATR(14)',
    body: 'Average True Range over 14 days — the typical daily price travel in rupees. A volatility gauge used for position-sizing and stop distance, not direction.',
  },
  volume_ratio: {
    title: 'Volume vs average',
    body: "Today's volume divided by its N-day average. Above 1× = heavier-than-usual participation (conviction behind the move); below 1× = thin.",
  },
  pos_52w: {
    title: '52-week range position',
    body: 'Where price sits within its trailing 52-week high–low band, as a percent. 100% = at the 1-year high, 0% = at the low.',
  },
  // ── flow ──
  delivery: {
    title: 'Delivery %',
    body: 'Share of traded volume that was actually taken to demat (delivered), not intraday-squared-off. Higher delivery = more genuine ownership change vs speculative churn.',
  },
  promoter: {
    title: 'Promoter holding',
    body: 'Percent of the company held by promoters (founders/controlling group). Rising promoter stake is a positive ownership signal; pledging or selling is a flag.',
  },
  smart_money: {
    title: 'Smart-money flow',
    body: 'Institutional / informed accumulation signal blended from delivery strength, bulk/block deals and institutional ownership change.',
  },
  // ── fundamental ──
  roe: { title: 'Return on equity (ROE)', body: 'Net profit as a percent of shareholders’ equity — how efficiently the company turns equity into profit.' },
  roce: { title: 'Return on capital (ROCE)', body: 'Operating profit as a percent of total capital employed (equity + debt) — profitability of the whole capital base, independent of financing.' },
  op_margin: { title: 'Operating margin', body: 'Operating profit ÷ revenue. Core profitability before interest and tax — pricing power and cost control.' },
  net_margin: { title: 'Net margin', body: 'Net profit ÷ revenue — the bottom-line take after all costs, interest and tax.' },
  debt_equity: { title: 'Debt / equity', body: 'Total debt ÷ shareholders’ equity — balance-sheet leverage. Lower is safer; high gearing amplifies both returns and risk.' },
  // ── valuation ──
  pe: { title: 'P/E (TTM)', body: 'Price ÷ trailing-12-month earnings per share — rupees paid per rupee of earnings. Compared to the stock’s own history and its sector.' },
  pb: { title: 'P/B', body: 'Price ÷ book value per share — valuation against net assets; most meaningful for financials and asset-heavy businesses.' },
  ev_ebitda: { title: 'EV / EBITDA', body: 'Enterprise value ÷ operating earnings before D&A — a capital-structure-neutral valuation multiple, good for cross-company comparison.' },
  // ── structure / scoring ──
  decile: { title: 'Decile (within cohort)', body: 'The stock’s rank from 1 (bottom 10%) to 10 (top 10%) versus peers of its OWN size cohort. D8–10 = leading, D1–4 = lagging.' },
  breadth_ema: { title: '% above EMA', body: 'Share of a sector’s constituents trading above their N-day exponential moving average. High participation = a broad advance; low = a narrow one carried by a few names.' },
  top_decile: { title: 'Top-decile count', body: 'How many of the sector’s stocks rank in the top decile (D10) of their cap cohort on this lens. More top-decile names = broader leadership, not a one-stock story.' },
  leadership_dist: { title: 'Leadership distribution', body: 'For each stock, how many conviction lenses it leads (top-decile) on — counted across the sector. 3–4/4 = multi-factor leaders; 0/4 = no edge on any lens.' },
  conviction: { title: 'Conviction', body: 'The headline 1–10 read = the average decile across the conviction lenses, with a boost when multiple lenses agree (convergence).' },
  dispersion: { title: 'Dispersion', body: 'How much the constituents disagree. Low dispersion = a broad, aligned move; high = the score is driven by a few names pulling in different directions.' },
  free_float_weight: { title: 'Free-float weight', body: 'Each constituent’s share of the sector by free-float market cap (the tradeable portion). Bigger names move the sector score more.' },
  leadership_breadth: { title: 'Leadership breadth', body: 'Share of holdings (by weight) that are multi-factor leaders — top-decile in ≥2 conviction lenses. Breadth shows whether strength is broad or concentrated.' },
  contribution: { title: 'Contribution', body: 'How much this item adds to the parent score = its weight × its score. Sorts who actually drives the number.' },
}
