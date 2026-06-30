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
  net_margin: { title: 'Net margin', body: 'Net profit ÷ revenue — the bottom-line take after all costs, interest and tax. At sector level this is revenue-weighted (sector-total PAT ÷ sector-total revenue), so the big names count more, not equally.' },
  debt_equity: { title: 'Debt / equity', body: 'Total debt ÷ shareholders’ equity — balance-sheet leverage. Lower is safer; high gearing amplifies both returns and risk.' },
  pct_profitable: { title: '% profitable', body: 'Share of the sector’s constituents that posted a positive bottom line (PAT > 0) in the latest filed quarter. A breadth read: high = profitability is broad-based; low = the sector’s margin is carried by a few names while many run losses.' },
  // ── valuation ──
  pe: { title: 'P/E (TTM)', body: 'Price ÷ trailing-12-month earnings per share — rupees paid per rupee of earnings. Compared to the stock’s own history and its sector.' },
  pb: { title: 'P/B', body: 'Price ÷ book value per share — valuation against net assets; most meaningful for financials and asset-heavy businesses.' },
  ev_ebitda: { title: 'EV / EBITDA', body: 'Enterprise value ÷ operating earnings before D&A — a capital-structure-neutral valuation multiple, good for cross-company comparison.' },
  // ── structure / scoring ──
  decile: { title: 'Decile (within cohort)', body: 'The stock’s rank from 1 (bottom 10%) to 10 (top 10%) versus peers of its OWN size cohort. D8–10 = leading, D1–4 = lagging.' },
  breadth_ema: { title: '% above EMA', body: 'Share of a sector’s constituents trading above their N-day exponential moving average. High participation = a broad advance; low = a narrow one carried by a few names.' },
  top_decile: { title: 'Top-decile count', body: 'How many of the sector’s stocks rank in the top decile (D10) of their cap cohort on this lens. More top-decile names = broader leadership, not a one-stock story.' },
  leadership_dist: { title: 'Leadership distribution', body: 'For each stock, how many of the two active conviction lenses (Technical & Flow) it leads — top-2-decile (D9/D10) — counted across the sector. 2/2 = leads both; 0/2 = no edge on either.' },
  ff_weight: { title: 'Free-float weight in sector', body: 'The stock’s share of the SECTOR’s total free-float market cap (free-float = market cap × the non-promoter, non-ESOP shareholding). It shows how concentrated the sector is: a few names near 100% = a top-heavy sector dominated by one or two stocks; weights spread evenly = a dispersed sector. Stocks without a market-cap reading show "—".' },
  conviction: { title: 'Conviction', body: 'The headline 1–10 read = the average decile across the conviction lenses, with a boost when multiple lenses agree (convergence).' },
  dispersion: { title: 'Dispersion', body: 'How much the constituents disagree. Low dispersion = a broad, aligned move; high = the score is driven by a few names pulling in different directions.' },
  free_float_weight: { title: 'Free-float weight', body: 'Each constituent’s share of the sector by free-float market cap (the tradeable portion). Bigger names move the sector score more.' },
  leadership_breadth: { title: 'Leadership breadth', body: 'Share of holdings (by weight) that are leaders — top-2-decile (D9/D10) in BOTH active conviction lenses, Technical and Flow. Breadth shows whether strength is broad or concentrated.' },
  contribution: { title: 'Contribution', body: 'How much this item adds to the parent score = its weight × its score. Sorts who actually drives the number.' },
  strength: { title: 'Strength (avg decile)', body: 'Average of the active-lens deciles — Technical and Flow — on a 1–10 scale. A high average means the name leads on both active lenses.' },
  lead: { title: 'Leadership count', body: 'How many of the two active conviction lenses (Technical, Flow) the stock leads — i.e. sits in the top two deciles (D9/D10) of its cap cohort. Ranges 0–2; a leader leads both.' },
  composite_score: { title: 'Conviction score (composite)', body: 'The 0–100 weighted conviction score = 0.30·Technical + 0.25·Fundamental + 0.25·Flow + 0.20·Catalyst (each a 0–100 lens score), then a convergence boost when ≥2 lenses agree and a valuation multiplier. Read from atlas_lens_scores_daily.' },
  sector_composite: { title: 'Sector score (composite)', body: 'The sector’s 0–100 conviction score = 0.30·Technical + 0.25·Fundamental + 0.25·Flow + 0.20·Catalyst, over the free-float-weighted sector lens vector. Click the row to see the exact derivation behind the number.' },
  sector_lens: { title: 'Sector lens score', body: 'The sector’s score on this lens (0–100) = the free-float-weighted average of its constituents’ scores on that lens. Bigger names move it more.' },
  conviction_tier: { title: 'Conviction tier', body: 'HIGHEST / HIGH / MEDIUM / WATCH / below-threshold, derived from the composite score together with how many lenses are active (scored). A high score on few lenses is capped to a lower tier.' },
  // ── returns / relative strength ──
  ret_window: { title: 'Return (window)', body: 'Price return over the labelled window = close ÷ close N ago − 1. Month-and-longer windows are calendar-anchored (price as of the date N months back), 1D/1W are session-based.' },
  rs_sector: { title: 'RS vs sector', body: "The stock's return minus its OWN sector index's return over the window (percentage points). Strips out sector beta, so it isolates whether the stock leads or lags inside its sector." },
  liq: { title: 'Liquidity (₹ Cr)', body: '≈20-session average daily traded value (close × volume), in ₹ crore. A tradability proxy — how much can be moved without disturbing the price.' },
  // ── identity / cohort ──
  cap_tier: { title: 'Cap tier', body: 'Size cohort by index membership: Large = Nifty 100, Mid = Nifty Midcap 150, Small = Nifty Smallcap 250, else Micro. All deciles are cut WITHIN this cohort so like is compared with like.' },
  sector_name: { title: 'Sector', body: 'The NSE industry sector the stock belongs to (folded to the canonical sector set). Drives the sector roll-ups and the RS-vs-sector column.' },
  // ── fund / ETF roll-up ──
  holdings_count: { title: 'Holdings', body: 'Number of scored, mapped equity holdings in the latest disclosed portfolio (cash and unmapped positions excluded from the lens base).' },
  leaders_count: { title: 'Leaders', body: 'Holdings that are leaders — top-2-decile (D9/D10) in BOTH active lenses, Technical and Flow. The base for leadership-breadth.' },
  expense: { title: 'Expense ratio', body: 'The fund’s annual expense ratio (%). A direct, certain drag on net return — lower is cheaper.' },
  cat_rank: { title: 'Category rank', body: 'Rank within the fund’s SEBI category by Atlas fund score, computed over the funds shown here (N of M). 1 = best in category. Ties broken by leadership-breadth, so every fund has a distinct position. The tag below (Top 10% / 20% / 50% / Bottom 50%) is the same rank as a within-category percentile.' },
  fund_score: { title: 'Fund score (composite)', body: 'Derived 0–100 composite of the fund’s holdings-weighted lenses — the SAME blend as a sector or stock, using the live lens weights from the thresholds panel (currently a 2-lens model: Technical + Flow), renormalised over the lenses present. Click the score to see the derivation. Valuation is context, not scored.' },
  rank_trend: { title: 'Rank trend', body: 'The fund’s category rank over time — one thin slice per trading day, green (best in category) → red (worst); hover a slice for its date and rank. The rank moves daily because the holdings are re-scored against each day’s stock lens scores. “stable Xd” = how many days the fund has held its current rank. “swing a / b” is the RANK SWING: the difference between its best and worst rank over the last 30 days (a) and 90 days (b) — a small swing means a steady rank, a large swing means it has bounced around the category. History runs from ~Feb 2026, when holdings first became available.' },
  fund_rs: { title: 'Relative strength (vs market)', body: 'The fund’s NAV return minus the index return over each window (1m · 3m · 6m · 12m), against Nifty 50 (N50) and Nifty 500 (N500) — the same idea as a stock’s relative strength. Green = the fund beat the index over that window, red = it lagged; numbers are percentage points. (The fund’s own stated TR benchmark isn’t in our price data, so the two broad market indices are used.) Hover a cell for the exact figure and the underlying fund/index returns. As of the latest published NAV.' },
  fund_ema: { title: '# holdings above EMA', body: 'How many of the fund’s latest-disclosed holdings are trading above their 21-, 50- and 200-day exponential moving average — within-portfolio trend breadth. A high count near 21 (short-term) with a high 200 (long-term) count means most of what the fund owns is in a healthy uptrend. Green when a majority are above. Hover for the count and share of priced holdings.' },
  sharpe: { title: 'Sharpe ratio', body: 'Return earned per unit of total risk: (annualised return − risk-free rate) ÷ annualised volatility, computed from the fund’s monthly NAV returns (risk-free assumed 6.5%). Higher is better; > 1 is strong. It rewards funds that deliver return without big swings.' },
  sortino: { title: 'Sortino ratio', body: 'Like Sharpe, but it only penalises DOWNSIDE volatility: (annualised return − risk-free) ÷ downside deviation. A fund with sharp gains but gentle drawdowns scores higher here than on Sharpe. Risk-free assumed 6.5%.' },
  max_drawdown: { title: 'Max drawdown', body: 'The worst peak-to-trough fall in NAV over the available history — how much a holder would have been down at the lowest point from a prior high. A small (less negative) number means the fund fell less in bad stretches.' },
  fund_volatility: { title: 'Volatility (annualised)', body: 'How much the fund’s monthly NAV return bounces around, annualised (standard deviation × √12). Lower = a smoother ride. Pair it with return to judge whether the return was worth the risk (that is the Sharpe ratio).' },
  fund_aum: { title: 'Assets under management', body: 'Fund size in ₹ crore (latest disclosed). Larger funds are more liquid; very large funds can find it harder to move in smaller names.' },
  weighted_lens: { title: 'Holdings-weighted lens', body: 'The portfolio’s score on this lens (0–100) = each holding’s lens score weighted by its portfolio weight. Shows what the fund/ETF actually owns, lens by lens.' },
  holding_weight: { title: 'Weight', body: 'The position’s share of the portfolio by latest disclosed weight (%). Drives the holdings-weighted roll-up.' },
  nav: { title: 'NAV', body: 'Net asset value per unit at the latest disclosed date — the fund’s per-unit price.' },
  aum: { title: 'AUM (₹ Cr)', body: 'Assets under management for the fund/ETF (₹ crore) at the latest disclosed date — its size.' },
  atlas_grade: { title: 'Atlas grade', body: 'A coarse letter grade (A best) summarising the holder fund/ETF’s overall lens quality — a quick read on whether a strong or weak vehicle holds this stock.' },
  ebitda: { title: 'EBITDA', body: 'Earnings before interest, tax, depreciation and amortisation (₹ crore) — operating cash profit before financing and accounting charges.' },
  // ── fundamentals ──
  ebitda_margin: { title: 'EBITDA margin', body: 'EBITDA ÷ revenue — operating profitability before depreciation, interest and tax. At sector level this is revenue-weighted: sector-total EBITDA ÷ sector-total revenue (not a flat average of each stock’s margin), so a ₹18,000 Cr major counts more than a ₹50 Cr micro-cap and a single tiny loss-maker can’t distort the read. Click the row to see every constituent’s own margin.' },
  rev_growth: { title: 'Revenue growth (YoY)', body: 'Revenue this quarter vs the same quarter a year ago, as a percent — the top-line trend.' },
  eps_growth: { title: 'EPS growth (YoY)', body: 'Earnings per share this quarter vs the same quarter a year ago — bottom-line growth per share.' },
  qoq_change: { title: 'Change QoQ', body: 'Percent change in the line above versus the immediately preceding quarter (this quarter ÷ last quarter − 1). The sequential trend, not year-over-year.' },
  revenue: { title: 'Revenue', body: 'Quarterly revenue (₹ crore) from the company’s filings.' },
  pat: { title: 'Net profit (PAT)', body: 'Profit after tax for the quarter (₹ crore) — the bottom line.' },
  eps: { title: 'EPS', body: 'Earnings per share for the quarter (₹) — net profit divided by shares outstanding.' },
  // ── flow (sector / stock) ──
  delivery_asym: { title: 'Up/down-day delivery asymmetry', body: 'Delivery % on up-days minus delivery % on down-days, in percentage points. It asks: on the days a stock rose, did more shares actually change hands (get delivered) than on the days it fell? POSITIVE = heavier real buying into strength than selling into weakness → accumulation (smart money adding on up-days). NEGATIVE = delivery clusters on down-days → distribution (real selling into declines). Around 0 = no directional bias. Roughly ranges −19…+18 across stocks.' },
  inst_flow: { title: 'Institutional flow score', body: 'A blended 0–100 measure of institutional / informed accumulation across the sector’s constituents (delivery strength, bulk/block deals, ownership change). 50 = neutral; above = net accumulation, below = net distribution.' },
  // ── breadth / market pulse ──
  pct_positive: { title: '% positive', body: 'Share of the sector’s constituents with a positive return over the window — a breadth read of how broad the move is.' },
  pct_top_decile_movers: { title: '% top-decile movers', body: 'Share of the sector’s constituents whose return ranks in the top decile of the whole universe over the window — concentration of the strongest movers.' },
  above_ema_count: { title: 'Above EMA (count)', body: 'Number of universe members trading above the given EMA (21 / 50 / 200). Read across now vs a week / month ago, the trend shows breadth widening or narrowing.' },
  golden_cross: { title: 'Golden cross', body: 'Members whose 50-EMA is above their 200-EMA — a long-trend-up structure. A rising count = broadening participation in the uptrend.' },
  net_new_highs: { title: 'Net new highs', body: 'New 52-week highs minus new 52-week lows across the universe. Positive = more names breaking out than breaking down.' },
  tier_return: { title: 'Cap-tier return', body: 'The cap-tier index return over the window (Large / Mid / Small). Compares where leadership sits across the size spectrum.' },
  smallcap_rs_z: { title: 'Smallcap RS (z)', body: 'Smallcap-vs-largecap relative strength as a 1-year z-score (standard deviations from its own mean). Positive = small-caps leading large-caps.' },
}
