// frontend/src/lib/eli5/thesis-data.ts
//
// Archetype bullet templates for the thesis registry.
// Each archetype has POSITIVE and/or NEGATIVE variants.
// Placeholders use {{key}} syntax, resolved by thesis.ts generateThesis().
// Source of truth: docs/v6/design-application.md §4
//
// NOTE: This file is DATA only — no logic, no imports.

export interface ArchetypeTemplate {
  /** Bullets for POSITIVE direction (3-5 entries, 10-25 words each) */
  positive?: string[]
  /** Bullets for NEGATIVE direction (3-5 entries, 10-25 words each) */
  negative?: string[]
}

export const ARCHETYPE_TEMPLATES: Record<string, ArchetypeTemplate> = {
  // ── 1. Sector Relative Leadership ───────────────────────────────────────────
  sector_relative_leadership: {
    positive: [
      "Top-ranked {{cap_tier}}-cap in sector **#{{sector_rank}}**-of-30; {{sector_name}} sector RS is in the top quartile.",
      "**{{sector_breadth_pos}}%** of {{sector_name}} sector names above 200d SMA — sector breadth confirms leadership.",
      "Stock leads its sector cohort by **{{vs_cohort_pp}}pp** over {{tenure}} — sector RS momentum self-reinforcing.",
      "Cell IC **{{ic}}** across {{tenure}} window; sector breadth and individual RS aligned.",
      "Hold as long as {{sector_name}} sector rank stays above 20-of-30; exit on sector degradation.",
    ],
    negative: [
      "Sector {{sector_name}} ranked **#{{sector_rank}}**-of-30 weakest — sector RS at the bottom.",
      "Sector breadth collapsed: only **{{sector_breadth_pos}}%** of {{sector_name}} names above 200d SMA.",
      "RS deteriorating versus Nifty 500 by **{{vs_nifty500_pp}}pp** over {{tenure}} — sector drag confirmed.",
      "Even strong stocks in the weakest sector underperform — sector tide drags the leader.",
      "Avoid until {{sector_name}} sector rank recovers above 20-of-30; monitor sector RS weekly.",
    ],
  },

  // ── 2. Quality Momentum ──────────────────────────────────────────────────────
  quality_momentum: {
    positive: [
      "Sustained {{cap_tier}}-cap leader — **{{vs_cohort_pp}}pp** above cohort; volatility **{{vol_60d_vs_avg}}x** below cohort average.",
      "Above 20W, 50D, and 200D SMA simultaneously — multi-timeframe trend confirmation.",
      "RS rank in top quartile of {{cap_tier}}-cap universe over {{tenure}}; momentum persistent.",
      "Low-volatility cohort outperformance pattern validated — quality momentum with **{{ic}}** IC.",
      "Thesis holds as long as price stays above 50D SMA and sector rank does not breach bottom quartile.",
    ],
    negative: [
      "Quality signals deteriorating — now **{{vs_cohort_pp}}pp** below cohort average over {{tenure}}.",
      "Below 200D SMA; multi-timeframe trend flipped negative; volatility expanding **{{vol_60d_vs_avg}}x** above cohort.",
      "RS rank has dropped out of top quartile; momentum reversal pattern confirmed in {{cap_tier}}-cap cohort.",
      "Cohort underperformance confirmed — volatility and RS both breached their thresholds simultaneously.",
      "Quality momentum breakdown: trend filters failing across multiple timeframes in this cohort.",
    ],
  },

  // ── 3. Betting Against Beta (Low Beta) ──────────────────────────────────────
  bab_low_beta: {
    positive: [
      "Low-beta {{cap_tier}}-cap survivor with positive momentum — risk-adjusted alpha historically persistent.",
      "Beta below cohort median; excess return per unit of risk is **{{vs_cohort_pp}}pp** over {{tenure}}.",
      "Defensive carry pattern: lower drawdown profile + positive RS — slow boat wins the race.",
      "BAB anomaly validated on {{cap_tier}}-cap cohort at **{{ic}}** IC; volatility **{{vol_60d_vs_avg}}x** below peers.",
      "Hold as a defensive anchor; momentum confirmation keeps the alpha durable, not theoretical.",
    ],
    negative: [
      "High-beta {{cap_tier}}-cap stock underperforming on a risk-adjusted basis — overpaying for beta.",
      "Beta above cohort median with RS deteriorating by **{{vs_cohort_pp}}pp** over {{tenure}}.",
      "High-beta names underperform forward — the market over-prices thrill and over-punishes on turns.",
      "Avoid: volatility **{{vol_60d_vs_avg}}x** above peers with negative momentum confirms BAB short signal.",
      "Exit or avoid until beta normalises relative to {{cap_tier}}-cap cohort and RS stabilises.",
    ],
  },

  // ── 4. Mean Reversion (Dip Buy) ─────────────────────────────────────────────
  mean_reversion: {
    positive: [
      "Leader pulled back **{{dd_pct}}%** from 52w high — buyable dip within an intact uptrend.",
      "RSI at oversold extreme but 12m RS still positive — rubber-band snap-back setup.",
      "Drawdown from peak is within historical bounce zone for {{cap_tier}}-cap pullbacks.",
      "Cell IC **{{ic}}** on {{tenure}} pullback window; prior leaders recover faster than laggards.",
      "Entry thesis: stock remains above 200D SMA and RS rank holds above cohort median.",
    ],
    negative: [
      "Attempted pullback from 52w low failed — trend still negative with no bottom confirmation.",
      "RSI overbought while 12m RS deteriorating — mean reversion bounce risk; avoid the pullback trap.",
      "Pullback from 52w-high to 52w-low zone incomplete; {{cap_tier}}-cap distribution pattern unresolved over {{tenure}}.",
      "No RS recovery signal yet — falling-knife pattern; pullback entries historically unprofitable here.",
      "Wait for RSI reset AND positive RS cross before re-entering; downside momentum persists.",
    ],
  },

  // ── 5. Liquidity Expansion ───────────────────────────────────────────────────
  liquidity_expansion: {
    positive: [
      "Rising turnover (z-score **{{vol_z}}**) plus positive RS — institutional accumulation signal.",
      "Volume z-score spike from a low base confirms new buyer interest entering the {{cap_tier}}-cap.",
      "Liquidity expansion pattern: sustained turnover increase over **{{tenure}}** with price holding.",
      "RS versus Nifty 500 is **+{{vs_nifty500_pp}}pp** — price strength confirms the volume thesis.",
      "Hold as long as turnover z-score remains elevated and RS rank stays in top half of cohort.",
    ],
    negative: [
      "Volume collapsing (z-score **{{vol_z}}**) — institutional distribution; buyers stepping away.",
      "Turnover declining from a high base while price weakens — distribution pattern confirmed.",
      "Liquidity contraction with deteriorating RS by **{{vs_nifty500_pp}}pp** over {{tenure}}.",
      "Sellers dominating on high volume; {{cap_tier}}-cap liquidity contraction historically precedes further decline.",
      "Avoid until turnover z-score stabilises and RS shows evidence of a floor forming.",
    ],
  },

  // ── 6. Inflection ────────────────────────────────────────────────────────────
  inflection: {
    positive: [
      "Just crossed above SMA200 with RS rank accelerating — early-stage trend change signal.",
      "Price inflection from below to above 200D SMA; momentum cycle reset favours bulls over {{tenure}}.",
      "RS rank turning from bottom-half to top-half of {{cap_tier}}-cap cohort — early trend leader.",
      "Cell IC **{{ic}}** on inflection pattern — trend-following entry post confirmation is historically clean.",
      "Conviction grows if the 200D SMA cross holds for 5+ days and RS rank maintains above cohort median.",
    ],
    negative: [
      "Crossed BELOW SMA200 — trend inflection to the downside confirmed for {{cap_tier}}-cap.",
      "RS rank deteriorating from top-half to bottom-half of cohort over {{tenure}} — inflection turning negative.",
      "200D SMA break with declining volume confirms distribution, not a short-term dip.",
      "Negative inflection: price and RS simultaneously rolling over — avoid until stabilisation.",
      "Exit on confirmation of two consecutive closes below 200D SMA with RS in bottom quartile.",
    ],
  },

  // ── 7. Consolidation Breakout ────────────────────────────────────────────────
  consolidation_breakout: {
    positive: [
      "Low-volatility base plus close at new **{{n_day}}**-day high — clean breakout setup.",
      "ATR contraction followed by expansion; breakout above prior range resistance on above-average volume.",
      "Consolidation period compressed volatility — energy release tends to sustain over {{tenure}}.",
      "RS versus cohort **+{{vs_cohort_pp}}pp** — breakout stock leading peers at the moment of break.",
      "Hold as long as price remains above the breakout level; first pullback to that level is a re-entry.",
    ],
    negative: [
      "Failed breakout — closed above resistance but reversed within 3 days; bull trap confirmed.",
      "Consolidation breaking DOWN; volatility expanding as support failed on above-average volume.",
      "ATR expanding on a downside break; volatility regime flipped — momentum now negative over {{tenure}}.",
      "RS deteriorating by **{{vs_cohort_pp}}pp** — failed breakout with cohort underperformance in {{cap_tier}}-cap.",
      "Avoid until a new consolidation base forms above the failed breakout level with stable volatility.",
    ],
  },

  // ── 8. Structural ────────────────────────────────────────────────────────────
  structural: {
    positive: [
      "10+ year ascending trend in {{cap_tier}}-cap universe — multi-cycle structural leadership.",
      "Top-decile RS sustained across multiple bear markets; structural anomaly not explained by sector.",
      "Multi-year base breakout; secular shift in fundamentals corroborated by RS trend over {{tenure}}.",
      "Cell IC **{{ic}}** on structural pattern — slow-burn signal with durability across regimes.",
      "Hold through volatility; structural signals require patience but deliver across full cycles.",
    ],
    negative: [
      "Structural support broken — multi-year ascending trendline violated on a monthly close.",
      "Top-decile RS collapsed; {{cap_tier}}-cap stock now in bottom quartile for the first time in years.",
      "Secular breakdown: long-term ascending trend failed — structural negative over {{tenure}}.",
      "Structural deterioration confirmed; position exit warranted before further cycle-level losses.",
      "Avoid until a new multi-year base forms and RS recovers above the long-term cohort median.",
    ],
  },

  // ── 9. Deep Value ────────────────────────────────────────────────────────────
  deep_value: {
    positive: [
      "Multi-year drawdown plus stock still listed — recovery accelerating over {{tenure}}.",
      "Price has stopped falling; RS starting to stabilise above the bottom decile of {{cap_tier}}-cap.",
      "Deep-value recovery pattern: worst already priced in; downside exhaustion confirmed.",
      "Cell IC **{{ic}}** on deep-value recovery window — entry when worst is priced in historically rewarding.",
      "Thesis requires patience over {{tenure}}; exit if RS drops back to bottom decile after entry.",
    ],
    negative: [
      "Deep-value stock with no recovery signal — still in downtrend; cheap is not a catalyst.",
      "Price declining over {{tenure}} with no RS stabilisation — deep-value AVOID; recovery not confirmed.",
      "No evidence of bottom formation; {{cap_tier}}-cap deep-value short: downtrend and no recovery acceleration.",
      "Avoid: multi-year drawdown without RS floor; recovery and downside exhaustion both absent.",
      "Wait for RSI reset above 30 AND positive RS cross before considering this a recoverable dip.",
    ],
  },

  // ── 10. Low Vol Carry ────────────────────────────────────────────────────────
  low_vol_carry: {
    positive: [
      "Low-volatility {{cap_tier}}-cap with stable positive returns — defensive carry pattern over {{tenure}}.",
      "Annualized vol **{{vol_60d_vs_avg}}x** below cohort average; risk-adjusted outperformance persistent.",
      "Low-vol carry anomaly: slow-moving leaders outperform on a Sharpe-adjusted basis across regimes.",
      "RS versus Nifty 500 **+{{vs_nifty500_pp}}pp** — outperformance without excess risk is durable.",
      "Hold as a defensive core; thesis breaks only if vol spikes above cohort median for 10+ days.",
    ],
    negative: [
      "Realized volatility spiking above cohort average — low-vol carry thesis invalidated; carry premium evaporating.",
      "Risk-adjusted carry deteriorating; realized volatility now **{{vol_60d_vs_avg}}x** above cohort median.",
      "Low-vol carry short: volatility expansion with negative RS confirms the carry anomaly has reversed.",
      "RS vs Nifty 500 deteriorating by **{{vs_nifty500_pp}}pp** — carry premium eroding rapidly.",
      "Exit when volatility crosses above cohort median for 5+ consecutive days; carry thesis no longer intact.",
    ],
  },

  // ── 11. Breakout With Pullback ───────────────────────────────────────────────
  breakout_with_pullback: {
    positive: [
      "52w high recently then small pullback — momentum continuation setup at the retest.",
      "Clean breakout from a multi-month base; pullback held at prior breakout level — classic re-entry.",
      "Volume lower on pullback, higher on the original break — institutional fingerprint intact.",
      "RS versus cohort **+{{vs_cohort_pp}}pp** — stock leading peers even on the pullback.",
      "Entry at the retest of the breakout level; stop below the breakout origin.",
    ],
    negative: [
      "Breakout at 52w high reversed sharply; pullback exceeded the original breakout level — bull trap.",
      "Failed retest from 52w high: price could not hold above breakout level on two attempts over {{tenure}}.",
      "Volume dry-up during the bounce from 52w-high zone; selling pressure resuming at the failed breakout.",
      "RS deteriorating by **{{vs_cohort_pp}}pp** — failed breakout-with-pullback pattern; cohort underperformance.",
      "Avoid: broken breakout from 52w high with elevated volume on the downside leg.",
    ],
  },

  // ── 12. Idiosyncratic High RS ────────────────────────────────────────────────
  idio_high_RS: {
    positive: [
      "High idiosyncratic volatility plus top-quartile RS — alpha-rich setup independent of sector.",
      "Stock RS outpacing sector RS by a wide margin; stock-specific catalyst driving excess returns.",
      "Idiosyncratic momentum over {{tenure}}: **+{{vs_nifty500_pp}}pp** vs Nifty 500 not explained by sector.",
      "Cell IC **{{ic}}** on idio-RS pattern — high idio vol with positive RS historically alpha-generating.",
      "Hold as long as stock RS leads sector RS; exit if sector catches up and idio premium collapses.",
    ],
    negative: [
      "Idiosyncratic RS turned negative — stock underperforming its sector by a wide margin.",
      "Stock-specific negative event eroding idiosyncratic RS; high vol with adverse direction.",
      "RS deteriorated by **{{vs_nifty500_pp}}pp** relative to Nifty 500 over {{tenure}} — idiosyncratic breakdown.",
      "Idiosyncratic risk without idiosyncratic reward: underperforming sector peers on high volatility.",
      "Avoid until idiosyncratic RS stabilises relative to sector and stock-specific headwind clears.",
    ],
  },

  // ── 13. OBV Thrust ───────────────────────────────────────────────────────────
  obv_thrust: {
    positive: [
      "On-balance volume thrust — OBV making new high while price is just behind; accumulation confirmed.",
      "OBV leading price: buyers absorbing supply consistently over {{tenure}} in {{cap_tier}}-cap.",
      "Volume confirmed uptrend — OBV divergence positive; institutional accumulation pattern.",
      "RS versus Nifty 500 **+{{vs_nifty500_pp}}pp** — OBV thrust with RS leadership is a clean setup.",
      "Hold as long as OBV continues making higher highs; any OBV divergence (lower high) is an exit signal.",
    ],
    negative: [
      "OBV divergence negative — price at new high but on-balance volume making a lower high; distribution.",
      "Selling pressure outpacing buying volume even as price holds; OBV accumulation exhausted over {{tenure}}.",
      "OBV rolling over in {{cap_tier}}-cap — institutional selling into price strength on rising volume.",
      "Negative OBV divergence with RS deteriorating by **{{vs_nifty500_pp}}pp** — volume distribution at top.",
      "Exit when OBV breaks its prior low; volume distribution pattern historically precedes 4-8 weeks weakness.",
    ],
  },

  // ── 14. Mean Reversion Overbought ────────────────────────────────────────────
  mean_reversion_overbought: {
    positive: [
      "Overbought extreme resolving — RSI reset and price pulling back to 200D SMA support zone.",
      "Overextension from 200D SMA narrowing; bounce from oversold after overbought extreme over {{tenure}}.",
      "RS bottoming after overbought correction; {{cap_tier}}-cap cohort breadth stabilising.",
      "Cell IC **{{ic}}** on post-overbought reversion; historically clean bounce at 200D retest.",
      "Entry only if RSI resets below 40 AND price holds 200D SMA on at least two tests.",
    ],
    negative: [
      "RSI **{{rsi}}** plus **{{dist_sma200_pct}}%** above 200D SMA — stretched and at risk of mean reversion.",
      "Stock **{{dist_sma200_pct}}%** extended from 200D SMA; cohort median extension is far lower.",
      "Overbought: RSI in extreme territory over {{tenure}}; profit-taking historically follows at this extension.",
      "RS temporarily elevated; regression to cohort mean likely over the next {{tenure}} period.",
      "Avoid new entries; existing holders consider partial reduction at this extension level.",
    ],
  },

  // ── 15. Distribution ─────────────────────────────────────────────────────────
  distribution: {
    positive: [
      "Distribution pattern resolved — volume z-score normalising and RS recovering over {{tenure}}.",
      "Selling pressure absorbed; accumulation re-emerging with positive OBV trend.",
      "Post-distribution recovery: RS improving by **+{{vs_cohort_pp}}pp** vs cohort.",
      "Volume pattern turning constructive after a distribution phase in {{cap_tier}}-cap.",
      "Re-entry signal: volume lower on down days, higher on up days — accumulation confirmed.",
    ],
    negative: [
      "Volume z-score high on down days; RS deteriorating — distribution at top confirmed.",
      "Heavy volume on weakness, light volume on bounces — institutions selling into strength.",
      "Distribution pattern over {{tenure}}: **{{vol_z}}** volume z-score spike with negative RS.",
      "RS versus cohort deteriorating by **{{vs_cohort_pp}}pp** — distribution precedes sustained decline.",
      "Avoid: historical distribution patterns in {{cap_tier}}-cap precede 4-8 weeks of underperformance.",
    ],
  },

  // ── 16. Volatility Spike ─────────────────────────────────────────────────────
  volatility_spike: {
    positive: [
      "Volatility regime stabilising after spike — vol mean-reverting with RS starting to recover.",
      "Post-spike RS recovery: **+{{vs_nifty500_pp}}pp** vs Nifty 500 as vol normalises.",
      "Volatility spike absorbed; {{cap_tier}}-cap breadth recovering above 200D SMA.",
      "Watch for follow-through: vol needs to stay below **{{vol_60d_vs_avg}}x** cohort for 5+ days.",
      "Position sizing should remain reduced until vol confirms sustained normalisation.",
    ],
    negative: [
      "Vol regime expanding with RS falling — caution; {{cap_tier}}-cap vol spike in progress.",
      "Realized vol **{{vol_60d_vs_avg}}x** above cohort average; shock signal — more vol likely follows.",
      "Volatility spike from a low base: sudden regime change, RS deteriorating by **{{vs_nifty500_pp}}pp**.",
      "Watch but do not buy — vol spikes in {{cap_tier}}-cap historically precede 2-4 weeks of further weakness.",
      "Reduce exposure; wait for vol to settle below cohort median before re-engaging.",
    ],
  },

  // ── 17. Breakdown ────────────────────────────────────────────────────────────
  breakdown: {
    positive: [
      "Breakdown reversal — price reclaimed 52w-low band; RS turning positive after negative 12m RS.",
      "RS recovering from negative 12m RS extreme; breakdown thesis invalidated by sustained reclaim.",
      "Post-breakdown recovery: price held above the breakdown level for 5+ days with positive RS.",
      "Cell IC **{{ic}}** on breakdown recovery — stocks that retake the breakdown zone recover quickly.",
      "Entry signal: close above 252D-low band for two consecutive days with improving RS.",
    ],
    negative: [
      "Close below 252D-low band plus negative 12m RS — breakdown confirmed across {{tenure}}.",
      "52w-low breach on above-average volume; negative 12m RS confirms directional momentum.",
      "Breakdown pattern in {{cap_tier}}-cap: new multi-year low with no RS floor visible.",
      "Historical {{cap_tier}}-cap breakdown signal: IC **{{ic}}** — downside continuation likely over {{tenure}}.",
      "Avoid: breakdowns below 252D-low band historically produce sustained underperformance for 3-6 months.",
    ],
  },

  // ── 18. Sector Drag ──────────────────────────────────────────────────────────
  sector_drag: {
    positive: [
      "Sector {{sector_name}} drag reversing — sector rank recovering; breadth expanding above 200D SMA.",
      "**{{sector_breadth_pos}}%** of {{sector_name}} names now above 200D SMA — sector tide turning.",
      "Sector RS recovering; stock RS following with **+{{vs_cohort_pp}}pp** vs cohort over {{tenure}}.",
      "Sector drag thesis resolved; accumulate as {{sector_name}} rank moves back above bottom quartile.",
      "Sector recovery with individual stock RS leadership — double confirmation of reversal.",
    ],
    negative: [
      "{{sector_name}} sector ranked **#{{sector_rank}}**-of-30 weakest; breadth at only **{{sector_breadth_pos}}%** above SMA200.",
      "Sector drag confirmed: even strong stocks in weakest sectors underperform over {{tenure}}.",
      "Sector RS deteriorating; **{{sector_breadth_pos}}%** breadth means most names in the sector are falling.",
      "Avoid until {{sector_name}} rank recovers above bottom quartile; sector macro tide overrides stock alpha.",
      "Individual stock strength insufficient — sector drag historically pulls all names lower within 4-8 weeks.",
    ],
  },

  // ── 19. Sector Breakdown ─────────────────────────────────────────────────────
  sector_breakdown: {
    positive: [
      "Sector {{sector_name}} recovery after breakdown — sector RS rebuilding from a depressed base.",
      "Fading-leader pattern resolved; sector rank recovering with stock RS confirming the turn.",
      "**{{sector_breadth_pos}}%** of sector back above 200D SMA — breadth expanding post-breakdown.",
      "Sector breakdown reversal: stock leading sector RS recovery by **+{{vs_cohort_pp}}pp** over {{tenure}}.",
      "Enter when sector rank crosses above the bottom quartile AND individual RS is positive.",
    ],
    negative: [
      "Strong stock in a weakening sector — fading-leader pattern; sector breakdown overrides stock alpha.",
      "{{sector_name}} sector breaking down; even the strongest names in this sector lose RS over {{tenure}}.",
      "Sector breadth collapsed to **{{sector_breadth_pos}}%** above 200D SMA — sector-level breakdown confirmed.",
      "Individual RS positive but sector RS negative — sector breakdown historically drags leaders within 6-8 weeks.",
      "Avoid: wait for sector to stabilise before re-entering even a fundamentally strong name in this cohort.",
    ],
  },
}
