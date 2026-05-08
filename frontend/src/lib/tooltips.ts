// frontend/src/lib/tooltips.ts

// Every ⓘ tooltip in the app. Add sections as pages are built.
// Format: one-sentence what-it-is, then how-it-works.

export const TOOLTIPS = {
  // ── Regime ──────────────────────────────────────────────────────────────
  regime_state: `The overall market environment: Risk-On (deploy fully), Constructive (deploy at 70%), Cautious (deploy at 40%), or Risk-Off (no new exposure). Determined by a weighted vote across 18 breadth indicators — see methodology §11.`,

  deployment_multiplier: `Scales all position sizes. 1.0× in Risk-On means a 3% base size stays 3%. 0.0× in Risk-Off means no new positions regardless of instrument signal. Applied as a multiplier to the base position size at the portfolio level.`,

  dislocation_active: `A macro shock event (e.g. circuit-breaker day, systemic volatility spike) that overrides the regime to 0× deployment regardless of breadth readings. Triggered when 5-day realized volatility on the Nifty 500 exceeds 3× the 252-day median.`,

  india_vix: `India VIX is the NSE's implied volatility index, derived from Nifty 50 options. Values above 20 indicate elevated fear. Not a directional signal on its own — used as a regime corroborator.`,

  pct_above_ema_20: `Percentage of the 750-stock universe whose closing price is above its 20-day exponential moving average. Values above 50% indicate broad short-term participation; below 30% indicate broad distribution.`,

  pct_above_ema_50: `Percentage of the 750-stock universe above their 50-day EMA. The primary breadth anchor in the Atlas methodology (§11.1). A reading above 60% supports Constructive or better; below 40% supports Cautious or worse.`,

  pct_above_ema_200: `Percentage of the universe above their 200-day EMA. A structural breadth measure. Persistent readings below 50% indicate a bear market environment.`,

  ad_ratio: `Advance/Decline ratio: stocks advancing today ÷ stocks declining. Values above 1 are bullish (more stocks rising than falling). Computed daily from close prices across the 750-stock universe.`,

  ad_line: `Cumulative Advance/Decline line: the running sum of (advances − declines) each day. A rising line confirms market breadth is healthy even if the index appears range-bound. Divergence between the index and A/D line is a leading warning signal.`,

  ad_line_slope_21: `21-day slope of the cumulative A/D line, expressed in σ units (standard deviation of daily A/D changes over the same period). Positive = line is rising; negative = line is falling. Values beyond ±1.5σ indicate strong directional breadth.`,

  mcclellan_oscillator: `EMA(19) of net daily advances minus EMA(39) of net daily advances. A momentum oscillator of breadth — positive values indicate improving breadth momentum, negative indicate deteriorating. Crossing zero is a transition signal.`,

  mcclellan_summation: `Running cumulative sum of the McClellan Oscillator. A rising Summation Index confirms a healthy market structure; declining confirms broad deterioration. The absolute level matters: deep negative values take time to recover.`,

  new_52w_highs: `Count of stocks in the universe making new 252-trading-day (52-week) closing highs today. A healthy bull market sees expanding new highs. Values below 20 in a rising index suggest a narrowing leadership — a warning sign.`,

  new_52w_lows: `Count of stocks in the universe making new 252-trading-day closing lows today. Rising new lows while the index holds its level is a classic breadth divergence — often precedes a broader decline.`,

  net_new_highs: `New 52-week highs minus new 52-week lows. Positive = more stocks at new highs than lows (bullish breadth expansion). Negative = more lows than highs (breadth deterioration or distribution).`,

  pct_in_strong_states: `Percentage of the universe classified as Leader, Strong, or Emerging in the Atlas RS state model. A high-quality breadth measure: it filters out stocks that are technically above a moving average but still in weak RS states.`,

  pct_weinstein_pass: `Percentage of the universe passing the Weinstein gate: price above the 30-week moving average AND that moving average has a positive slope over the last 4 weeks. A structural filter for Stage 2 uptrends per Stan Weinstein's Stage Analysis.`,

  nifty500_ema_50_slope: `Slope of the Nifty 500's 50-day EMA over the last 21 trading days, expressed in σ units. A positive slope confirms the index's trend is accelerating upward; a flattening or negative slope indicates a trend under stress.`,

  nifty500_ema_200_slope: `Slope of the Nifty 500's 200-day EMA over the last 21 trading days. A long-term structural indicator. Negative slope is a significant bear market signal.`,

  new_high_low_ratio: `New 52-week highs ÷ max(new 52-week lows, 1). Values above 1 are bullish (more highs than lows). Used as a normalized breadth measure that adjusts for total market participation.`,
} as const

export type TooltipKey = keyof typeof TOOLTIPS
