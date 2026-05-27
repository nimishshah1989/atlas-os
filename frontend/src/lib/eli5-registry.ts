// frontend/src/lib/eli5-registry.ts
//
// L1 ELI5 copy for every Atlas v6 technical concept.
// Source: atlas-v6-ia.html §E.1 (archetypes) + §E.2 (cell metrics).
// 25 archetypes + 12 metrics. Lookup is case-sensitive on the registry key.

export interface ELI5Entry {
  /** One-sentence plain-English explanation. */
  text: string
  /** Anchor to /methodology section if the user wants the math. */
  mathAnchor?: string
}

export const ARCHETYPE_ELI5: Record<string, ELI5Entry> = {
  quality_momentum: {
    text:
      "Stocks already going up across multiple moving averages, with steady (not wild) volatility, tend to keep going.",
    mathAnchor: 'quality_momentum',
  },
  sector_relative_leadership: {
    text:
      "Stocks that lead their own sector usually continue leading — the sector tide lifts the leader's boat first.",
    mathAnchor: 'sector_relative_leadership',
  },
  bab_low_beta: {
    text:
      "Lower-beta stocks deliver more bang per unit of risk — the market over-prices excitement and under-prices stability.",
    mathAnchor: 'bab_low_beta',
  },
  bab_high_beta_short: {
    text:
      "Extremely high-beta stocks underperform their risk on a forward basis — a classic 'overpaying for thrill' anomaly.",
    mathAnchor: 'bab_high_beta_short',
  },
  mean_reversion: {
    text:
      "When a stock has fallen far enough from its own trend, the rubber-band snaps back — short-term oversold often rallies.",
    mathAnchor: 'mean_reversion',
  },
  mean_reversion_overbought: {
    text:
      "When a stock has stretched far enough above its own trend, profit-taking tends to pull it back — short-term overbought often softens.",
    mathAnchor: 'mean_reversion_overbought',
  },
  consolidation_breakout: {
    text:
      "After a tight sideways range, a clean break above the range with volume tends to keep going.",
    mathAnchor: 'consolidation_breakout',
  },
  breakout_with_pullback: {
    text:
      "The cleanest breakouts pull back to the breakout level, hold it, and then resume — buy the test, not the original break.",
    mathAnchor: 'breakout_with_pullback',
  },
  inflection: {
    text:
      "Stocks turning from down-trend to up-trend (or vice versa) at the moving-average cross often run for weeks before the news catches up.",
    mathAnchor: 'inflection',
  },
  deep_value: {
    text:
      "Stocks that fell hard a year ago, then stopped falling, often rebound — the worst was already priced in.",
    mathAnchor: 'deep_value',
  },
  deep_value_avoid: {
    text:
      "Deep-value stocks still trending down (no bottom yet) keep falling — 'cheap' is not a reason on its own.",
    mathAnchor: 'deep_value_avoid',
  },
  overextension: {
    text:
      "Price too far above its long moving average — mean reversion risk is high, expensive entries pay back over the next 3-6 months.",
    mathAnchor: 'overextension',
  },
  weak_quality: {
    text:
      "Stocks failing multiple trend filters at once (below 30W, below 50D, deteriorating RS) tend to keep underperforming.",
    mathAnchor: 'weak_quality',
  },
  breakdown: {
    text:
      "A clean break below long support, with volume, tends to keep going down — the inverse of a breakout.",
    mathAnchor: 'breakdown',
  },
  distribution: {
    text:
      "Heavy volume on down days but lighter volume on up days — institutions selling into strength. Often precedes 4–8 weeks of weakness.",
    mathAnchor: 'distribution',
  },
  volatility_spike: {
    text:
      "A sudden surge in realized vol from a low base — usually a shock signal — tends to be followed by more vol, not calm.",
    mathAnchor: 'volatility_spike',
  },
  low_vol_carry: {
    text:
      "Persistently low-vol leaders generate market-beating risk-adjusted returns — the slow boat actually wins.",
    mathAnchor: 'low_vol_carry',
  },
  liquidity_expansion: {
    text:
      "A sustained jump in daily turnover from a low base usually flags new institutional interest — buyers staying.",
    mathAnchor: 'liquidity_expansion',
  },
  liquidity_thrust_mfi: {
    text:
      "A short, intense burst of money-flow above a high MFI threshold often marks the start of a fresh leg up.",
    mathAnchor: 'liquidity_thrust_mfi',
  },
  mfi_overbought_distrib: {
    text:
      "Very high money-flow combined with volume distribution = stretched buyers handing off to sellers.",
    mathAnchor: 'mfi_overbought_distrib',
  },
  obv_thrust: {
    text:
      "On-balance volume making a clean new high while price is just behind tends to drag price forward over the next 1–3 months.",
    mathAnchor: 'obv_thrust',
  },
  obv_divergence_neg: {
    text:
      "Price making a new high but OBV making a lower high — buying pressure is fading. Quietly bearish.",
    mathAnchor: 'obv_divergence_neg',
  },
  sector_drag: {
    text:
      "Even strong stocks in weakening sectors tend to underperform — the macro sector tide eventually pulls.",
    mathAnchor: 'sector_drag',
  },
  sector_breakdown: {
    text:
      "When the sector itself breaks down, individual leadership rarely saves you — exit at the sector signal, not the stock signal.",
    mathAnchor: 'sector_breakdown',
  },
  structural: {
    text:
      "Long-horizon structural patterns (multi-year base, secular shift) — slow-burn signals that pay off across cycles.",
    mathAnchor: 'structural',
  },
}

export const METRIC_ELI5: Record<string, ELI5Entry> = {
  ic_mean: {
    text:
      "How well this rule's signal lines up with the next-N-day return, on average. 0.05 is industry-grade.",
    mathAnchor: 'ic-mean',
  },
  ic: {
    text:
      "Information coefficient — how strongly the rule's trigger predicts future returns. Above 0.05 is strong.",
    mathAnchor: 'ic-mean',
  },
  ic_ir: {
    text:
      "IC mean divided by IC standard deviation — how reliable the signal is, not just how strong. 0.5 is solid.",
    mathAnchor: 'ic-ir',
  },
  q_value: {
    text:
      "Adjusted false-discovery rate. Below 0.05 = unlikely to be a fluke after correcting for all the rules we tested.",
    mathAnchor: 'q-value',
  },
  bh_q_value: {
    text:
      "Benjamini-Hochberg FDR-adjusted q-value. Below 0.10 = signal is real after correcting for multiple testing.",
    mathAnchor: 'q-value',
  },
  bh_fdr: {
    text:
      "Benjamini-Hochberg FDR procedure: correcting q-values across many tested rules so we don't claim signal from chance.",
    mathAnchor: 'q-value',
  },
  friction_adjusted_excess: {
    text:
      "Annualized excess return after transaction costs and slippage. The number that survives reality.",
    mathAnchor: 'fric-adj',
  },
  fric_adj: {
    text:
      "Annualized excess return after transaction costs and slippage. The number that survives reality.",
    mathAnchor: 'fric-adj',
  },
  fric_adj_excess: {
    text:
      "Annualized excess return after transaction costs and slippage. The number that survives reality.",
    mathAnchor: 'fric-adj',
  },
  gate_pass: {
    text:
      "How many of the 12 rolling out-of-sample windows the rule passed our criteria in. 8 of 12 or higher is robust.",
    mathAnchor: 'gate-pass',
  },
  gate_pass_count: {
    text:
      "How many of the 12 rolling out-of-sample windows the rule passed our criteria in. 8 of 12 or higher is robust.",
    mathAnchor: 'gate-pass',
  },
  per_window_stability: {
    text:
      "Visual of returns across rolling out-of-sample windows. We want stable green bars, not one giant bar.",
    mathAnchor: 'per-window',
  },
  archetype: {
    text:
      "The plain-English bucket the rule belongs to (quality_momentum, mean_reversion, etc.) — the human-readable signal family.",
    mathAnchor: 'archetypes',
  },
}

/** Combined lookup. Archetype keys win over metric keys when both exist. */
export function eli5For(term: string): ELI5Entry | null {
  if (term in ARCHETYPE_ELI5) return ARCHETYPE_ELI5[term]
  if (term in METRIC_ELI5) return METRIC_ELI5[term]
  return null
}

/** All archetype keys — used by /methodology archetype tab. */
export function listArchetypes(): { key: string; entry: ELI5Entry }[] {
  return Object.entries(ARCHETYPE_ELI5).map(([key, entry]) => ({ key, entry }))
}

export function listMetrics(): { key: string; entry: ELI5Entry }[] {
  return Object.entries(METRIC_ELI5).map(([key, entry]) => ({ key, entry }))
}
